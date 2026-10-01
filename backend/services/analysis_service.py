"""Single UI/API entrypoint: extraction, checks, semantics, scoring, normalized result."""
import logging
import re

from backend.analyzers.basic_analyzer import BasicAnalyzer
from backend.analyzers.gemini_analyzer import GeminiAnalyzer
from backend.analyzers.fallback_analyzer import match_requirement
from backend.config import SCORING_VERSION, Settings
from backend.exceptions import InvalidCVError, LLMError, LLMFailureReason, LLMResponseError, LLMUnavailableError
from backend.models import (AISemanticAnalysis, AnalysisMetadata, CVAnalysisResult, CVDocument,
                            Recommendation, RequirementMatch, SemanticJudgment)
from backend.normalization import normalize_skill, normalize_skills, normalized_text, skill_in_text, valid_evidence
from backend.parsers.cv_parser import CVParser
from backend.parsers.jd_parser import JDParser
from backend.prompts.cv_analysis_prompt import PROMPT_VERSION
from backend.providers.gemini_provider import GeminiProvider
from backend.services.scoring_service import ScoringService

logger = logging.getLogger(__name__)
AI_FALLBACK_WARNING = "AI semantic analysis is temporarily unavailable. Basic CV checks are still available."
AI_FAILURE_WARNINGS = {
    LLMFailureReason.MISSING_KEY: "AI analysis is not configured. Set GEMINI_API_KEY in the project's .env file or Streamlit secrets, then analyze again. Basic CV checks are still available.",
    LLMFailureReason.AUTHENTICATION: "The AI provider rejected access. Check the API key and its project permissions.",
    LLMFailureReason.QUOTA: "The AI provider's quota or rate limit was reached. Check usage limits or try again later.",
    LLMFailureReason.TIMEOUT: "The AI request timed out. Try again later.",
    LLMFailureReason.NETWORK: "The AI provider could not be reached. Check the server's network connection.",
    LLMFailureReason.MODEL_UNAVAILABLE: "The configured AI model was not found. Check GEMINI_MODEL and model access.",
    LLMFailureReason.REQUEST_REJECTED: "The AI provider rejected the request. Check the API key, model and request configuration.",
    LLMFailureReason.SERVICE_UNAVAILABLE: "The AI provider encountered a service error. Try again later.",
    LLMFailureReason.INVALID_RESPONSE: "The AI response could not be validated. Basic CV checks are still available.",
}


def _fallback_reason(error):
    if isinstance(error, LLMUnavailableError):
        return error.reason
    if isinstance(error, LLMResponseError):
        return LLMFailureReason.INVALID_RESPONSE
    if isinstance(error, TimeoutError):
        return LLMFailureReason.TIMEOUT
    if isinstance(error, ConnectionError):
        return LLMFailureReason.NETWORK
    return LLMFailureReason.UNKNOWN
SAFE_ACTIONS = {
    "content": "Clarify your real action, scope, ownership and outcome. Include metrics only when you can verify them.",
    "structure": "Use clear section headings and review contact details in the extracted text.",
    "skills": "If you genuinely have experience with the relevant skills, make that evidence clearer. Do not add unsupported skills.",
    "experience": "Describe only work or internships you actually completed, including your contribution and scope.",
    "projects": "Describe only projects you actually completed, including tools, your contribution and outcome.",
    "education": "Clarify your actual degree, field, study status and relevant coursework.",
}


