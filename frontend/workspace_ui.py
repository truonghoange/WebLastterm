"""Career workspace screens. All persistence goes through WorkspaceService."""
from pathlib import Path
import logging

from pydantic import ValidationError
import streamlit as st

from backend.exceptions import InvalidCVError
from backend.services.workspace_service import WorkspaceService
from backend.storage.models import ApplicationStatus, ApplicationWrite, JobWrite, WorkspaceError
from frontend.components import badge, count_row, empty_state, evidence_quote, page_header, surface

logger = logging.getLogger(__name__)
STATUS_TONES = {ApplicationStatus.saved: "neutral", ApplicationStatus.applied: "primary",
    ApplicationStatus.interview: "warning", ApplicationStatus.offer: "success",
    ApplicationStatus.rejected: "neutral", ApplicationStatus.withdrawn: "neutral"}


def _date(value):
    return value.strftime("%b %d, %Y") if value else "Not analyzed yet"


def _safe(action):
    try:
        return action()
    except (WorkspaceError, InvalidCVError) as error:
        st.error(str(error))
    except ValidationError:
        st.error("Check the required fields and choose valid values before saving.")
    except Exception as error:
        logger.error("Workspace action failed (type=%s)", type(error).__name__)
        st.error("The workspace could not complete this action. Please try again and check that local storage is available.")
    return None


def _flash(message):
    st.session_state.workspace_notice = message


def _open(go, page, key, value):
    st.session_state[key] = value
    go(page)


def _compare(go, cv_id=None, job_id=None):
    st.session_state.compare_cv_id = cv_id
    st.session_state.compare_job_id = job_id
    st.session_state.pop("compare_cv_selection", None)
    st.session_state.pop("compare_job_selection", None)
    go("Compare")


def _application(go, cv_id=None, job_id=None):
    st.session_state.new_application_cv_id = cv_id
    st.session_state.new_application_job_id = job_id
    st.session_state.application_form_revision = st.session_state.get("application_form_revision", 0) + 1
    go("New Application")


def show_snapshot(workspace, snapshot, go):
    cv = workspace.get_cv(snapshot.cv_id)
    job = workspace.get_job(snapshot.job_id) if snapshot.job_id else None
    st.session_state.cv_document = workspace.cv_document(cv)
    st.session_state.cv_text = cv.cv_text
    st.session_state.jd_text = job.job_description if job else ""
    st.session_state.target_position = snapshot.review.target_role or ""
    st.session_state.industry = snapshot.review.industry
    st.session_state.analysis_result = snapshot.review.analysis
    st.session_state.review_result = snapshot.review
    st.session_state.rewrite_suggestions = []
    st.session_state.saved_cv_id = cv.id
    st.session_state.saved_job_id = job.id if job else None
    st.session_state.saved_cv_name = cv.display_name
    st.session_state.saved_snapshot_id = snapshot.id
    st.session_state._saved_review_json = snapshot.review.model_dump_json()
    for key in list(st.session_state):
        if key.startswith(("input_cv_", "input_jd_", "bullet-select-")) or key in {"input_target", "input_industry"}:
            st.session_state.pop(key, None)
    st.session_state.upload_revision = st.session_state.get("upload_revision", 0) + 1
    st.session_state.pop("_cv_upload_sig", None)
    st.session_state.pop("_jd_upload_sig", None)
    go("Results")


def clear_saved_context():
    for key in ("saved_cv_id", "saved_job_id", "saved_cv_name", "saved_snapshot_id", "_saved_review_json", "save_cv_display_name", "workspace_save_error"):
        st.session_state.pop(key, None)


