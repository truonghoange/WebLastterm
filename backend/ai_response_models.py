"""Typed, tolerant wire models. Never expose these models to UI or scoring."""
from pydantic import BaseModel, ConfigDict, Field


class AIResponseModel(BaseModel):
    # Extra provider fields are discarded rather than entering application contracts.
    # Strict primitive types prevent a number/object from masquerading as text.
    model_config = ConfigDict(extra="ignore", strict=True)


class AIJudgmentResponse(AIResponseModel):
    quality: str | None = Field(default="unknown", description="exceptional, strong, adequate, limited, weak, insufficient; unknown when no evidence")
    evidence: list[str] | None = Field(default_factory=list, description="Exact quotations from the CV")


class AIRequirementResponse(AIResponseModel):
    requirement: str
    status: str | None = Field(default="unknown", description="matched, partial, or missing; uncertainty is missing")
    evidence: list[str] | None = Field(default_factory=list)
    explanation: str | None = None


class AIRecommendationResponse(AIResponseModel):
    priority: int | None = Field(default=3, description="Priority from 1 to 10")
    category: str
    title: str | None = None
    reason: str | None = None
    action: str | None = None
    evidence: list[str] | None = Field(default_factory=list)


class AISemanticResponse(AIResponseModel):
    candidate_summary: str
    detected_skills: list[str] | None = Field(default_factory=list)
    strengths: list[str] | None = Field(default_factory=list)
    weaknesses: list[str] | None = Field(default_factory=list)
    # The preferred wire shape is an object. Local validation also accepts a
    # bare rating from a provider; without evidence it cannot earn positive points.
    content_quality: AIJudgmentResponse | str | None = None
    experience_quality: AIJudgmentResponse | str | None = None
    project_quality: AIJudgmentResponse | str | None = None
    education_quality: AIJudgmentResponse | str | None = None
    skill_quality: AIJudgmentResponse | str | None = None
    role_relevance: AIJudgmentResponse | str | None = None
    experience_relevance: AIJudgmentResponse | str | None = None
    project_relevance: AIJudgmentResponse | str | None = None
    education_relevance: AIJudgmentResponse | str | None = None
    requirements: list[AIRequirementResponse] | None = Field(default_factory=list)
    recommendations: list[AIRecommendationResponse] | None = Field(default_factory=list)
