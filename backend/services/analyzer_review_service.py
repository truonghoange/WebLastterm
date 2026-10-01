"""Product review built around the unchanged analysis pipeline, with one AI request."""
import re

from backend.config import QUALITY_POINTS
from backend.exceptions import InvalidCVError
from backend.models import AISemanticAnalysis, CVDocument, Recommendation
from backend.normalization import normalized_text, skill_in_text, valid_evidence
from backend.parsers.cv_parser import extract_sections
from backend.parsers.jd_parser import JDParser
from backend.review_models import (AnalyzerReview, ImprovementArea, RequirementGroups,
                                   ReviewStrength, SkillEvidence)
from backend.services.analysis_service import AnalysisService, SAFE_ACTIONS
from backend.services.bullet_review_service import ACTION, review_bullets, section_bullets
from backend.services.scoring_service import ScoringService
from processor import _match_section_heading


class _ScoringCapture:
    """Capture already-grounded semantic evidence at the existing injection point."""
    def __init__(self, scorer):
        self.scorer = scorer
        self.semantic = None
        self.profile = None
        self.cv_quality = None

    def score(self, profile, checks, semantic=None, jd=None, matches=None):
        self.profile, self.semantic = profile, semantic
        outcome = self.scorer.score(profile, checks, semantic, jd, matches)
        self.cv_quality = outcome if jd is None else self.scorer.score(profile, checks, semantic)
        return outcome


def classify_skills(document: CVDocument, skills: list[str], semantic: AISemanticAnalysis | None = None) -> list[SkillEvidence]:
    sections = extract_sections(document.raw_text)
    bullets = section_bullets(document)
    # Only verified quotes already present in the single semantic response are reused.
    semantic_quotes = []
    if semantic:
        for name in ("skill_quality", "experience_quality", "project_quality"):
            semantic_quotes.extend(valid_evidence(getattr(semantic, name).evidence, document.raw_text))
    result = []
    for skill in skills:
        support = []
        for _, quote in bullets:
            if skill_in_text(skill, quote) and ACTION.search(quote):
                support.append(quote)
        # An implementation may be described in unbulleted project/work text.
        for name in ("experience", "projects"):
            for quote in sections.get(name, "").splitlines():
                quote = re.sub(r"^\s*[-•●*]\s*", "", quote).strip()
                if skill_in_text(skill, quote) and ACTION.search(quote):
                    support.append(quote)
        for quote in semantic_quotes:
            if (skill_in_text(skill, quote) and ACTION.search(quote)
                    and any(normalized_text(quote) in normalized_text(sections.get(name, ""))
                            for name in ("experience", "projects"))):
                support.append(quote)
        support = valid_evidence(support, document.raw_text)
        # Avoid counting the same wrapped bullet, substring or duplicated sentence twice.
        unique = []
        for quote in sorted(support, key=len, reverse=True):
            if not any(normalized_text(quote) in normalized_text(existing) for existing in unique):
                unique.append(quote)
        mentions = valid_evidence([line.strip() for line in document.raw_text.splitlines()
                                  if skill_in_text(skill, line)], document.raw_text)
        strength = "strong_evidence" if len(unique) >= 2 else "some_evidence" if unique else "mention_only"
        explanation = ("Used in multiple distinct project or work descriptions." if len(unique) >= 2
                       else "Demonstrated in a project or work description; add further detail if available." if unique
                       else "Mentioned in the CV. No concrete project/work evidence was found.")
        result.append(SkillEvidence(skill=skill, strength=strength, evidence=unique,
                                    mention_evidence=mentions, explanation=explanation))
    return result


def friendly_warnings(result):
    warnings = []
    for text in result.warnings:
        if "AI judgments lacked" in text or "requirement matches lacked" in text:
            message = "Some suggestions were excluded because the supporting CV evidence could not be verified."
        elif text.startswith("AI ") or "AI provider" in text or "AI model" in text or "AI response" in text:
            message = "Full analysis is unavailable right now. Basic document checks and text evidence are still available."
        elif "Deterministic fallback" in text:
            message = "This basic review checks the text provided; deeper relevance and skill proficiency have not been assessed."
        else:
            message = text
        if message not in warnings:
            warnings.append(message)
    return warnings


def _headline(document, profile):
    for line in document.raw_text.splitlines():
        text = line.strip()
        if _match_section_heading(text) or text.lower().rstrip(":") in {"summary", "profile", "objective"}:
            break
        if (len(text) <= 100 and "@" not in text and "http" not in text.lower()
                and text.casefold() not in {"student name", "candidate name"}
                and re.search(r"\b(student|graduate|intern|analyst|engineer|developer|designer|consultant|specialist)\b", text, re.I)):
            return text
    if profile.summary:
        return re.split(r"(?<=[.!?])\s+|\n", profile.summary)[0][:120]
    return None


def _strengths(result, semantic):
    items, used_fields = [], set()
    for text in result.strengths[:5]:
        evidence = []
        if semantic:
            for pattern, field in ((r"project", "project_quality"), (r"education|academic|coursework", "education_quality"),
                                   (r"skill|technical|programming|tool", "skill_quality"),
                                   (r"experience|internship", "experience_quality"), (r"content|clarity|contribution", "content_quality")):
                judgment = getattr(semantic, field)
                if re.search(pattern, text, re.I) and QUALITY_POINTS[judgment.quality] >= QUALITY_POINTS["adequate"] and judgment.evidence:
                    evidence = judgment.evidence[:2]
                    used_fields.add(field)
                    break
        items.append(ReviewStrength(title=text if len(text) <= 85 else text[:82] + "…",
            explanation=text if len(text) > 85 else "Supported by the following CV details." if evidence else "",
            evidence=evidence))
    if semantic:
        for field, title in (("project_quality", "Concrete project evidence"), ("skill_quality", "Demonstrated technical skills"),
                             ("education_quality", "Academic foundation"), ("content_quality", "Clear contribution evidence")):
            judgment = getattr(semantic, field)
            if field not in used_fields and QUALITY_POINTS[judgment.quality] >= QUALITY_POINTS["adequate"] and judgment.evidence and len(items) < 5:
                items.append(ReviewStrength(title=title, explanation="Supported by the following details in your CV.",
                                            evidence=judgment.evidence[:2]))
    return items[:5]


