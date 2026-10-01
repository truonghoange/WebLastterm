"""Analyzer inputs and product review. Scores always come from backend services."""
from hashlib import sha256
import logging

import streamlit as st

from backend.exceptions import DocumentParseError, InvalidCVError
from backend.models import CVDocument
from backend.parsers.file_parser import FileParser
from backend.services.analyzer_review_service import AnalyzerReviewService
from backend.services.bullet_review_service import rewrite_bullets
from backend.services.report_service import generate_report
from constants import INDUSTRIES
from frontend.workspace_ui import clear_saved_context, persist_reanalysis, render_save_controls
from frontend.components import badge, evidence_quote, metric_card, mode_notice, page_header, surface, upload_status

logger = logging.getLogger(__name__)
STRENGTH_LABELS = {"strong_evidence": "Strong evidence", "some_evidence": "Some evidence", "mention_only": "Mention only"}


def _clear_review():
    st.session_state.analysis_result = None
    st.session_state.review_result = None
    st.session_state.rewrite_suggestions = []
    for key in list(st.session_state):
        if key.startswith("bullet-select-"):
            del st.session_state[key]


def _analyze():
    document = st.session_state.get("cv_document")
    if document is None or document.raw_text != st.session_state.cv_text:
        document = CVDocument(raw_text=st.session_state.cv_text)
    service = None
    try:
        service = AnalyzerReviewService()
        with st.spinner("Reviewing your CV and its supporting evidence…"):
            review = service.analyze_cv(document, jd_text=st.session_state.jd_text,
                target_position=st.session_state.target_position, industry=st.session_state.industry)
    except (InvalidCVError, DocumentParseError) as error:
        st.error(str(error))
        return False
    except Exception as error:
        # Normal users never receive an exception body, stack trace or private input.
        logger.error("Product review failed (type=%s)", type(error).__name__)
        st.error("This review could not be completed. Please try again or use a different document.")
        return False
    finally:
        if service is not None:
            try:
                service.close()
            except Exception as error:
                logger.warning("Product review cleanup failed (type=%s)", type(error).__name__)
    _clear_review()
    st.session_state.cv_document = document
    st.session_state.analysis_result = review.analysis
    st.session_state.review_result = review
    persist_reanalysis(document, review)
    return True


def _upload_document(upload, kind):
    if upload is None:
        st.session_state.pop(f"_{kind}_upload_sig", None)
        st.session_state.pop(f"_{kind}_upload_document", None)
        return
    signature = (upload.name, sha256(upload.getvalue()).hexdigest())
    key = f"_{kind}_upload_sig"
    if st.session_state.get(key) == signature:
        _show_upload_status(st.session_state.get(f"_{kind}_upload_document"))
        return
    try:
        document = FileParser().parse(upload)
    except DocumentParseError as error:
        st.error(str(error))
        st.caption("Choose another file, remove this upload, or paste readable text below.")
        return
    st.session_state[key] = signature
    st.session_state[f"_{kind}_upload_document"] = document
    st.session_state[f"{kind}_text"] = document.raw_text
    revision_key = f"{kind}_editor_revision"
    revision = st.session_state.get(revision_key, 0) + 1
    st.session_state[revision_key] = revision
    # A new widget identity prevents an older browser edit from overriding an upload.
    st.session_state[f"input_{kind}_{revision}"] = document.raw_text
    if kind == "cv":
        if st.session_state.get("cv_document") is None or st.session_state.cv_document.raw_text != document.raw_text:
            clear_saved_context()
        st.session_state.cv_document = document
    _show_upload_status(document)


def _show_upload_status(document):
    if document is None:
        return
    pages = f"{document.page_count} {'page' if document.page_count == 1 else 'pages'} · " if document.page_count else ""
    upload_status(document.filename or "Document ready", pages + "Text extracted successfully. Review it below.")
    if document.extraction_quality == "low":
        st.warning("Some text may be missing or out of order. Check the extracted text before analyzing.")


