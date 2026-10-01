"""Application contracts. AI responses are deliberately separate from UI results."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Score = Annotated[int, Field(ge=0, le=100)]
MatchStatus = Literal["matched", "partial", "missing"]
RequirementCategory = Literal["hard_skill", "experience", "project", "education", "role", "other"]
Quality = Literal["unknown", "insufficient", "weak", "limited", "adequate", "strong", "exceptional"]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class CVDocument(Model):
    raw_text: str
    source_type: Literal["text", "txt", "pdf", "docx"] = "text"
    filename: str | None = None
    page_count: int | None = Field(default=None, ge=1)
    extraction_quality: Literal["good", "low"] | None = None


class CandidateProfile(Model):
    summary: str | None = None
    skills: list[str] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)
    experience: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    sections_detected: list[str] = Field(default_factory=list)


class BasicChecks(Model):
    has_email: bool
    has_phone: bool
    word_count: int = Field(ge=0)
    sections_detected: list[str] = Field(default_factory=list)
    missing_sections: list[str] = Field(default_factory=list)
    bullet_count: int = Field(ge=0)
    extraction_warning: str | None = None


class JDRequirement(Model):
    requirement: str = Field(min_length=1)
    category: RequirementCategory
    skill_name: str | None = None
    preferred: bool = False


class JobDescription(Model):
    raw_text: str
    job_title: str | None = None
    requirements: list[JDRequirement] = Field(default_factory=list)


class RequirementMatch(Model):
    requirement: str = Field(min_length=1)
    status: MatchStatus
    evidence: list[str] = Field(default_factory=list)
    explanation: str | None = None

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class Recommendation(Model):
    priority: int = Field(ge=1, le=10)
    category: str
    title: str
    reason: str
    action: str


class SemanticJudgment(Model):
    quality: Quality
    evidence: list[str] = Field(default_factory=list)


class AIRecommendation(Recommendation):
    evidence: list[str] = Field(default_factory=list)


class AISemanticAnalysis(Model):
    candidate_summary: str
    detected_skills: list[str]
    strengths: list[str]
    weaknesses: list[str]
    content_quality: SemanticJudgment
    experience_quality: SemanticJudgment
    project_quality: SemanticJudgment
    education_quality: SemanticJudgment
    skill_quality: SemanticJudgment
    role_relevance: SemanticJudgment | None = None
    experience_relevance: SemanticJudgment | None = None
    project_relevance: SemanticJudgment | None = None
    education_relevance: SemanticJudgment | None = None
    requirements: list[RequirementMatch] = Field(default_factory=list)
    recommendations: list[AIRecommendation] = Field(default_factory=list)


class ScoreBreakdown(Model):
    content: Score | None = None
    skills: Score | None = None
    experience: Score | None = None
    education: Score | None = None
    structure: Score | None = None
    job_match: Score | None = None
    projects: Score | None = None
    role: Score | None = None
    other_keywords: Score | None = None


class ScoringOutcome(Model):
    overall_score: Score
    scores: ScoreBreakdown
    components: dict[str, Score]
    effective_weights: dict[str, float]


class AnalysisMetadata(Model):
    model: str | None = None
    prompt_version: str | None = None
    scoring_version: str = "2.0"
    ai_available: bool
    analysis_mode: Literal["cv_only", "job_match"]
    scoring_components: dict[str, Score] = Field(default_factory=dict)
    effective_weights: dict[str, float] = Field(default_factory=dict)


class CVAnalysisResult(Model):
    mode: Literal["cv_only", "job_match"]
    overall_score: Score
    scores: ScoreBreakdown
    candidate_summary: str
    detected_skills: list[str]
    strengths: list[str]
    weaknesses: list[str]
    basic_checks: BasicChecks
    recommendations: list[Recommendation]
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    partially_matched_skills: list[str] = Field(default_factory=list)
    requirement_matches: list[RequirementMatch] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    ai_available: bool
    analysis_metadata: AnalysisMetadata | None = None