def persist_reanalysis(document, review):
    """An explicit re-analysis of a saved CV appends a snapshot once."""
    cv_id = st.session_state.get("saved_cv_id")
    if cv_id is None:
        return
    # A fresh analysis may have identical output; it still deserves a fresh snapshot.
    st.session_state.pop("_saved_review_json", None)
    st.session_state.pop("saved_snapshot_id", None)
    def save():
        workspace = WorkspaceService()
        cv = workspace.get_cv(cv_id)
        job_id = st.session_state.get("saved_job_id")
        if job_id is not None:
            job = workspace.get_job(job_id)
            if review.analysis.mode != "job_match" or job.job_description.strip() != st.session_state.jd_text.strip():
                job_id = None
        cv, snapshot = workspace.save_analyzer_review(document, review, cv.display_name, cv.id, job_id)
        st.session_state.saved_job_id = job_id
        st.session_state.saved_snapshot_id = snapshot.id
        st.session_state.saved_cv_name = cv.display_name
        st.session_state._saved_review_json = review.model_dump_json()
        _flash("Analysis saved to CV history.")
        return snapshot
    if _safe(save) is None:
        st.session_state.workspace_save_error = "The review is ready, but its history could not be saved. Use Update saved CV to retry."


def render_save_controls(go):
    review = st.session_state.review_result
    cv_id = st.session_state.get("saved_cv_id")
    if st.session_state.get("workspace_notice"):
        st.success(st.session_state.pop("workspace_notice"))
    if st.session_state.get("workspace_save_error"):
        st.warning(st.session_state.pop("workspace_save_error"))
    if cv_id is not None:
        st.caption("Saved CV: " + st.session_state.get("saved_cv_name", "CV"))
    with st.expander("Save CV", expanded=cv_id is None):
        st.caption("CV text and normalized reviews are saved in your local workspace database.")
        document = st.session_state.cv_document
        default_name = st.session_state.get("saved_cv_name") or review.target_role or (Path(document.filename).stem if document.filename else None) or "My CV"
        with st.form("save_cv_form"):
            name = st.text_input("Display name", value=default_name, max_chars=200)
            submitted = st.form_submit_button("Update saved CV" if cv_id is not None else "Save as new CV")
        if submitted:
            def save():
                workspace = WorkspaceService()
                if cv_id is not None and st.session_state.get("_saved_review_json") == review.model_dump_json():
                    cv = workspace.rename_cv(cv_id, name)
                    snapshot_id = st.session_state.get("saved_snapshot_id")
                else:
                    cv, snapshot = workspace.save_analyzer_review(document, review, name, cv_id, st.session_state.get("saved_job_id"))
                    snapshot_id = snapshot.id
                st.session_state.saved_cv_id = cv.id
                st.session_state.saved_cv_name = cv.display_name
                st.session_state.saved_snapshot_id = snapshot_id
                st.session_state._saved_review_json = review.model_dump_json()
                _flash("CV saved to My CVs.")
                return cv
            if _safe(save) is not None:
                st.rerun()
    if cv_id is not None:
        a, b = st.columns(2)
        if a.button("Open saved CV"):
            _open(go, "CV Detail", "selected_cv_id", cv_id)
        if st.session_state.get("saved_job_id") and review.analysis.mode == "job_match":
            if b.button("Create Application"):
                _application(go, cv_id, st.session_state.saved_job_id)


def _delete(kind, record_id, action, go, destination):
    key = f"confirm_delete_{kind}_{record_id}"
    if st.button("Delete " + kind, key="delete_" + key):
        st.session_state[key] = True
    if st.session_state.get(key):
        st.warning(f"Delete this {kind.lower()}? Its related analysis history will also be removed. Applications must be deleted first." if kind != "Application"
                   else "Delete this application? Your CV, job and analyses will be kept.")
        confirm, cancel = st.columns(2)
        if confirm.button("Confirm delete", key=key + "_yes"):
            def perform():
                action(record_id)
                return True
            if _safe(perform):
                st.session_state.pop(key, None)
                if ((kind == "CV" and st.session_state.get("saved_cv_id") == record_id)
                        or (kind == "Job" and st.session_state.get("saved_job_id") == record_id)):
                    clear_saved_context()
                _flash(kind + " deleted.")
                go(destination)
        if cancel.button("Cancel", key=key + "_no"):
            st.session_state.pop(key, None)
            st.rerun()