def render_analyzer(go):
    page_header("Analyze your CV", "Get an evidence-based review or compare your CV against a job.", "Analyzer")
    left, right = st.columns(2, gap="large")
    revision = st.session_state.get("upload_revision", 0)
    with left, surface("cv_input"):
        st.subheader("Your CV")
        st.caption(f"PDF, DOCX or TXT · Up to {st.get_option('server.maxUploadSize')} MB per file")
        upload = st.file_uploader("Upload CV", type=["pdf", "docx", "txt"], key=f"cv_upload_{revision}")
        _upload_document(upload, "cv")
        editor_key = f"input_cv_{st.session_state.get('cv_editor_revision', 0)}"
        if editor_key not in st.session_state:
            st.session_state[editor_key] = st.session_state.cv_text
        st.session_state.cv_text = st.text_area("CV text", key=editor_key, height=300, placeholder="Or paste your CV here…")
        st.caption(f"{len(st.session_state.cv_text.split())} words · Check the extracted text before analysis.")
    with right, surface("jd_input"):
        st.subheader("Job Description (optional)")
        st.caption("Add a Job Description to receive a separate Job Match score.")
        with st.expander("Upload a JD instead"):
            upload = st.file_uploader("Upload JD (optional)", type=["pdf", "docx", "txt"], key=f"jd_upload_{revision}")
            _upload_document(upload, "jd")
        editor_key = f"input_jd_{st.session_state.get('jd_editor_revision', 0)}"
        if editor_key not in st.session_state:
            st.session_state[editor_key] = st.session_state.jd_text
        st.session_state.jd_text = st.text_area("Job Description", key=editor_key, height=300,
                                              placeholder="Leave blank for CV Review…")
        st.caption(f"{len(st.session_state.jd_text.split())} words")
    with surface("role_context"):
        st.subheader("Role and industry context")
        st.caption("Optional. Leave these blank or on Auto when you want a general review.")
        a, b = st.columns(2)
        industries = ["General / Auto"] + INDUSTRIES
        if "input_industry" not in st.session_state:
            st.session_state.input_industry = st.session_state.industry or "General / Auto"
        if st.session_state.input_industry not in industries:
            st.session_state.input_industry = "General / Auto"
        st.session_state.industry = b.selectbox("Industry", industries, key="input_industry",
            help="Optional context. CV Review does not use industry to change quality ratings.")
        if "input_target" not in st.session_state:
            st.session_state.input_target = st.session_state.target_position
        st.session_state.target_position = a.text_input("Target position", key="input_target",
            placeholder="e.g. Data Analyst Intern", help="Leave blank to use the JD title or CV headline when available.")
    if st.session_state.jd_text.strip():
        mode_notice("CV + Job Match", "CV quality and job alignment are scored separately.")
    else:
        mode_notice("CV Review", "Review your content, skills, projects and academic evidence. No job description needed.")
    st.caption("Include only information you want processed. Your review uses the text shown above.")
    if st.button("Analyze CV  →", type="primary"):
        if _analyze():
            go("Results")


def _metric(label, value, detail):
    metric_card(label, value, detail, compact_value=label == "Analysis")


def _priorities(review):
    st.subheader("Fix these first")
    if not review.top_recommendations:
        st.info("No specific priorities were identified. Review the evidence below.")
    columns = st.columns(max(1, len(review.top_recommendations)), gap="medium")
    for number, (column, item) in enumerate(zip(columns, review.top_recommendations), 1):
        with column, surface(f"priority_{number}"):
            badge(f"Priority {number}", "primary")
            st.markdown(f"**{item.title}**")
            st.write(item.reason)
            st.write(item.action)


def _skills(review):
    st.subheader("Skills evidence")
    strong, other = st.columns(2)
    for column, title, states in ((strong, "Skills with strong evidence", {"strong_evidence"}),
                                  (other, "Skills needing stronger evidence", {"some_evidence", "mention_only"})):
        with column:
            st.markdown(f"**{title}**")
            items = [item for item in review.skill_evidence if item.strength in states]
            if not items:
                st.caption("No skills in this group were identified.")
            for item in items:
                with st.expander(f"{item.skill} · {STRENGTH_LABELS[item.strength]}"):
                    st.write(item.explanation)
                    badge(STRENGTH_LABELS[item.strength], "success" if item.strength == "strong_evidence" else "primary" if item.strength == "some_evidence" else "neutral")
                    for quote in item.evidence:
                        evidence_quote(quote)
                    if not item.evidence:
                        st.caption("Mentioned in the CV; no project/work evidence found.")
                        for quote in item.mention_evidence[:3]:
                            st.write(quote)


