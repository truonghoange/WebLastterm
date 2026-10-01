"""Conservative canonical names and evidence checks, shared by all stages."""
import re
import unicodedata

from constants import INDUSTRY_KEYWORDS, SKILL_SYNONYMS, SOFT_SKILLS
from processor import _contains_term
from backend.ai_response_models import AIJudgmentResponse, AISemanticResponse
from backend.exceptions import LLMResponseError
from backend.models import (AIRecommendation, AISemanticAnalysis, MatchStatus,
                            Quality, RequirementMatch, SemanticJudgment)

# Preserve database/tool distinctions that the legacy aliases collapse into SQL.
ALIASES = {k: v for k, v in SKILL_SYNONYMS.items()
           if k not in {"postgresql", "mysql", "sql server", "cfa candidate", "cfa level 1", "cfa level 2", "cfa level 3"}}
DISPLAY_NAMES = {"python": "Python", "sql": "SQL", "pandas": "Pandas", "numpy": "NumPy",
                 "excel": "Excel", "power bi": "Power BI", "postgresql": "PostgreSQL",
                 "mysql": "MySQL", "sql server": "SQL Server", "r": "R", "powerpoint": "PowerPoint",
                 "cpa": "CPA", "cfa": "CFA", "etl": "ETL", "seo": "SEO"}
DISPLAY_NAMES.update({"java": "Java", "javascript": "JavaScript", "typescript": "TypeScript",
                      "c++": "C++", "c#": "C#", "fastapi": "FastAPI", "react": "React"})
KNOWN_TERMS = set(ALIASES) | set(ALIASES.values()) | set(SOFT_SKILLS) | set(DISPLAY_NAMES)
KNOWN_TERMS.update(term for terms in INDUSTRY_KEYWORDS.values() for term in terms)


def normalize_skill(value: str) -> str:
    key = re.sub(r"\s+", " ", value.strip().lower()).rstrip(".,;:!?")
    key = ALIASES.get(key, key)
    return DISPLAY_NAMES.get(key, key)


def normalize_skills(values: list[str]) -> list[str]:
    return list(dict.fromkeys(normalize_skill(value) for value in values if value.strip()))


def skill_in_text(skill: str, text: str) -> bool:
    canonical = normalize_skill(skill)
    variants = [canonical] + [alias for alias in ALIASES if normalize_skill(alias) == canonical]
    return any(_contains_term(text, term) for term in variants)


def extract_known_skills(text: str) -> list[str]:
    return sorted(normalize_skills([term for term in KNOWN_TERMS if _contains_term(text, term)]))


def normalized_text(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip().casefold()


def valid_evidence(quotes: list[str], cv_text: str) -> list[str]:
    source = normalized_text(cv_text)
    return list(dict.fromkeys(quote.strip() for quote in quotes
                             if len(quote.strip()) >= 3 and normalized_text(quote) in source))


STATUS_ALIASES: dict[str, MatchStatus] = {
    "matched": "matched", "match": "matched", "fully_matched": "matched",
    "clearly_demonstrated": "matched",
    "partial": "partial", "partially_matched": "partial",
    "partially_demonstrated": "partial", "some_evidence": "partial",
    "missing": "missing", "not_found": "missing", "not_demonstrated": "missing",
    "no_evidence": "missing", "unknown": "missing", "not_mentioned": "missing",
}
QUALITY_ALIASES: dict[str, Quality] = {
    "unknown": "unknown", "not_assessed": "unknown", "not_mentioned": "unknown",
    "weak": "weak", "low": "weak",
    "insufficient": "insufficient", "limited": "limited", "adequate": "adequate",
    "moderate": "adequate", "medium": "adequate",
    "strong": "strong", "high": "strong",
    "exceptional": "exceptional",
}
QUALITY_FIELDS = ("content_quality", "experience_quality", "project_quality",
                  "education_quality", "skill_quality")
RELEVANCE_FIELDS = ("role_relevance", "experience_relevance", "project_relevance", "education_relevance")


def _label(value: str) -> str:
    return re.sub(r"[\s-]+", "_", value.strip().casefold())


def normalize_requirement_status(value: str | None) -> MatchStatus:
    if value is None:
        return "missing"
    status = STATUS_ALIASES.get(_label(value))
    if status is None:
        # Unknown vocabulary is not a positive match and not silently guessed.
        raise LLMResponseError("AI returned an unrecognized requirement status.")
    return status


def normalize_quality(value: str | None) -> Quality:
    if value is None:
        return "unknown"
    quality = QUALITY_ALIASES.get(_label(value))
    if quality is None:
        raise LLMResponseError("AI returned an unrecognized semantic quality.")
    return quality


def normalize_ai_list(values: list[str] | None) -> list[str]:
    """Null/missing lists become empty; primitive validation happens in wire models."""
    return list(dict.fromkeys(value.strip() for value in values or [] if value.strip()))


def normalize_judgment(value: AIJudgmentResponse | str | None) -> SemanticJudgment:
    if isinstance(value, AIJudgmentResponse):
        return SemanticJudgment(quality=normalize_quality(value.quality),
                                evidence=normalize_ai_list(value.evidence))
    return SemanticJudgment(quality=normalize_quality(value), evidence=[])


def normalize_ai_response(response: AISemanticResponse, *, job_match: bool) -> AISemanticAnalysis:
    """Convert validated wire data into strict, freshly validated application models."""
    if not response.candidate_summary.strip():
        raise LLMResponseError("AI returned an empty candidate summary.")
    if not any(getattr(response, name) is not None for name in QUALITY_FIELDS) and not (job_match and response.requirements):
        raise LLMResponseError("AI returned no semantic analysis signals.")
    requirements = [RequirementMatch(
        requirement=item.requirement.strip(), status=normalize_requirement_status(item.status),
        evidence=normalize_ai_list(item.evidence), explanation=item.explanation,
    ) for item in response.requirements or []] if job_match else []
    recommendations = [AIRecommendation(
        priority=max(1, min(10, item.priority if item.priority is not None else 3)),
        category=item.category.strip().casefold(), title=item.title or "Review existing CV evidence",
        reason=item.reason or "Review how your existing CV evidence is described.",
        action=item.action or "Clarify only evidence that reflects your actual background.",
        evidence=normalize_ai_list(item.evidence),
    ) for item in response.recommendations or []]
    return AISemanticAnalysis(
        candidate_summary=response.candidate_summary.strip(),
        detected_skills=normalize_skills(normalize_ai_list(response.detected_skills)),
        strengths=normalize_ai_list(response.strengths), weaknesses=normalize_ai_list(response.weaknesses),
        **{name: normalize_judgment(getattr(response, name)) for name in QUALITY_FIELDS},
        **{name: normalize_judgment(getattr(response, name))
           if job_match and getattr(response, name) is not None else None for name in RELEVANCE_FIELDS},
        requirements=requirements, recommendations=recommendations,
    )