def _rename(workspace, cv):
    with st.form(f"rename_cv_{cv.id}"):
        name = st.text_input("CV name", value=cv.display_name, max_chars=200)
        if st.form_submit_button("Save name"):
            if _safe(lambda: workspace.rename_cv(cv.id, name)) is not None:
                st.session_state.pop("rename_cv_id", None)
                _flash("CV name updated.")
                st.rerun()


def render_cvs(workspace, go):
    page_header("My CVs", "Your saved CVs, supporting evidence and review history.", "Workspace")
    cvs = workspace.list_cvs()
    if not cvs:
        empty_state("No saved CVs yet.", "Analyze your first CV to get started.")
        if st.button("Analyze your first CV", type="primary"):
            go("Analyzer")
    columns = st.columns(2, gap="large")
    for index, cv in enumerate(cvs):
        with columns[index % 2], surface(f"cv_{cv.id}"):
            st.subheader(cv.display_name)
            st.write("Target: " + (cv.target_role or "Not specified"))
            st.write(f"CV Score: {cv.latest_cv_score if cv.latest_cv_score is not None else 'Not analyzed'}")
            st.caption("Last analyzed: " + _date(cv.last_analyzed_at))
            a, b = st.columns(2)
            if a.button("Open", key=f"open_cv_{cv.id}"):
                _open(go, "CV Detail", "selected_cv_id", cv.id)
            if b.button("Analyze against job", key=f"match_cv_{cv.id}"):
                _compare(go, cv_id=cv.id)
            c, d = st.columns(2)
            if c.button("Rename", key=f"rename_{cv.id}"):
                st.session_state.rename_cv_id = cv.id
            with d:
                _delete("CV", cv.id, workspace.delete_cv, go, "My CVs")
            if st.session_state.get("rename_cv_id") == cv.id:
                _rename(workspace, cv)


def render_cv_detail(workspace, go):
    cv = workspace.get_cv(st.session_state.selected_cv_id)
    page_header(cv.display_name, "Review your latest evidence and explore previous analyses.", "Saved CV")
    st.write("Target role: " + (cv.target_role or "Not specified"))
    st.metric("Latest CV quality", cv.latest_cv_score if cv.latest_cv_score is not None else "—")
    st.caption("Last analysis: " + _date(cv.last_analyzed_at))
    a, b, c = st.columns(3)
    if a.button("Analyze again", type="primary"):
        with st.spinner("Analyzing saved CV…"):
            snapshot = _safe(lambda: workspace.analyze_saved_cv(cv.id))
        if snapshot:
            show_snapshot(workspace, snapshot, go)
    if b.button("Compare with job"):
        _compare(go, cv_id=cv.id)
    if c.button("Edit name"):
        st.session_state.rename_cv_id = cv.id
    if st.session_state.get("rename_cv_id") == cv.id:
        _rename(workspace, cv)
    _delete("CV", cv.id, workspace.delete_cv, go, "My CVs")
    latest = workspace.latest_cv_analysis(cv.id)
    if latest:
        st.subheader("Latest review")
        st.write(latest.review.summary)
        st.subheader("Strengths")
        for item in latest.review.strengths:
            with st.expander(item.title):
                st.write(item.explanation)
                for quote in item.evidence:
                    evidence_quote(quote)
        st.subheader("Improvement areas")
        for item in latest.review.improvement_areas:
            with st.expander(item.issue):
                st.write(item.why_it_matters)
                st.write(item.recommended_action)
        from frontend.review_ui import _skills
        _skills(latest.review)
    else:
        st.info("No analysis saved yet. Choose Analyze again to create a review.")
    st.subheader("Analysis history")
    history = workspace.analysis_history(cv.id)
    for index, snapshot in enumerate(history):
        text = f"{_date(snapshot.created_at)} · CV Quality: {snapshot.cv_quality_score}"
        if snapshot.job_match_score is not None:
            text += f" · Job Match: {snapshot.job_match_score}"
        with surface(f"history_{snapshot.id}"):
            st.write(text)
            if index + 1 < len(history):
                st.caption(f"Score change: {snapshot.cv_quality_score - history[index+1].cv_quality_score:+d}")
            if st.button("View analysis", key=f"history_{snapshot.id}"):
                show_snapshot(workspace, snapshot, go)