def _bullet_review(review):
    st.subheader("Bullet Review")
    flagged = [item for item in review.bullet_reviews if item.issues]
    if not review.bullet_reviews:
        st.info("No project or experience bullets were detected. Use clear headings and bullet markers to review them here.")
        return
    if not flagged:
        st.success("No bullet issues were flagged by the current review rules.")
        return
    st.caption("Select up to 20 bullets for suggestions. Unknown details stay as placeholders for you to verify.")
    selected = []
    for item in flagged:
        with st.expander(item.original[:85] + ("…" if len(item.original) > 85 else "")):
            st.markdown("**Original**")
            evidence_quote(item.original)
            st.markdown("**Issue**")
            for issue in item.issues:
                st.write("• " + issue)
            st.markdown("**How to improve**")
            for action in item.how_to_improve:
                st.write(action)
            if st.checkbox("Select for rewrite", key=f"bullet-select-{item.id}"):
                selected.append(item.original)
    if st.button("Suggest rewrite", disabled=not selected):
        try:
            st.session_state.rewrite_suggestions = rewrite_bullets(selected, st.session_state.cv_document)
        except InvalidCVError as error:
            st.error(str(error))
    for index, item in enumerate(st.session_state.get("rewrite_suggestions", [])):
        with surface(f"rewrite_{index}"):
            st.markdown("**Suggested rewrite**")
            st.write(item.rewrite)
            st.caption(item.notes)
            if item.requires_user_input:
                st.caption("Details to confirm: " + ", ".join(item.requires_user_input))


def _cv_review(review):
    st.subheader("CV score breakdown")
    columns = st.columns(2, gap="large")
    for index, (name, value) in enumerate(review.cv_quality.scores.model_dump(exclude_none=True).items()):
        with columns[index % 2]:
            st.write(f"**{name.replace('_', ' ').title()}** · {value}/100")
            st.progress(value / 100)
    st.subheader("Your strengths")
    if not review.strengths:
        st.info("No specific strengths were identified in this review.")
    columns = st.columns(2, gap="large")
    for index, item in enumerate(review.strengths):
        with columns[index % 2], surface(f"strength_{index}"):
            st.markdown(f"**{item.title}**")
            if item.explanation:
                st.write(item.explanation)
            for quote in item.evidence:
                evidence_quote(quote)
    st.subheader("Areas to improve")
    if not review.improvement_areas:
        st.caption("No specific improvement areas were identified.")
    for item in review.improvement_areas:
        with st.expander(item.issue):
            st.markdown("**Why it matters**")
            st.write(item.why_it_matters)
            st.markdown("**Recommended action**")
            st.write(item.recommended_action)
    _skills(review)
    st.subheader("CV issues")
    checks = review.analysis.basic_checks
    for name, present in (("Email", checks.has_email), ("Phone", checks.has_phone)):
        st.write(f"{'✓' if present else '○'} {name} {'present' if present else 'not detected'}")
    if checks.missing_sections:
        for name in checks.missing_sections:
            st.warning("Section not detected: " + name.replace("_", " "))
    else:
        st.caption("Core section headings were detected.")
    st.caption(f"{checks.word_count} words · {checks.bullet_count} bullets detected")
    _bullet_review(review)


def _job_match(review):
    result = review.analysis
    st.subheader("Why this match score?")
    names = {"hard_skills": "Hard skills", "experience": "Experience relevance", "projects": "Projects",
             "education": "Education alignment", "role": "Role relevance", "other": "Soft/other requirements"}
    components = result.analysis_metadata.scoring_components if result.analysis_metadata else {}
    columns = st.columns(2, gap="large")
    for index, (name, label) in enumerate(names.items()):
        with columns[index % 2]:
            value = components.get(name)
            if value is None:
                st.caption(f"{label}: no assessable requirement in this JD")
            else:
                st.write(f"**{label}** · {value}/100")
                st.progress(value / 100)
    columns = st.columns(3)
    for column, state, title in zip(columns, ("matched", "partial", "missing"),
                                     ("Matched requirements", "Partially matched requirements", "Missing requirements")):
        with column:
            st.markdown(f"**{title}**")
            matches = getattr(review.requirement_groups, state)
            if not matches:
                st.caption("None identified.")
            for match in matches:
                with st.expander(f"{match.requirement} · {state.title()}"):
                    badge(state.title(), {"matched": "success", "partial": "warning", "missing": "danger"}[state])
                    if match.evidence:
                        st.markdown("**Evidence**")
                        for quote in match.evidence:
                            evidence_quote(quote)
                    else:
                        st.caption("No supporting CV evidence found.")
                    if match.explanation:
                        st.write(match.explanation)
    st.subheader("Skills and job requirements")
    st.write("**Matched skills:** " + (", ".join(result.matched_skills) or "None"))
    st.write("**Partially matched skills:** " + (", ".join(result.partially_matched_skills) or "None"))
    st.write("**Missing skills:** " + (", ".join(result.missing_skills) or "None"))
    st.caption("A missing requirement is a gap against this JD. Only add skills or experience that reflect your background.")