def _area(issue):
    lower = issue.casefold()
    if "bullet" in lower or "outcome" in lower or "impact" in lower:
        category = "content"
        why = "Concrete actions and outcomes make your contribution easier to assess."
    elif "experience" in lower or "duration" in lower:
        category = "experience"
        why = "Work and internship evidence helps readers understand your contribution and experience level."
    elif "skill" in lower:
        category = "skills"
        why = "Examples of practical use are more informative than a list of tools."
    elif "education" in lower or "degree" in lower:
        category = "education"
        why = "Clear study status and relevant coursework help readers assess your academic foundation."
    elif "section" in lower or "contact" in lower:
        category = "structure"
        why = "Clear headings and contact information help readers find key details."
    else:
        category = "content"
        why = "Concrete actions and outcomes make your contribution easier to assess."
    return ImprovementArea(issue=issue, why_it_matters=why, recommended_action=SAFE_ACTIONS[category])


class AnalyzerReviewService:
    def __init__(self, *, settings=None, provider=None, scoring_service=None):
        self.capture = _ScoringCapture(scoring_service or ScoringService())
        self.analysis_service = AnalysisService(settings=settings, provider=provider, scoring_service=self.capture)

    def close(self):
        self.analysis_service.close()

    def analyze_cv(self, cv_document: CVDocument, jd_text: str | None = None,
                   target_position: str | None = None, industry: str | None = None) -> AnalyzerReview:
        if not isinstance(cv_document, CVDocument):
            raise InvalidCVError("Supply a readable CV document before analyzing.")
        if len(cv_document.raw_text.split()) < 20:
            raise InvalidCVError("Your CV is too short. Add at least 20 words of CV content before analyzing.")
        jd_text = jd_text.strip() if jd_text else None
        if jd_text and (len(re.findall(r"\b\w+\b", jd_text)) < 3 or not JDParser().parse(jd_text).requirements):
            raise InvalidCVError("The Job Description is too short or has no usable requirements. Add more detail or leave it blank for CV Review.")
        industry = industry.strip() if industry else "General / Auto"
        target_position = target_position.strip() if target_position else None
        # Industry is presentation context in CV Review, never a quality-rating bias.
        analysis_industry = None if jd_text is None or industry == "General / Auto" else industry
        result = self.analysis_service.analyze_cv(cv_document, jd_text, target_position, analysis_industry)
        skills = classify_skills(cv_document, result.detected_skills, self.capture.semantic)
        bullets = review_bullets(cv_document)
        areas = [_area(text) for text in result.weaknesses]
        if not self.capture.profile.experience and not any("experience" in item.issue.casefold() for item in areas):
            areas.append(_area("No professional work or internship evidence was found."))
        mentions = [item.skill for item in skills if item.strength == "mention_only"]
        if mentions:
            areas.append(_area("Some skills are mentioned without project/work evidence: " + ", ".join(mentions[:8])))
        if any(any("outcome" in issue for issue in item.issues) for item in bullets):
            areas.append(_area("Some project or experience bullets do not clearly describe their output or outcome."))
        recommendations = list(result.recommendations)
        if mentions:
            recommendations.append(Recommendation(priority=2, category="skills", title="Demonstrate listed skills",
                reason="Some tools are listed without a concrete example of use.",
                action="If you have used these tools, connect them to truthful project or work examples. Remove a skill only if it does not reflect your background."))
        if any(item.issues for item in bullets):
            recommendations.append(Recommendation(priority=2, category="projects", title="Clarify project contributions and outcomes",
                reason="Some bullets need clearer action, context or output.",
                action="Explain your actual contribution and output. Add dataset size or measured results only if you know them."))
        # Specific product actions precede the generic default 'Review your evidence'.
        recommendations.sort(key=lambda item: (item.priority, item.title == "Review your evidence"))
        unique = {item.title: item for item in recommendations}
        groups = RequirementGroups(**{status: [match for match in result.requirement_matches if match.status == status]
                                      for status in ("matched", "partial", "missing")})
        target = target_position or (JDParser().parse(jd_text).job_title if jd_text else _headline(cv_document, self.capture.profile))
        sentences = re.split(r"(?<=[.!?])\s+|\n", result.candidate_summary.strip())
        # A tool inventory belongs in Skills evidence rather than the summary.
        non_inventory = [sentence for sentence in sentences
                         if sum(skill_in_text(skill, sentence) for skill in result.detected_skills) < 5]
        if non_inventory:
            sentences = non_inventory
        elif result.strengths:
            sentences = [text.rstrip(".") + "." for text in result.strengths[:2]]
        summary = " ".join(sentences[:3])
        if len(summary) > 420:
            summary = summary[:417].rsplit(" ", 1)[0] + "…"
        return AnalyzerReview(analysis=result, cv_quality=self.capture.cv_quality, target_role=target,
            industry=industry, summary=summary, skill_evidence=skills, strengths=_strengths(result, self.capture.semantic),
            improvement_areas=areas, bullet_reviews=bullets, top_recommendations=list(unique.values())[:3],
            requirement_groups=groups, display_warnings=friendly_warnings(result))
