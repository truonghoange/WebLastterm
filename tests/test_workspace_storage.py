from datetime import date
import sqlite3
from unittest.mock import patch

from pydantic import ValidationError
import pytest

from backend.config import Settings
from backend.review_models import ImprovementArea
from backend.services.analyzer_review_service import AnalyzerReviewService
from backend.services.workspace_service import WorkspaceService
from backend.storage import initialize_database
from backend.storage.database import PROJECT_ROOT, configured_database_path
from backend.storage.models import (ApplicationStatus, ApplicationWrite, CVWrite, JobWrite,
    WorkspaceDataError, WorkspaceError)
from tests.helpers import CV, JD, MockProvider, document, semantic_payload


@pytest.fixture
def workspace(tmp_path):
    return WorkspaceService(tmp_path / "nested" / "workspace.db")


@pytest.fixture
def cv(workspace):
    return workspace.save_cv(CVWrite(display_name="Data CV", cv_text=CV, target_role="Data Intern"))


@pytest.fixture
def job(workspace):
    return workspace.save_job(JobWrite(job_title="Data Analyst", job_description=JD, company="Example"))


@pytest.fixture
def review():
    return AnalyzerReviewService(settings=Settings(), provider=MockProvider(semantic_payload(None))).analyze_cv(document())


@pytest.fixture
def match_review():
    return AnalyzerReviewService(settings=Settings(), provider=MockProvider()).analyze_cv(document(), JD)


def test_database_initialization_is_explicit_idempotent_and_preserves_data(workspace, cv):
    initialize_database(workspace.database.path)
    assert workspace.get_cv(cv.id) == cv
    with workspace.database.transaction() as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert tables == {"cvs", "jobs", "applications", "analyses"}
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        indexes = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        assert {"idx_analysis_cv", "idx_analysis_job", "idx_application_status"} <= indexes


def test_configured_path_environment_and_project_relative(monkeypatch):
    monkeypatch.setenv("CVISION_DB_PATH", "data/example.db")
    assert configured_database_path() == PROJECT_ROOT / "data/example.db"


def test_default_path_and_dotenv_are_supported(monkeypatch):
    monkeypatch.delenv("CVISION_DB_PATH")
    with patch("backend.storage.database.dotenv_values", return_value={}):
        assert configured_database_path() == PROJECT_ROOT / "data/cvision.db"
    with patch("backend.storage.database.dotenv_values", return_value={"CVISION_DB_PATH": "data/custom.db"}):
        assert configured_database_path() == PROJECT_ROOT / "data/custom.db"


def test_cv_create_read_list_update_delete(workspace, cv):
    assert workspace.get_cv(cv.id).cv_text == CV.strip()
    assert workspace.list_cvs() == [cv]
    changed = workspace.update_cv(cv.id, CVWrite(display_name="Renamed", cv_text=CV + "More projects"))
    assert changed.display_name == "Renamed"
    assert changed.created_at == cv.created_at
    assert changed.updated_at >= cv.updated_at
    workspace.delete_cv(cv.id)
    assert workspace.list_cvs() == []
    with pytest.raises(WorkspaceError, match="no longer exists"):
        workspace.get_cv(cv.id)


def test_cv_rename_does_not_change_source_or_text(workspace, cv):
    renamed = workspace.rename_cv(cv.id, "  New name  ")
    assert renamed.display_name == "New name"
    assert renamed.cv_text == cv.cv_text
    assert renamed.target_role == cv.target_role


def test_job_create_read_update_delete(workspace, job):
    assert workspace.get_job(job.id) == job
    assert workspace.list_jobs() == [job]
    data = JobWrite(job_title="Junior Analyst", job_description=JD, notes="Follow up", source_url="https://example.test/job")
    changed = workspace.update_job(job.id, data)
    assert changed.notes == "Follow up"
    assert changed.created_at == job.created_at
    workspace.delete_job(job.id)
    assert workspace.list_jobs() == []


@pytest.mark.parametrize("model,values", [(CVWrite, {"display_name": " ", "cv_text": CV}),
    (CVWrite, {"display_name": "CV", "cv_text": " "}),
    (JobWrite, {"job_title": " ", "job_description": JD}),
    (JobWrite, {"job_title": "Job", "job_description": " "})])
def test_required_fields_reject_blank(model, values):
    with pytest.raises(ValidationError):
        model(**values)