def _job_form(workspace, go, job=None):
    with st.form(f"job_form_{job.id if job else 'new'}"):
        title = st.text_input("Job title", value=job.job_title if job else "", max_chars=200)
        company = st.text_input("Company", value=job.company if job else "")
        location = st.text_input("Location (optional)", value=job.location if job else "")
        url = st.text_input("Source URL (optional)", value=job.source_url if job else "")
        jd = st.text_area("Job Description", value=job.job_description if job else "", height=240)
        notes = st.text_area("Notes (optional)", value=job.notes if job else "")
        submitted = st.form_submit_button("Update job" if job else "Save job", type="primary")
    if submitted:
        def save():
            data = JobWrite(job_title=title, company=company, location=location, source_url=url, job_description=jd, notes=notes)
            return workspace.update_job(job.id, data) if job else workspace.save_job(data)
        saved = _safe(save)
        if saved:
            _flash("Job saved.")
            _open(go, "Job Detail", "selected_job_id", saved.id)


def render_jobs(workspace, go):
    page_header("Jobs", "Keep the opportunities you want to explore and compare them with your CV.", "Workspace")
    if st.button("Add Job", type="primary"):
        go("New Job")
    jobs = workspace.list_jobs()
    if not jobs:
        empty_state("No saved jobs yet.", "Save a job description to compare against your CV.")
    columns = st.columns(2, gap="large")
    for index, job in enumerate(jobs):
        with columns[index % 2], surface(f"job_{job.id}"):
            st.subheader(job.job_title)
            st.write(job.company or "Company not specified")
            if job.location:
                st.write(job.location)
            st.caption("Saved " + _date(job.created_at))
            a, b = st.columns(2)
            if a.button("Open", key=f"open_job_{job.id}"):
                _open(go, "Job Detail", "selected_job_id", job.id)
            if b.button("Compare CV", key=f"compare_job_{job.id}"):
                _compare(go, job_id=job.id)
            c, d = st.columns(2)
            if c.button("Create application", key=f"apply_job_{job.id}"):
                _application(go, job_id=job.id)
            with d:
                _delete("Job", job.id, workspace.delete_job, go, "Jobs")


def render_job_detail(workspace, go):
    job = workspace.get_job(st.session_state.selected_job_id)
    page_header(job.job_title, "Compare your evidence with this role and track your application.", "Saved job")
    st.write(job.company or "Company not specified")
    if job.location:
        st.write(job.location)
    st.caption("Saved " + _date(job.created_at))
    st.subheader("Job Description")
    with surface("job_description"):
        st.text(job.job_description)
    if job.source_url:
        st.write("Source: " + job.source_url)
    if job.notes:
        st.write("Notes: " + job.notes)
    a, b, c = st.columns(3)
    if a.button("Compare another CV", type="primary"):
        _compare(go, job_id=job.id)
    if b.button("Edit Job"):
        go("Edit Job")
    if c.button("Create Application"):
        _application(go, job_id=job.id)
    _delete("Job", job.id, workspace.delete_job, go, "Jobs")
    st.subheader("Compared CVs")
    snapshots = workspace.job_comparisons(job.id)
    if not snapshots:
        st.caption("No comparisons saved yet.")
    for snapshot in snapshots:
        cv = workspace.get_cv(snapshot.cv_id)
        with surface(f"comparison_{snapshot.id}"):
            st.write(f"{cv.display_name} · Latest Match: {snapshot.job_match_score}")
            history = workspace.pair_history(cv.id, job.id, limit=2)
            if len(history) > 1:
                st.caption(f"Previous: {history[1].job_match_score}")
            st.caption("Compared " + _date(snapshot.created_at))
            if st.button("View comparison", key=f"job_analysis_{snapshot.id}"):
                show_snapshot(workspace, snapshot, go)


