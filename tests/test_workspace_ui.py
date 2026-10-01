from pathlib import Path
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest

from backend.config import Settings
from backend.services.analyzer_review_service import AnalyzerReviewService
from backend.services.workspace_service import WorkspaceService
from backend.storage.models import ApplicationStatus, ApplicationWrite, CVWrite, JobWrite
from tests.helpers import CV, JD, MockProvider, document

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def click(app, label, *, exact=False):
    next(button for button in app.button if button.label == label or (not exact and label in button.label)).click().run(timeout=20)
    assert not app.exception


def output(app):
    return "\n".join(item.value for item in [*app.markdown, *app.title, *app.subheader, *app.info, *app.warning, *app.error, *app.success])


def app_at(page, **state):
    app = AppTest.from_file(APP)
    app.session_state["page"] = page
    for key, value in state.items():
        app.session_state[key] = value
    app.run(timeout=20)
    assert not app.exception
    return app


@pytest.fixture
def provider(monkeypatch):
    provider = MockProvider()
    factory = lambda: AnalyzerReviewService(settings=Settings(), provider=provider)
    monkeypatch.setattr("frontend.review_ui.AnalyzerReviewService", factory)
    monkeypatch.setattr("backend.services.workspace_service.AnalyzerReviewService", factory)
    return provider


@pytest.fixture
def seeded(provider):
    workspace = WorkspaceService()
    cv = workspace.save_cv(CVWrite(display_name="Data CV", cv_text=CV))
    job = workspace.save_job(JobWrite(job_title="Data Analyst", job_description=JD, company="Example"))
    return workspace, cv, job


def test_analyze_save_open_and_reanalyze_without_duplicate_cvs(provider):
    app = app_at("Analyzer", cv_text=CV)
    click(app, "Analyze CV")
    assert len(provider.calls) == 1
    next(field for field in app.text_input if field.label == "Display name").set_value("My Data CV")
    click(app, "Save as new CV", exact=True)
    workspace = WorkspaceService()
    cv = workspace.list_cvs()[0]
    assert cv.display_name == "My Data CV"
    assert len(workspace.analysis_history(cv.id)) == 1
    click(app, "Update saved CV", exact=True)
    assert len(workspace.list_cvs()) == 1
    assert len(workspace.analysis_history(cv.id)) == 1
    click(app, "My CVs")
    assert "My Data CV" in output(app)
    click(app, "Open", exact=True)
    assert "Analysis history" in output(app)
    assert len(provider.calls) == 1
    click(app, "Analyze again", exact=True)
    assert len(provider.calls) == 2
    assert len(workspace.list_cvs()) == 1
    assert len(workspace.analysis_history(cv.id)) == 2


def test_job_save_compare_application_tracking_and_insights(provider):
    workspace = WorkspaceService()
    cv = workspace.save_cv(CVWrite(display_name="Data CV", cv_text=CV))
    app = app_at("Jobs")
    click(app, "Add Job", exact=True)
    for field in app.text_input:
        if field.label == "Job title":
            field.set_value("Data Analyst")
        if field.label == "Company":
            field.set_value("Example Company")
    next(field for field in app.text_area if field.label == "Job Description").set_value(JD)
    click(app, "Save job", exact=True)
    assert "Compared CVs" in output(app)
    assert len(provider.calls) == 0
    click(app, "Compare another CV", exact=True)
    click(app, "Compare CV to Job", exact=True)
    assert "CV Quality Score" in output(app)
    assert "Job Match Score" in output(app)
    assert "83/100" in output(app)
    assert "63/100" in output(app)
    assert len(provider.calls) == 1
    job = workspace.list_jobs()[0]
    assert workspace.latest_job_analysis(cv.id, job.id).job_match_score == 63
    click(app, "Create Application", exact=True)
    click(app, "Create application", exact=True)
    application = workspace.list_applications()[0]
    assert application.status == ApplicationStatus.saved
    next(box for box in app.selectbox if box.label == "Status").select(ApplicationStatus.applied)
    click(app, "Update status", exact=True)
    assert workspace.get_application(application.id).status == ApplicationStatus.applied
    next(box for box in app.selectbox if box.label == "Status").select(ApplicationStatus.interview)
    click(app, "Update status", exact=True)
    assert workspace.get_application(application.id).status == ApplicationStatus.interview
    click(app, "Insights")
    assert "Most common missing skills" in output(app)
    assert "Skills often partially demonstrated" in output(app)
    assert "Interview · 1" in output(app)
    assert len(provider.calls) == 1


@pytest.mark.parametrize("page,empty_text", [("My CVs", "No saved CVs yet"),
    ("Jobs", "No saved jobs yet"), ("Applications", "No applications tracked yet"),
    ("Insights", "More insights will appear"), ("Compare", "Save at least one CV and one job")])
def test_empty_workspace_pages_and_sidebar_are_functional(page, empty_text, provider):
    app = app_at(page)
    assert empty_text in output(app)
    for name in ("My CVs", "Jobs", "Applications", "Insights"):
        assert next(button for button in app.sidebar.button if name in button.label).disabled is False
    assert len(provider.calls) == 0