class AnalysisService:
    def __init__(self, *, settings=None, provider=None, ai_analyzer=None, basic_analyzer=None,
                 scoring_service=None, cv_parser=None, jd_parser=None):
        self.settings = settings or Settings.from_env()
        self.cv_parser = cv_parser or CVParser()
        self.jd_parser = jd_parser or JDParser()
        self.basic_analyzer = basic_analyzer or BasicAnalyzer()
        self.scoring_service = scoring_service or ScoringService()
        self.provider = provider if provider is not None else GeminiProvider(self.settings)
        self.ai_analyzer = ai_analyzer or GeminiAnalyzer(self.provider, self.jd_parser)

    def close(self):
        close = getattr(self.provider, "close", None)
        if close:
            close()

    def analyze_cv(self, cv_document: CVDocument, jd_text: str | None = None,
                   target_position: str | None = None, industry: str | None = None) -> CVAnalysisResult:
        if not isinstance(cv_document, CVDocument) or not cv_document.raw_text.strip():
            raise InvalidCVError("Supply a nonempty CV document.")
        if len(cv_document.raw_text) > self.settings.max_document_chars:
            raise InvalidCVError("The CV is too large. Supply a shorter document.")
        if jd_text is not None and not isinstance(jd_text, str):
            raise InvalidCVError("The Job Description must be text.")
        jd_text = jd_text.strip() if jd_text else None
        if jd_text and len(jd_text) > self.settings.max_document_chars:
            raise InvalidCVError("The Job Description is too large.")
        profile = self.cv_parser.parse(cv_document, industry)
        jd = self.jd_parser.parse(jd_text) if jd_text else None
        checks = self.basic_analyzer.analyze(cv_document, profile)
        warnings = [checks.extraction_warning] if checks.extraction_warning else []
        semantic = None
        try:
            semantic = self.ai_analyzer.analyze(cv_document, jd_text, target_position, industry)
            semantic = self._ground_semantics(semantic, cv_document, warnings)
        except (LLMError, TimeoutError, ConnectionError) as error:
            reason = _fallback_reason(error)
            logger.warning("AI fallback activated (reason=%s)", reason.value)
            if reason != LLMFailureReason.MISSING_KEY:
                warnings.append(AI_FALLBACK_WARNING)
            if reason in AI_FAILURE_WARNINGS:
                warnings.append(AI_FAILURE_WARNINGS[reason])
        matches = self._matches(jd, cv_document, profile, semantic, warnings) if jd else []
        skills = normalize_skills(profile.skills + (semantic.detected_skills if semantic else []))
        score = self.scoring_service.score(profile, checks, semantic, jd, matches)
        recommendations = self._recommendations(checks, matches, semantic)
        strengths = semantic.strengths if semantic else (["Skills are explicitly present in the CV."] if profile.skills else [])
        weaknesses = semantic.weaknesses if semantic else [f"Section not detected: {name}." for name in checks.missing_sections]
        if not semantic:
            warnings.append("Deterministic fallback uses text evidence; semantic relevance is not fully assessed.")
        if jd and not jd.requirements:
            warnings.append("No assessable requirements were found in the Job Description.")
        skill_states = {"matched": [], "missing": [], "partial": []}
        # Skill lists contain only JD skills, with one conservative aggregate state per skill.
        grouped = {}
        for requirement, match in zip(jd.requirements if jd else [], matches):
            if requirement.skill_name:
                grouped.setdefault(requirement.skill_name, []).append(match.status)
        for skill, statuses in grouped.items():
            state = "matched" if all(s == "matched" for s in statuses) else "missing" if all(s == "missing" for s in statuses) else "partial"
            skill_states[state].append(skill)
        mode = "job_match" if jd else "cv_only"
        return CVAnalysisResult(mode=mode, overall_score=score.overall_score, scores=score.scores,
            candidate_summary=semantic.candidate_summary if semantic else profile.summary or "CV analyzed using basic document checks and explicit text evidence.",
            detected_skills=skills, strengths=strengths, weaknesses=weaknesses, basic_checks=checks,
            recommendations=recommendations, matched_skills=skill_states["matched"],
            missing_skills=skill_states["missing"], partially_matched_skills=skill_states["partial"],
            requirement_matches=matches, warnings=list(dict.fromkeys(warnings)), ai_available=semantic is not None,
            analysis_metadata=AnalysisMetadata(model=getattr(self.provider, "model_name", None) if semantic else None,
                prompt_version=PROMPT_VERSION if semantic else None, scoring_version=SCORING_VERSION,
                ai_available=semantic is not None, analysis_mode=mode, scoring_components=score.components,
                effective_weights=score.effective_weights))

    @staticmethod
    def _ground_semantics(semantic: AISemanticAnalysis, document, warnings):
        semantic = semantic.model_copy(deep=True)
        semantic.detected_skills = normalize_skills([skill for skill in semantic.detected_skills
                                                    if skill_in_text(skill, document.raw_text)])
        changed = False
        for name in ("content_quality", "experience_quality", "project_quality", "education_quality", "skill_quality",
                     "role_relevance", "experience_relevance", "project_relevance", "education_relevance"):
            judgment = getattr(semantic, name)
            if judgment is None:
                continue
            quotes = valid_evidence(judgment.evidence, document.raw_text)
            if judgment.quality != "unknown" and not quotes:
                setattr(semantic, name, SemanticJudgment(quality="unknown"))
                changed = True
            else:
                judgment.evidence = quotes
        if changed:
            warnings.append("Some AI judgments lacked verifiable CV evidence and were excluded from scoring.")
        for suggestion in semantic.recommendations:
            suggestion.evidence = valid_evidence(suggestion.evidence, document.raw_text)
        return semantic

    @staticmethod
    def _matches(jd, document, profile, semantic, warnings):
        index = {}
        if semantic:
            for match in semantic.requirements:
                key = normalized_text(normalize_skill(match.requirement))
                if key in index:
                    # Duplicated conclusions are ambiguous; use conservative local evidence.
                    index[key] = None
                else:
                    index[key] = match
        results = []
        changed = False
        for requirement in jd.requirements:
            ai_match = index.get(normalized_text(normalize_skill(requirement.requirement)))
            if ai_match is None:
                results.append(match_requirement(requirement, document, profile))
                continue
            quotes = valid_evidence(ai_match.evidence, document.raw_text)
            status = ai_match.status
            invalid = False
            if status != "missing" and not quotes:
                status = "missing"
                changed = True
                invalid = True
            elif requirement.skill_name and requirement.category in {"hard_skill", "other"} and status == "matched":
                # A keyword in Skills, alone, is never proof of proficiency.
                supporting = "\n".join(profile.experience + profile.projects + profile.education + profile.certifications)
                if not skill_in_text(requirement.skill_name, supporting) or not any(skill_in_text(requirement.skill_name, quote) for quote in quotes):
                    status = "partial"
            elif requirement.category == "experience" and status == "matched":
                experience_text = normalized_text("\n".join(profile.experience))
                if not any(normalized_text(quote) in experience_text for quote in quotes):
                    status = "partial"
                elif re.search(r"\b\d+\+?\s*(?:years?|yrs?)\b", requirement.requirement, re.I):
                    # Explicit local duration must support a full match. Date-based
                    # inference remains partial until a richer experience parser exists.
                    local = match_requirement(requirement, document, profile)
                    if local.status != "matched":
                        status = "partial"
            results.append(RequirementMatch(requirement=requirement.requirement, status=status,
                                           evidence=quotes if status != "missing" else [],
                                           explanation=ai_match.explanation if not invalid else "Unverifiable evidence was excluded."))
        if changed:
            warnings.append("Some requirement matches lacked verifiable CV evidence and were downgraded.")
        return results

    @staticmethod
    def _recommendations(checks, matches, semantic):
        items = []
        for match in matches:
            if match.status != "matched":
                items.append(Recommendation(priority=1, category="skills", title=f"Review evidence for {match.requirement}",
                    reason="The requirement is missing or only partially demonstrated in the supplied CV.",
                    action=f"If you genuinely have experience with {match.requirement}, make that evidence clearer. Otherwise, treat it as a development goal; do not claim unsupported experience."))
        for section in checks.missing_sections:
            items.append(Recommendation(priority=2, category="structure", title=f"Review {section.replace('_', ' ')} section",
                reason="A recognizable heading was not detected.", action=SAFE_ACTIONS["structure"]))
        if not checks.has_email or not checks.has_phone:
            items.append(Recommendation(priority=2, category="structure", title="Review contact details",
                reason="Email or phone was not detected.", action="Include the contact details you want recruiters to use."))
        if semantic:
            for suggestion in semantic.recommendations:
                # Never surface an LLM-generated replacement bullet or unverified claim.
                # Its category can select a safe edit strategy; backend owns the action.
                if suggestion.category in SAFE_ACTIONS and suggestion.evidence:
                    items.append(Recommendation(priority=suggestion.priority, category=suggestion.category,
                        title=f"Review {suggestion.category} evidence", reason="Review how your existing CV evidence is described.",
                        action=SAFE_ACTIONS[suggestion.category]))
        if not items:
            items.append(Recommendation(priority=3, category="content", title="Review your evidence",
                reason="Concrete contributions make the CV easier to assess.", action=SAFE_ACTIONS["content"]))
        unique = {item.title: item for item in items}
        return sorted(unique.values(), key=lambda item: item.priority)[:10]