def render_compare(workspace, go):
    page_header("Compare saved CV with job", "Choose a CV and an opportunity to review how they align.", "Job match")
    cvs, jobs = workspace.list_cvs(), workspace.list_jobs()
    if not cvs or not jobs:
        empty_state("Save at least one CV and one job before comparing.", "Your saved documents will appear here.")
        if st.button("My CVs"):
            go("My CVs")
        if st.button("Add Job"):
            go("New Job")
        return
    cv_names = {cv.id: cv.display_name for cv in cvs}
    job_names = {job.id: f"{job.job_title} · {job.company}" if job.company else job.job_title for job in jobs}
    ids = list(cv_names)
    cv_id = st.selectbox("Saved CV", ids, index=ids.index(st.session_state.get("compare_cv_id")) if st.session_state.get("compare_cv_id") in ids else 0,
                        format_func=cv_names.get, key="compare_cv_selection")
    ids = list(job_names)
    job_id = st.selectbox("Saved job", ids, index=ids.index(st.session_state.get("compare_job_id")) if st.session_state.get("compare_job_id") in ids else 0,
                         format_func=job_names.get, key="compare_job_selection")
    st.caption("This explicit comparison runs the existing analyzer and saves a new history snapshot.")
    if st.button("Compare CV to Job", type="primary"):
        with st.spinner("Comparing CV evidence with job requirements…"):
            snapshot = _safe(lambda: workspace.compare_cv_to_job(cv_id, job_id))
        if snapshot:
            _flash("Comparison saved to analysis history.")
            show_snapshot(workspace, snapshot, go)


def render_application_form(workspace, go):
    page_header("Create Application", "Keep track of the job, CV and next stage in one place.", "Applications")
    cvs, jobs = workspace.list_cvs(), workspace.list_jobs()
    if not cvs or not jobs:
        empty_state("Save a CV and job first to track an application.")
        return
    cv_names = {cv.id: cv.display_name for cv in cvs}
    job_names = {job.id: f"{job.job_title} · {job.company}" for job in jobs}
    revision = st.session_state.get("application_form_revision", 0)
    with st.form(f"new_application_{revision}"):
        ids = list(job_names)
        selected = st.session_state.get("new_application_job_id")
        job_id = st.selectbox("Job", ids, index=ids.index(selected) if selected in ids else 0, format_func=job_names.get)
        ids = list(cv_names)
        selected = st.session_state.get("new_application_cv_id")
        cv_id = st.selectbox("CV", ids, index=ids.index(selected) if selected in ids else 0, format_func=cv_names.get)
        status = st.selectbox("Status", list(ApplicationStatus), format_func=lambda value: value.value.title())
        applied = st.date_input("Date applied (optional)", value=None)
        notes = st.text_area("Application notes")
        submitted = st.form_submit_button("Create application", type="primary")
    if submitted:
        application = _safe(lambda: workspace.create_application(ApplicationWrite(job_id=job_id, cv_id=cv_id, status=status, date_applied=applied, notes=notes)))
        if application:
            _flash("Application created.")
            _open(go, "Application Detail", "selected_application_id", application.id)