def test_saved_cv_reanalysis_from_result_appends_snapshot_and_reset_detaches_identity(seeded, provider):
    workspace, cv, job = seeded
    snapshot = workspace.compare_cv_to_job(cv.id, job.id)
    app = app_at("Results", cv_document=document(), cv_text=CV, jd_text=JD,
        analysis_result=snapshot.review.analysis, review_result=snapshot.review,
        saved_cv_id=cv.id, saved_job_id=job.id, saved_cv_name=cv.display_name)
    click(app, "Re-analyze", exact=True)
    assert len(workspace.analysis_history(cv.id)) == 2
    assert len(workspace.list_cvs()) == 1
    click(app, "Analyze another CV", exact=True)
    assert app.session_state.get("saved_cv_id") is None
    assert app.session_state["cv_text"] == ""


def test_duplicate_application_shows_message(seeded, provider):
    workspace, cv, job = seeded
    workspace.create_application(ApplicationWrite(cv_id=cv.id, job_id=job.id))
    app = app_at("New Application", new_application_cv_id=cv.id, new_application_job_id=job.id)
    click(app, "Create application", exact=True)
    assert "Application already exists" in output(app)
    assert len(workspace.list_applications()) == 1
    assert len(provider.calls) == 0


def test_delete_requires_confirmation_and_blocks_related_application(seeded, provider):
    workspace, cv, job = seeded
    application = workspace.create_application(ApplicationWrite(cv_id=cv.id, job_id=job.id))
    app = app_at("CV Detail", selected_cv_id=cv.id)
    click(app, "Delete CV", exact=True)
    assert workspace.get_cv(cv.id)
    click(app, "Cancel", exact=True)
    assert workspace.get_cv(cv.id)
    click(app, "Delete CV", exact=True)
    click(app, "Confirm delete", exact=True)
    assert "used in applications" in output(app)
    workspace.delete_application(application.id)
    click(app, "Confirm delete", exact=True)
    assert workspace.list_cvs() == []
    assert workspace.get_job(job.id)


def test_job_edit_and_cv_rename_preserve_records(seeded, provider):
    workspace, cv, job = seeded
    app = app_at("Job Detail", selected_job_id=job.id)
    click(app, "Edit Job", exact=True)
    next(field for field in app.text_input if field.label == "Job title").set_value("Senior Analyst")
    click(app, "Update job", exact=True)
    assert workspace.get_job(job.id).job_title == "Senior Analyst"
    click(app, "My CVs")
    click(app, "Rename", exact=True)
    next(field for field in app.text_input if field.label == "CV name").set_value("Renamed CV")
    click(app, "Save name", exact=True)
    assert workspace.get_cv(cv.id).display_name == "Renamed CV"
    assert len(provider.calls) == 0


def test_workspace_storage_failure_never_exposes_traceback_or_private_data():
    with patch("frontend.workspace_ui.WorkspaceService", side_effect=RuntimeError("student@example.test private content")):
        app = app_at("Insights")
    assert "could not complete this action" in output(app)
    assert "student@example.test" not in output(app)


def test_dashboard_metrics_browse_without_ai(seeded, provider):
    app = app_at("Dashboard")
    metrics = {item.label: item.value for item in app.metric}
    assert metrics["Saved CVs"] == "1"
    assert metrics["Saved Jobs"] == "1"
    assert metrics["Latest CV Score"] == "—"
    assert len(provider.calls) == 0


def test_history_view_reuses_existing_results_without_gemini(seeded, provider):
    workspace, cv, job = seeded
    workspace.compare_cv_to_job(cv.id, job.id)
    app = app_at("Job Detail", selected_job_id=job.id)
    click(app, "View comparison", exact=True)
    assert "Job Match Score" in output(app)
    assert len(provider.calls) == 1
    assert len(workspace.analysis_history(cv.id)) == 1


def test_failed_auto_save_can_retry_identical_review_without_another_ai_call(seeded, provider):
    workspace, cv, job = seeded
    snapshot = workspace.compare_cv_to_job(cv.id, job.id)
    app = app_at("Results", cv_document=document(), cv_text=CV, jd_text=JD,
        analysis_result=snapshot.review.analysis, review_result=snapshot.review,
        saved_cv_id=cv.id, saved_job_id=job.id, saved_cv_name=cv.display_name,
        saved_snapshot_id=snapshot.id, _saved_review_json=snapshot.review.model_dump_json())
    with patch("frontend.workspace_ui.WorkspaceService", side_effect=RuntimeError("private body")):
        click(app, "Re-analyze", exact=True)
    assert "history could not be saved" in output(app)
    assert len(workspace.analysis_history(cv.id)) == 1
    click(app, "Update saved CV", exact=True)
    assert len(workspace.analysis_history(cv.id)) == 2
    assert len(provider.calls) == 2
    assert "private body" not in output(app)
