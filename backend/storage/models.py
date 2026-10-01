"""Typed workspace records and validated write contracts."""
from datetime import date, datetime
from enum import Enum
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from backend.models import Model, Score
from backend.review_models import AnalyzerReview

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class WorkspaceError(ValueError):
    """Safe message that can be shown in the workspace UI."""


class WorkspaceDataError(WorkspaceError):
    pass


class ApplicationStatus(str, Enum):
    saved = "saved"
    applied = "applied"
    interview = "interview"
    offer = "offer"
    rejected = "rejected"
    withdrawn = "withdrawn"


class CVWrite(Model):
    display_name: Name
    cv_text: Text
    filename: str | None = None
    target_role: str | None = None
    headline: str | None = None
    source_type: Literal["text", "txt", "pdf", "docx"] = "text"
    page_count: int | None = Field(default=None, ge=1)
    extraction_quality: Literal["good", "low"] | None = None


class SavedCV(CVWrite):
    id: int
    created_at: datetime
    updated_at: datetime
    last_analyzed_at: datetime | None = None
    latest_cv_score: Score | None = None


class JobWrite(Model):
    job_title: Name
    job_description: Text
    company: str = ""
    location: str = ""
    source_url: str = ""
    notes: str = ""


class SavedJob(JobWrite):
    id: int
    created_at: datetime
    updated_at: datetime


class ApplicationWrite(Model):
    job_id: int = Field(gt=0)
    cv_id: int = Field(gt=0)
    status: ApplicationStatus = ApplicationStatus.saved
    date_applied: date | None = None
    notes: str = ""


class SavedApplication(ApplicationWrite):
    id: int
    created_at: datetime
    updated_at: datetime


class AnalysisSnapshot(Model):
    id: int
    cv_id: int
    job_id: int | None = None
    mode: Literal["cv_only", "job_match"]
    cv_quality_score: Score
    job_match_score: Score | None = None
    review: AnalyzerReview
    created_at: datetime

    @model_validator(mode="after")
    def consistent_scores(self):
        expected_match = self.review.analysis.overall_score if self.mode == "job_match" else None
        if (self.mode != self.review.analysis.mode or self.cv_quality_score != self.review.cv_quality.overall_score
                or self.job_match_score != expected_match or (self.mode == "cv_only" and self.job_id is not None)):
            raise ValueError("Snapshot does not agree with its normalized review")
        return self


class InsightCount(Model):
    label: str
    count: int = Field(ge=0)


class WorkspaceInsights(Model):
    saved_cvs: int = 0
    saved_jobs: int = 0
    applications: int = 0
    active_applications: int = 0
    average_cv_quality: float | None = None
    average_job_match: float | None = None
    latest_cv_score: Score | None = None
    latest_job_match: Score | None = None
    missing_skills: list[InsightCount] = Field(default_factory=list)
    partial_skills: list[InsightCount] = Field(default_factory=list)
    requested_skills: list[InsightCount] = Field(default_factory=list)
    improvement_areas: list[InsightCount] = Field(default_factory=list)
    application_pipeline: dict[ApplicationStatus, int] = Field(default_factory=dict)
