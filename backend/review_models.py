"""Additive product contracts; existing analysis and scoring models stay unchanged."""
from typing import Literal

from pydantic import Field

from backend.models import CVAnalysisResult, Model, Recommendation, RequirementMatch, ScoringOutcome

EvidenceStrength = Literal["strong_evidence", "some_evidence", "mention_only"]


class SkillEvidence(Model):
    skill: str
    strength: EvidenceStrength
    evidence: list[str] = Field(default_factory=list)
    mention_evidence: list[str] = Field(default_factory=list)
    explanation: str


class ReviewStrength(Model):
    title: str
    explanation: str = ""
    evidence: list[str] = Field(default_factory=list)


class ImprovementArea(Model):
    issue: str
    why_it_matters: str
    recommended_action: str


class BulletReview(Model):
    id: str
    section: Literal["experience", "projects"]
    original: str
    issues: list[str] = Field(default_factory=list)
    how_to_improve: list[str] = Field(default_factory=list)


class BulletRewrite(Model):
    original: str
    rewrite: str
    notes: str
    requires_user_input: list[str] = Field(default_factory=list)


class RequirementGroups(Model):
    matched: list[RequirementMatch] = Field(default_factory=list)
    partial: list[RequirementMatch] = Field(default_factory=list)
    missing: list[RequirementMatch] = Field(default_factory=list)


class AnalyzerReview(Model):
    analysis: CVAnalysisResult
    cv_quality: ScoringOutcome
    target_role: str | None = None
    industry: str = "General / Auto"
    summary: str
    skill_evidence: list[SkillEvidence] = Field(default_factory=list)
    strengths: list[ReviewStrength] = Field(default_factory=list, max_length=5)
    improvement_areas: list[ImprovementArea] = Field(default_factory=list)
    bullet_reviews: list[BulletReview] = Field(default_factory=list)
    top_recommendations: list[Recommendation] = Field(default_factory=list, max_length=3)
    requirement_groups: RequirementGroups = Field(default_factory=RequirementGroups)
    display_warnings: list[str] = Field(default_factory=list)