def test_application_create_duplicate_protection_and_update(workspace, cv, job):
    application = workspace.create_application(ApplicationWrite(cv_id=cv.id, job_id=job.id))
    assert application.status == ApplicationStatus.saved
    assert workspace.get_application(application.id) == application
    with pytest.raises(WorkspaceError, match="Application already exists"):
        workspace.create_application(ApplicationWrite(cv_id=cv.id, job_id=job.id))
    changed = workspace.update_application_status(application.id, ApplicationStatus.applied, date(2026, 10, 1), "Submitted")
    assert changed.date_applied == date(2026, 10, 1)
    assert changed.notes == "Submitted"
    assert changed.created_at == application.created_at
    changed = workspace.update_application_status(application.id, ApplicationStatus.interview, changed.date_applied)
    assert changed.status == ApplicationStatus.interview
    assert changed.notes == "Submitted"
    workspace.delete_application(application.id)
    assert workspace.list_applications() == []


def test_application_invalid_status_rejected_at_model_repository_and_database(workspace, cv, job):
    with pytest.raises(ValidationError):
        ApplicationWrite(cv_id=cv.id, job_id=job.id, status="hired maybe")
    application = workspace.create_application(ApplicationWrite(cv_id=cv.id, job_id=job.id))
    with pytest.raises(WorkspaceError, match="valid application status"):
        workspace.update_application_status(application.id, "hired maybe")
    with pytest.raises(sqlite3.IntegrityError), workspace.database.transaction() as db:
        db.execute("UPDATE applications SET status=? WHERE id=?", ("random", application.id))
    assert workspace.get_application(application.id).status == ApplicationStatus.saved


def test_application_references_must_exist(workspace, cv):
    with pytest.raises(WorkspaceError, match="existing saved CV and job"):
        workspace.create_application(ApplicationWrite(cv_id=cv.id, job_id=999))


def test_analysis_snapshot_validated_round_trip_and_cached_cv_score(workspace, cv, review):
    snapshot = workspace.save_analysis(cv.id, review)
    loaded = workspace.get_analysis(snapshot.id)
    assert loaded.review == review
    assert loaded.cv_quality_score == 83
    assert loaded.job_match_score is None
    saved = workspace.get_cv(cv.id)
    assert saved.latest_cv_score == 83
    assert saved.last_analyzed_at == snapshot.created_at
    with workspace.database.transaction() as db:
        raw = db.execute("SELECT analysis_json FROM analyses").fetchone()[0]
        assert "candidate_summary" in raw
        assert '"raw_text"' not in raw
        assert '"prompt"' not in raw
        assert '"raw_response"' not in raw


def test_analysis_history_and_latest_cv_and_pair(workspace, cv, job, review, match_review):
    first = workspace.save_analysis(cv.id, review)
    second = workspace.save_analysis(cv.id, match_review, job.id)
    third = workspace.save_analysis(cv.id, match_review, job.id)
    assert [s.id for s in workspace.analysis_history(cv.id)] == [third.id, second.id, first.id]
    assert workspace.latest_cv_analysis(cv.id).id == third.id
    assert workspace.latest_job_analysis(cv.id, job.id).id == third.id
    assert [s.id for s in workspace.pair_history(cv.id, job.id)] == [third.id, second.id]
    assert workspace.job_comparisons(job.id)[0].id == third.id


def test_snapshot_cv_only_cannot_be_attached_to_job(workspace, cv, job, review):
    with pytest.raises(WorkspaceError):
        workspace.save_analysis(cv.id, review, job.id)
    assert workspace.analysis_history(cv.id) == []
    assert workspace.get_cv(cv.id).latest_cv_score is None


def test_save_new_and_update_saved_cv_preserves_identity_and_history(workspace, review):
    cv, first = workspace.save_analyzer_review(document(), review, "My CV")
    changed, second = workspace.save_analyzer_review(document(), review, "My updated CV", cv.id)
    assert cv.id == changed.id
    assert len(workspace.list_cvs()) == 1
    assert [s.id for s in workspace.analysis_history(cv.id)] == [second.id, first.id]


def test_save_cv_and_snapshot_is_atomic(workspace, review):
    with patch.object(workspace.cvs, "mark_analyzed", side_effect=RuntimeError("fail")):
        with pytest.raises(RuntimeError):
            workspace.save_analyzer_review(document(), review, "Atomic CV")
    assert workspace.list_cvs() == []
    assert workspace.analyses.latest_per_cv() == []


