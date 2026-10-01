"""Career workspace orchestration; browsing never constructs an AI service."""
from collections import Counter
from datetime import date
from pathlib import Path
import logging
from typing import Callable

from backend.models import CVDocument
from backend.normalization import normalize_skill
from backend.parsers.jd_parser import JDParser
from backend.review_models import AnalyzerReview
from backend.services.analyzer_review_service import AnalyzerReviewService
from backend.storage import initialize_database
from backend.storage.analysis_repository import AnalysisRepository
from backend.storage.application_repository import ApplicationRepository
from backend.storage.cv_repository import CVRepository
from backend.storage.job_repository import JobRepository
from backend.storage.models import (ApplicationStatus, ApplicationWrite, CVWrite, InsightCount,
    JobWrite, WorkspaceError, WorkspaceInsights)

logger = logging.getLogger(__name__)


class WorkspaceService:
    def __init__(self, database_path: str | Path | None = None,
                 review_service_factory: Callable[[], AnalyzerReviewService] | None = None):
        self.database = initialize_database(database_path)
        self.cvs = CVRepository(self.database)
        self.jobs = JobRepository(self.database)
        self.applications = ApplicationRepository(self.database)
        self.analyses = AnalysisRepository(self.database)
        # Lazy: initialize a provider only for an explicit analysis action.
        self.review_service_factory = review_service_factory or AnalyzerReviewService

    def save_cv(self, data: CVWrite):
        return self.cvs.create(data)

    def update_cv(self, cv_id: int, data: CVWrite):
        return self.cvs.update(cv_id, data)

    def rename_cv(self, cv_id: int, display_name: str):
        cv = self.get_cv(cv_id)
        data = CVWrite.model_validate({**cv.model_dump(include=set(CVWrite.model_fields)), "display_name": display_name})
        return self.update_cv(cv_id, data)

    def get_cv(self, cv_id: int):
        cv = self.cvs.get_by_id(cv_id)
        if cv is None:
            raise WorkspaceError("This CV no longer exists.")
        return cv

    def list_cvs(self):
        return self.cvs.list_all()

    def delete_cv(self, cv_id: int):
        self.cvs.delete(cv_id)

    def save_job(self, data: JobWrite):
        return self.jobs.create(data)

    def update_job(self, job_id: int, data: JobWrite):
        return self.jobs.update(job_id, data)

    def get_job(self, job_id: int):
        job = self.jobs.get_by_id(job_id)
        if job is None:
            raise WorkspaceError("This job no longer exists.")
        return job

    def list_jobs(self):
        return self.jobs.list_all()

    def delete_job(self, job_id: int):
        with self.database.transaction() as connection:
            cv_ids = self.analyses.cv_ids_for_job(job_id, connection=connection)
            self.jobs.delete(job_id, connection=connection)
            for cv_id in cv_ids:
                self.cvs.refresh_analysis_metadata(cv_id, connection=connection)

    def save_analysis(self, cv_id: int, review: AnalyzerReview, job_id: int | None = None):
        with self.database.transaction() as connection:
            snapshot = self.analyses.create(cv_id, review, job_id, connection=connection)
            self.cvs.mark_analyzed(cv_id, snapshot.cv_quality_score, snapshot.created_at.isoformat(), connection=connection)
            return snapshot

    def save_analyzer_review(self, document: CVDocument, review: AnalyzerReview, display_name: str,
                             cv_id: int | None = None, job_id: int | None = None):
        data = CVWrite(display_name=display_name, cv_text=document.raw_text, filename=document.filename,
            source_type=document.source_type, page_count=document.page_count, extraction_quality=document.extraction_quality,
            target_role=review.target_role, headline=review.target_role)
        with self.database.transaction() as connection:
            cv = self.cvs.create(data, connection=connection) if cv_id is None else self.cvs.update(cv_id, data, connection=connection)
            snapshot = self.save_analysis_in_transaction(cv.id, review, job_id, connection)
            return self.cvs.get_by_id(cv.id, connection=connection), snapshot

    def save_analysis_in_transaction(self, cv_id, review, job_id, connection):
        snapshot = self.analyses.create(cv_id, review, job_id, connection=connection)
        self.cvs.mark_analyzed(cv_id, snapshot.cv_quality_score, snapshot.created_at.isoformat(), connection=connection)
        return snapshot

    def get_analysis(self, analysis_id: int):
        snapshot = self.analyses.get_by_id(analysis_id)
        if snapshot is None:
            raise WorkspaceError("This saved analysis no longer exists.")
        return snapshot

    def analysis_history(self, cv_id: int):
        return self.analyses.list_for_cv(cv_id)

    def latest_cv_analysis(self, cv_id: int):
        return self.analyses.latest_for_cv(cv_id)

    def latest_job_analysis(self, cv_id: int, job_id: int):
        return self.analyses.latest_for_pair(cv_id, job_id)

    def job_comparisons(self, job_id: int):
        return self.analyses.latest_per_pair(job_id)

    def pair_history(self, cv_id: int, job_id: int, limit: int = 50):
        return self.analyses.list_for_pair(cv_id, job_id, limit)

    @staticmethod
    def cv_document(cv):
        return CVDocument(raw_text=cv.cv_text, source_type=cv.source_type, filename=cv.filename,
                          page_count=cv.page_count, extraction_quality=cv.extraction_quality)

    def _run_analysis(self, cv, job=None):
        service = self.review_service_factory()
        try:
            review = service.analyze_cv(self.cv_document(cv), jd_text=job.job_description if job else None,
                target_position=job.job_title if job else cv.target_role)
        finally:
            try:
                service.close()
            except Exception as error:
                logger.warning("Workspace analysis cleanup failed (type=%s)", type(error).__name__)
        return self.save_analysis(cv.id, review, job.id if job else None)

    def analyze_saved_cv(self, cv_id: int):
        return self._run_analysis(self.get_cv(cv_id))

    def compare_cv_to_job(self, cv_id: int, job_id: int):
        return self._run_analysis(self.get_cv(cv_id), self.get_job(job_id))

    def create_application(self, data: ApplicationWrite):
        return self.applications.create(data)

    def get_application(self, application_id: int):
        application = self.applications.get_by_id(application_id)
        if application is None:
            raise WorkspaceError("This application no longer exists.")
        return application

    def list_applications(self):
        return self.applications.list_all()

    def update_application_status(self, application_id: int, status: ApplicationStatus,
                                  date_applied: date | None = None, notes: str | None = None):
        existing = self.get_application(application_id)
        return self.applications.update(application_id, status, date_applied if date_applied is not None else existing.date_applied,
                                        existing.notes if notes is None else notes)

    def update_application(self, application_id: int, status: ApplicationStatus, date_applied: date | None, notes: str):
        return self.applications.update(application_id, status, date_applied, notes)

    def delete_application(self, application_id: int):
        self.applications.delete(application_id)

    def get_workspace_insights(self) -> WorkspaceInsights:
        cvs, jobs, applications = self.list_cvs(), self.list_jobs(), self.list_applications()
        latest_cv = self.analyses.latest_per_cv()
        latest_pair = self.analyses.latest_per_pair()
        pipeline = {status: sum(app.status == status for app in applications) for status in ApplicationStatus}
        # Count distinct jobs, so several CVs compared with one job cannot inflate skill counts.
        missing_by_job, partial_by_job = {}, {}
        for snapshot in latest_pair:
            result = snapshot.review.analysis
            missing_by_job.setdefault(snapshot.job_id, set()).update(normalize_skill(skill) for skill in result.missing_skills)
            partial_by_job.setdefault(snapshot.job_id, set()).update(normalize_skill(skill) for skill in result.partially_matched_skills)
        requested = Counter()
        for job in jobs:
            requested.update({normalize_skill(req.skill_name) for req in JDParser().parse(job.job_description).requirements if req.skill_name})
        missing = Counter(skill for skills in missing_by_job.values() for skill in skills)
        partial = Counter(skill for skills in partial_by_job.values() for skill in skills)
        improvements, labels = Counter(), {}
        for snapshot in latest_cv:
            seen = set()
            for area in snapshot.review.improvement_areas:
                key = " ".join(area.issue.casefold().split())
                if key not in seen:
                    improvements[key] += 1
                    labels.setdefault(key, area.issue)
                    seen.add(key)

        def counts(counter, names=None):
            return [InsightCount(label=names[key] if names else key, count=count)
                    for key, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:10]]

        return WorkspaceInsights(saved_cvs=len(cvs), saved_jobs=len(jobs), applications=len(applications),
            active_applications=sum(app.status not in {ApplicationStatus.rejected, ApplicationStatus.withdrawn} for app in applications),
            average_cv_quality=round(sum(item.cv_quality_score for item in latest_cv) / len(latest_cv), 1) if latest_cv else None,
            average_job_match=round(sum(item.job_match_score for item in latest_pair) / len(latest_pair), 1) if latest_pair else None,
            latest_cv_score=latest_cv[0].cv_quality_score if latest_cv else None,
            latest_job_match=latest_pair[0].job_match_score if latest_pair else None,
            missing_skills=counts(missing), partial_skills=counts(partial), requested_skills=counts(requested),
            improvement_areas=counts(improvements, labels), application_pipeline=pipeline)