def render_applications(workspace, go):
    page_header("Applications", "A clear view of your opportunities, from saved roles to next steps.", "Workspace")
    if st.button("Create Application", type="primary"):
        _application(go)
    applications = workspace.list_applications()
    if not applications:
        empty_state("No applications tracked yet.", "Create an application from a saved job and CV.")
        return
    cvs = {cv.id: cv for cv in workspace.list_cvs()}
    jobs = {job.id: job for job in workspace.list_jobs()}
    columns = st.columns(3, gap="large")
    for index, status in enumerate(ApplicationStatus):
        items = [application for application in applications if application.status == status]
        with columns[index % 3]:
            st.subheader(f"{status.value.title()} ({len(items)})")
            if not items:
                st.caption("No applications in this stage.")
            for application in items:
                job, cv = jobs[application.job_id], cvs[application.cv_id]
                with surface(f"application_{application.id}"):
                    badge(status.value.title(), STATUS_TONES[status])
                    st.markdown(f"**{job.job_title}**")
                    st.caption(job.company or "Company not specified")
                    st.write(f"CV: {cv.display_name}")
                    if st.button("Open application", key=f"open_application_{application.id}"):
                        _open(go, "Application Detail", "selected_application_id", application.id)


def render_application_detail(workspace, go):
    application = workspace.get_application(st.session_state.selected_application_id)
    job, cv = workspace.get_job(application.job_id), workspace.get_cv(application.cv_id)
    page_header(job.job_title, "Update the stage, keep notes and revisit the evidence behind your match.", "Application")
    badge(application.status.value.title(), STATUS_TONES[application.status])
    st.write(job.company or "Company not specified")
    st.write("Selected CV: " + cv.display_name)
    latest = workspace.latest_job_analysis(cv.id, job.id)
    st.metric("Latest job match", latest.job_match_score if latest else "—")
    with st.form(f"update_application_{application.id}"):
        status = st.selectbox("Status", list(ApplicationStatus), index=list(ApplicationStatus).index(application.status), format_func=lambda value: value.value.title())
        date_applied = st.date_input("Date applied (optional)", value=application.date_applied)
        notes = st.text_area("Application notes", value=application.notes)
        submitted = st.form_submit_button("Update status", type="primary")
    if submitted:
        if _safe(lambda: workspace.update_application(application.id, status, date_applied, notes)):
            _flash("Application updated.")
            st.rerun()
    a, b, c = st.columns(3)
    if a.button("Open Job"):
        _open(go, "Job Detail", "selected_job_id", job.id)
    if b.button("Open CV"):
        _open(go, "CV Detail", "selected_cv_id", cv.id)
    if latest and c.button("View latest match analysis"):
        show_snapshot(workspace, latest, go)
    _delete("Application", application.id, workspace.delete_application, go, "Applications")


def _insight_list(title, items, unit):
    st.subheader(title)
    if not items:
        st.caption("No stored evidence for this insight yet.")
    for item in items:
        count_row(item.label, item.count, unit.rstrip("s") if item.count == 1 else unit)


def render_insights(workspace, go):
    page_header("Insights", "See patterns in your saved reviews, job requirements and application activity.", "Workspace")
    insights = workspace.get_workspace_insights()
    st.caption("Calculated from saved data. Averages use the latest analysis per CV and latest comparison per CV/job pair.")
    with st.container(key="insights_metrics"):
        columns = st.columns(5)
        for column, label, value in zip(columns,
                ("Saved CVs", "Saved Jobs", "Active Applications", "Average CV Quality", "Average Job Match"),
                (insights.saved_cvs, insights.saved_jobs, insights.active_applications, insights.average_cv_quality, insights.average_job_match)):
            column.metric(label, value if value is not None else "—")
    if not insights.saved_cvs or insights.average_cv_quality is None or insights.average_job_match is None:
        empty_state("More insights will appear after you save CVs and compare them with jobs.")
    left, right = st.columns(2, gap="large")
    with left, surface("missing_skills"):
        _insight_list("Most common missing skills", insights.missing_skills, "jobs")
    with right, surface("partial_skills"):
        _insight_list("Skills often partially demonstrated", insights.partial_skills, "jobs")
    with left, surface("requested_skills"):
        _insight_list("Frequently requested skills", insights.requested_skills, "jobs")
    with right, surface("improvement_areas"):
        _insight_list("Recurring CV improvement areas", insights.improvement_areas, "CVs")
    st.subheader("Application pipeline")
    for status, count in insights.application_pipeline.items():
        st.write(f"{status.value.title()} · {count}")