def test_corrupt_json_or_inconsistent_saved_score_is_rejected_safely(workspace, cv, review):
    snapshot = workspace.save_analysis(cv.id, review)
    with workspace.database.transaction() as db:
        db.execute("UPDATE analyses SET analysis_json=? WHERE id=?", ('{"private":"secret"}', snapshot.id))
    with pytest.raises(WorkspaceDataError) as error:
        workspace.get_analysis(snapshot.id)
    assert "secret" not in str(error.value)
    with workspace.database.transaction() as db:
        db.execute("UPDATE analyses SET analysis_json=?,cv_quality_score=1 WHERE id=?", (review.model_dump_json(), snapshot.id))
    with pytest.raises(WorkspaceDataError):
        workspace.get_analysis(snapshot.id)


@pytest.mark.parametrize("entity", ["cv", "job"])
def test_delete_blocked_by_application_then_controlled_analysis_cascade(workspace, cv, job, review, match_review, entity):
    other_cv = workspace.save_cv(CVWrite(display_name="Other CV", cv_text=CV))
    other_job = workspace.save_job(JobWrite(job_title="Other Job", job_description=JD))
    unrelated = workspace.save_analysis(other_cv.id, match_review, other_job.id)
    workspace.save_analysis(cv.id, review)
    pair = workspace.save_analysis(cv.id, match_review, job.id)
    application = workspace.create_application(ApplicationWrite(cv_id=cv.id, job_id=job.id))
    delete = workspace.delete_cv if entity == "cv" else workspace.delete_job
    record_id = cv.id if entity == "cv" else job.id
    with pytest.raises(WorkspaceError, match="used in applications"):
        delete(record_id)
    assert workspace.get_analysis(pair.id)
    workspace.delete_application(application.id)
    delete(record_id)
    assert workspace.get_analysis(unrelated.id)
    assert workspace.get_cv(other_cv.id)
    assert workspace.get_job(other_job.id)
    with pytest.raises(WorkspaceError):
        workspace.get_analysis(pair.id)
    if entity == "job":
        assert len(workspace.analysis_history(cv.id)) == 1
        remaining = workspace.latest_cv_analysis(cv.id)
        assert workspace.get_cv(cv.id).last_analyzed_at == remaining.created_at
    else:
        assert workspace.get_job(job.id)


def test_empty_workspace_data_does_not_call_gemini(workspace):
    with patch("backend.services.workspace_service.AnalyzerReviewService", side_effect=AssertionError("must not construct")):
        assert workspace.list_cvs() == []
        assert workspace.list_jobs() == []
        assert workspace.list_applications() == []
        insights = workspace.get_workspace_insights()
        assert insights.saved_cvs == insights.saved_jobs == insights.active_applications == 0
        assert insights.average_cv_quality is insights.average_job_match is None
        assert insights.missing_skills == insights.partial_skills == []
        assert all(count == 0 for count in insights.application_pipeline.values())


def test_browsing_existing_workspace_never_constructs_ai(workspace, cv, job, match_review):
    snapshot = workspace.save_analysis(cv.id, match_review, job.id)
    application = workspace.create_application(ApplicationWrite(cv_id=cv.id, job_id=job.id))
    with patch("backend.services.workspace_service.AnalyzerReviewService", side_effect=AssertionError("AI on browse")):
        fresh = WorkspaceService(workspace.database.path)
        assert fresh.get_cv(cv.id) == workspace.get_cv(cv.id)
        assert fresh.get_job(job.id) == job
        assert fresh.get_application(application.id) == application
        assert fresh.get_analysis(snapshot.id) == snapshot
        fresh.analysis_history(cv.id)
        fresh.job_comparisons(job.id)
        fresh.get_workspace_insights()


def test_explicit_compare_and_reanalysis_reuse_existing_pipeline_once_and_save(workspace, cv, job):
    provider = MockProvider()
    workspace.review_service_factory = lambda: AnalyzerReviewService(settings=Settings(), provider=provider)
    snapshot = workspace.compare_cv_to_job(cv.id, job.id)
    assert len(provider.calls) == 1
    assert snapshot.review.cv_quality.overall_score == 83
    assert snapshot.job_match_score == 63
    provider.payload = semantic_payload(None)
    second = workspace.analyze_saved_cv(cv.id)
    assert len(provider.calls) == 2
    assert second.mode == "cv_only"
    assert len(workspace.analysis_history(cv.id)) == 2


def test_invalid_compare_input_does_not_create_history(workspace, cv):
    with pytest.raises(WorkspaceError):
        workspace.compare_cv_to_job(cv.id, 999)
    assert workspace.analysis_history(cv.id) == []