def render_results(go, score_label):
    review = st.session_state.get("review_result")
    if review is None:
        st.info("Analyze your CV again to open the complete review.")
        if st.button("Edit inputs"):
            go("Analyzer")
        return
    result = review.analysis
    page_header("Your CV review" if result.mode == "cv_only" else "Your job match review",
                "See the evidence behind your scores and focus on your next steps.", "Analysis results")
    if review.target_role:
        st.subheader(review.target_role)
    badge("CV + Job Match" if result.mode == "job_match" else "CV Review", "primary")
    st.caption(review.industry)
    st.write(review.summary)
    for warning in review.display_warnings:
        st.warning(warning)
    with st.container(key="result_metrics"):
        columns = st.columns(4)
        with columns[0]:
            _metric("CV Quality Score" if result.mode == "job_match" else "CV score",
                    f"{review.cv_quality.overall_score}/100", score_label(review.cv_quality.overall_score, "cv_only"))
        with columns[1]:
            if result.mode == "job_match":
                _metric("Job Match Score", f"{result.overall_score}/100", score_label(result.overall_score, "job_match"))
            else:
                _metric("Detected skills", str(len(review.skill_evidence)), "Skills with supporting detail")
        with columns[2]:
            _metric("Analysis", "AI + Basic ✓" if result.ai_available else "Basic fallback",
                    "Full analysis" if result.ai_available else "Basic analysis")
        with columns[3]:
            _metric("CV issues", str(len(result.basic_checks.missing_sections) + int(not result.basic_checks.has_email)
                                     + int(not result.basic_checks.has_phone)), "Contact and section checks")
    st.download_button("Download Report", data=generate_report(review), file_name="CVision_review.md", mime="text/markdown")
    _priorities(review)
    if result.mode == "job_match":
        cv_tab, match_tab = st.tabs(["CV Review", "Job Match"])
        with cv_tab:
            _cv_review(review)
        with match_tab:
            _job_match(review)
    else:
        _cv_review(review)
    with st.expander("How the scores work"):
        st.write("CV quality and job alignment answer different questions. Scores come from the existing backend scoring service; they are never combined.")
        st.write("CV Review considers content, skills, experience, projects, education and structure. Job Match assesses the requirements in your supplied JD.")
        st.caption("These scores are review aids, not hiring probabilities or official ATS scores.")
    with st.expander("Analysis details (debug)"):
        st.write("Technical warnings")
        for warning in result.warnings:
            st.write(warning)
        if result.analysis_metadata:
            st.json(result.analysis_metadata.model_dump(mode="json"))
    render_save_controls(go)
    another, edit, again = st.columns(3)
    if another.button("Analyze another CV", use_container_width=True):
        clear_saved_context()
        _clear_review()
        st.session_state.cv_text = ""
        st.session_state.jd_text = ""
        st.session_state.target_position = ""
        st.session_state.cv_document = None
        st.session_state.upload_revision = st.session_state.get("upload_revision", 0) + 1
        for key in ("input_cv", "input_jd", "input_target", "_cv_upload_sig", "_jd_upload_sig"):
            st.session_state.pop(key, None)
        for key in list(st.session_state):
            if key.startswith(("input_cv_", "input_jd_")):
                st.session_state.pop(key, None)
        go("Analyzer")
    if edit.button("Edit inputs", use_container_width=True):
        # Preserve the draft text while allowing the original file to be uploaded again.
        st.session_state.upload_revision = st.session_state.get("upload_revision", 0) + 1
        st.session_state.pop("_cv_upload_sig", None)
        st.session_state.pop("_jd_upload_sig", None)
        go("Analyzer")
    if again.button("Re-analyze", use_container_width=True):
        if _analyze():
            st.rerun()