def render_dashboard(workspace, go):
    page_header("Welcome back", "Build stronger applications with evidence-based CV analysis.", "Your career workspace")
    insights = workspace.get_workspace_insights()
    with st.container(horizontal=True):
        analyze = st.button("Analyze CV", type="primary", icon=":material/description:")
        add_job = st.button("Add Job", icon=":material/add:")
    if analyze:
        go("Analyzer")
    if add_job:
        go("New Job")
    with st.container(key="dashboard_metrics"):
        columns = st.columns(4)
        for column, label, value in zip(columns, ("Saved CVs", "Saved Jobs", "Applications", "Latest CV Score"),
                (insights.saved_cvs, insights.saved_jobs, insights.applications, insights.latest_cv_score)):
            column.metric(label, value if value is not None else "—")
    if not insights.saved_cvs:
        empty_state("Start with your first CV", "Analyze your first CV, then use Save CV on the results page.")
    left, right = st.columns(2, gap="large")
    with left, surface("recent_cvs"):
        st.subheader("Recent CVs")
        cvs = workspace.list_cvs()[:3]
        if not cvs:
            st.caption("Your saved CVs will appear here.")
        for cv in cvs:
            st.markdown(f"**{cv.display_name}**")
            st.caption(f"CV quality: {cv.latest_cv_score if cv.latest_cv_score is not None else 'Not analyzed'} · {_date(cv.updated_at)}")
            if st.button("Open CV", key=f"recent_cv_{cv.id}"):
                _open(go, "CV Detail", "selected_cv_id", cv.id)
        if st.button("View CVs →"):
            go("My CVs")
    with right, surface("recent_jobs"):
        st.subheader("Recent Jobs")
        jobs = workspace.list_jobs()[:3]
        if not jobs:
            st.caption("Save a role to start comparing.")
        for job in jobs:
            st.markdown(f"**{job.job_title}**")
            st.caption(job.company or "Company not specified")
            if st.button("Open Job", key=f"recent_job_{job.id}"):
                _open(go, "Job Detail", "selected_job_id", job.id)
        if st.button("View Jobs →"):
            go("Jobs")
    with surface("application_pipeline"):
        st.subheader("Application Pipeline")
        columns = st.columns(3)
        for index, (status, count) in enumerate(insights.application_pipeline.items()):
            with columns[index % 3]:
                badge(f"{status.value.title()} · {count}", STATUS_TONES[status])
        if st.button("View Applications"):
            go("Applications")


def render_workspace(page, go):
    def render():
        workspace = WorkspaceService()
        if st.session_state.get("workspace_notice"):
            st.success(st.session_state.pop("workspace_notice"))
        if page == "New Job":
            page_header("Add Job", "Save a role and its requirements for your next comparison.", "Jobs")
            _job_form(workspace, go)
        elif page == "Edit Job":
            page_header("Edit Job", "Keep the role details and requirements up to date.", "Jobs")
            _job_form(workspace, go, workspace.get_job(st.session_state.selected_job_id))
        else:
            screens = {"Dashboard": render_dashboard, "My CVs": render_cvs, "CV Detail": render_cv_detail,
                "Jobs": render_jobs, "Job Detail": render_job_detail, "Compare": render_compare,
                "Applications": render_applications, "Application Detail": render_application_detail,
                "New Application": render_application_form, "Insights": render_insights}
            screens[page](workspace, go)
    _safe(render)