def test_fallback_review_can_be_saved_without_changing_score(workspace, cv, job):
    workspace.review_service_factory = lambda: AnalyzerReviewService(settings=Settings())
    snapshot = workspace.compare_cv_to_job(cv.id, job.id)
    assert snapshot.review.analysis.ai_available is False
    assert workspace.get_analysis(snapshot.id).review == snapshot.review


def test_latest_analysis_only_average_and_distinct_job_skill_counts(workspace, cv, job, review, match_review):
    other_cv = workspace.save_cv(CVWrite(display_name="Other", cv_text=CV))
    other_job = workspace.save_job(JobWrite(job_title="Other", job_description="Python, SQL and AWS required."))
    old = match_review.model_copy(deep=True)
    old.analysis.overall_score = 10
    old.cv_quality.overall_score = 20
    old.analysis.missing_skills = ["Tableau"]
    workspace.save_analysis(cv.id, old, job.id)
    latest = match_review.model_copy(deep=True)
    latest.analysis.overall_score = 70
    latest.cv_quality.overall_score = 80
    latest.analysis.missing_skills = ["AWS", "AWS"]
    latest.analysis.partially_matched_skills = ["PowerBI"]
    latest.improvement_areas = [ImprovementArea(issue="No professional experience", why_it_matters="Evidence", recommended_action="Add truthful examples")]
    workspace.save_analysis(cv.id, latest, job.id)
    second = latest.model_copy(deep=True)
    second.analysis.overall_score = 50
    second.cv_quality.overall_score = 60
    workspace.save_analysis(other_cv.id, second, job.id)
    workspace.save_analysis(other_cv.id, second, other_job.id)
    insights = workspace.get_workspace_insights()
    assert insights.average_job_match == 56.7  # (70+50+50)/3 latest pairs, never 10
    assert insights.average_cv_quality == 70  # (80+60)/2 latest CVs, never 20
    assert {item.label: item.count for item in insights.missing_skills} == {"aws": 2}
    assert {item.label: item.count for item in insights.partial_skills} == {"Power BI": 2}
    assert {item.label: item.count for item in insights.requested_skills}["Python"] == 2
    assert insights.improvement_areas[0].count == 2
    assert insights.latest_job_match == 50


def test_unsaved_job_comparison_retained_but_excluded_from_pair_average(workspace, cv, match_review):
    workspace.save_analysis(cv.id, match_review)
    assert workspace.analysis_history(cv.id)[0].job_match_score == 63
    insights = workspace.get_workspace_insights()
    assert insights.average_cv_quality == 83
    assert insights.average_job_match is None


def test_application_pipeline_counts_and_active_policy(workspace, cv):
    for status in ApplicationStatus:
        job = workspace.save_job(JobWrite(job_title=status.value, job_description=JD))
        workspace.create_application(ApplicationWrite(cv_id=cv.id, job_id=job.id, status=status))
    insights = workspace.get_workspace_insights()
    assert insights.applications == 6
    assert insights.active_applications == 4
    assert all(count == 1 for count in insights.application_pipeline.values())


def test_private_cv_and_jd_are_not_logged(workspace, cv, job, match_review, caplog):
    workspace.save_analysis(cv.id, match_review, job.id)
    workspace.get_workspace_insights()
    assert "student@example.test" not in caplog.text
    assert CV not in caplog.text
    assert JD not in caplog.text


def test_deleting_last_compared_job_clears_cached_cv_score(workspace, cv, job, match_review):
    workspace.save_analysis(cv.id, match_review, job.id)
    workspace.delete_job(job.id)
    saved = workspace.get_cv(cv.id)
    assert saved.latest_cv_score is saved.last_analyzed_at is None
    assert workspace.get_workspace_insights().average_cv_quality is None


def test_status_only_update_preserves_date_and_explicit_edit_can_clear_it(workspace, cv, job):
    app = workspace.create_application(ApplicationWrite(cv_id=cv.id, job_id=job.id, date_applied=date(2026, 10, 1)))
    changed = workspace.update_application_status(app.id, ApplicationStatus.interview)
    assert changed.date_applied == app.date_applied
    assert workspace.update_application(app.id, ApplicationStatus.interview, None, "").date_applied is None


def test_cleanup_failure_preserves_successful_comparison(workspace, cv, job, caplog):
    service = AnalyzerReviewService(settings=Settings(), provider=MockProvider())
    workspace.review_service_factory = lambda: service
    with patch.object(service, "close", side_effect=RuntimeError("private body")):
        snapshot = workspace.compare_cv_to_job(cv.id, job.id)
    assert snapshot.job_match_score == 63
    assert "private body" not in caplog.text
