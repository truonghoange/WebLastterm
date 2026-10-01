from pathlib import Path
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from streamlit.testing.v1 import AppTest

from backend.config import Settings
from backend.exceptions import LLMUnavailableError
from backend.services.analyzer_review_service import AnalyzerReviewService
from tests.helpers import CV, JD, MockProvider, document, semantic_payload

APP = str(Path(__file__).resolve().parents[1] / "app.py")


class AnalyzerUITests(unittest.TestCase):
    def app(self, *, cv=CV, jd=""):
        app = AppTest.from_file(APP)
        app.session_state["page"] = "Analyzer"
        app.session_state["cv_text"] = cv
        app.session_state["jd_text"] = jd
        app.run(timeout=20)
        self.assertFalse(app.exception)
        return app

    def click(self, app, text):
        next(button for button in app.button if text in button.label).click().run(timeout=20)
        self.assertFalse(app.exception)

    def markdown(self, app):
        return "\n".join(item.value for item in [*app.markdown, *app.subheader, *app.title])

    def service(self, jd=None, error=None):
        provider = MockProvider(semantic_payload(jd), error)
        return AnalyzerReviewService(settings=Settings(), provider=provider), provider

    def test_submit_cv_without_industry_or_target_then_edit_and_reset(self):
        app = self.app()
        service, provider = self.service()
        self.assertEqual(app.selectbox[0].value, "General / Auto")
        self.assertEqual(app.text_input[0].value, "")
        with patch("frontend.review_ui.AnalyzerReviewService", return_value=service):
            self.click(app, "Analyze CV")
        self.assertEqual(len(provider.calls), 1)
        output = self.markdown(app)
        for text in ("CV score", "Skills with strong evidence", "Skills needing stronger evidence", "Your strengths", "Areas to improve", "Bullet Review", "AI + Basic"):
            self.assertIn(text, output)
        self.assertNotIn("Missing / needs clearer evidence", output)
        self.assertNotIn("Missing skills:", output)
        self.assertNotIn("Job Match Score", output)
        self.click(app, "Edit inputs")
        self.assertEqual(app.text_area[0].value, CV)
        with patch("frontend.review_ui.AnalyzerReviewService", return_value=service):
            self.click(app, "Analyze CV")
        self.click(app, "Analyze another CV")
        self.assertEqual(app.session_state["cv_text"], "")
        self.assertEqual(app.session_state["jd_text"], "")
        self.assertIsNone(app.session_state["analysis_result"])
        self.assertIsNone(app.session_state["review_result"])
        self.assertEqual(app.text_area[0].value, "")

    def test_reanalyze_is_explicit_one_additional_request(self):
        app = self.app()
        service, provider = self.service()
        with patch("frontend.review_ui.AnalyzerReviewService", return_value=service):
            self.click(app, "Analyze CV")
            first = app.session_state["review_result"]
            self.click(app, "Re-analyze")
        self.assertEqual(len(provider.calls), 2)
        self.assertEqual(app.session_state["review_result"].analysis, first.analysis)

    def test_job_match_has_two_scores_and_three_separate_requirement_groups(self):
        app = self.app(jd=JD)
        service, provider = self.service(JD)
        with patch("frontend.review_ui.AnalyzerReviewService", return_value=service):
            self.click(app, "Analyze CV")
        self.assertEqual(len(provider.calls), 1)
        output = self.markdown(app)
        for text in ("CV Quality Score", "Job Match Score", "83/100", "63/100", "Why this match score?", "Matched requirements", "Partially matched requirements", "Missing requirements", "Matched skills:", "Partially matched skills:", "Missing skills:", "Data Analyst"):
            self.assertIn(text, output + "\n".join(item.value for item in app.title))
        self.assertEqual(app.session_state["review_result"].target_role, "Data Analyst")

    def test_cv_too_short_has_clear_error_and_no_ai_request(self):
        app = self.app(cv="Short CV")
        service, provider = self.service()
        with patch("frontend.review_ui.AnalyzerReviewService", return_value=service):
            self.click(app, "Analyze CV")
        self.assertEqual(len(provider.calls), 0)
        self.assertTrue(any("too short" in error.value for error in app.error))

    def test_jd_too_short_can_be_cleared_to_use_cv_review(self):
        app = self.app(jd="Python")
        service, provider = self.service()
        with patch("frontend.review_ui.AnalyzerReviewService", return_value=service):
            self.click(app, "Analyze CV")
            self.assertTrue(any("Job Description" in error.value for error in app.error))
            self.assertEqual(len(provider.calls), 0)
            app.text_area[1].set_value("").run()
            self.click(app, "Analyze CV")
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(app.session_state["review_result"].analysis.mode, "cv_only")

    def test_basic_fallback_and_report_are_available(self):
        app = self.app()
        service, provider = self.service(error=LLMUnavailableError("private provider error"))
        with patch("frontend.review_ui.AnalyzerReviewService", return_value=service):
            self.click(app, "Analyze CV")
        self.assertIn("Basic fallback", self.markdown(app))
        self.assertTrue(any("Full analysis is unavailable" in item.value for item in app.warning))
        self.assertNotIn("private provider error", self.markdown(app))
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(app.get("download_button")[0].label, "Download Report")

    def test_rewrite_is_one_batch_without_additional_gemini_calls(self):
        app = self.app()
        service, provider = self.service()
        with patch("frontend.review_ui.AnalyzerReviewService", return_value=service):
            self.click(app, "Analyze CV")
        selections = [item for item in app.checkbox if item.label == "Select for rewrite"]
        self.assertGreaterEqual(len(selections), 2)
        selections[0].check()
        selections[1].check()
        app.run()
        self.click(app, "Suggest rewrite")
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(len(app.session_state["rewrite_suggestions"]), 2)
        self.assertIn("[verified output or outcome", self.markdown(app))

    def test_unexpected_failure_is_human_readable_and_does_not_expose_exception(self):
        app = self.app()
        with patch("frontend.review_ui.AnalyzerReviewService") as factory:
            factory.return_value.analyze_cv.side_effect = RuntimeError("private-key secret CV")
            self.click(app, "Analyze CV")
        self.assertTrue(any("could not be completed" in item.value for item in app.error))
        self.assertNotIn("private-key", self.markdown(app))

    def test_constructor_error_does_not_expose_a_traceback(self):
        app = self.app()
        with patch("frontend.review_ui.AnalyzerReviewService", side_effect=RuntimeError("private-key")):
            self.click(app, "Analyze CV")
        self.assertTrue(any("could not be completed" in item.value for item in app.error))

    def test_cleanup_error_does_not_discard_a_completed_review(self):
        app = self.app()
        service, _ = self.service()
        with patch("frontend.review_ui.AnalyzerReviewService", return_value=service), patch.object(service, "close", side_effect=RuntimeError("private-key")):
            self.click(app, "Analyze CV")
        self.assertIn("AI + Basic", self.markdown(app))
        self.assertIsNotNone(app.session_state["review_result"])

    def test_new_upload_replaces_a_draft_with_a_fresh_editor(self):
        app = self.app()
        original_key = app.text_area[0].key
        app.text_area[0].set_value("Temporary edited draft").run()
        upload = SimpleNamespace(name="original-cv.txt", getvalue=lambda: CV.encode("utf-8"))
        def file_uploader(label, **kwargs):
            return upload if label == "Upload CV" else None
        with patch("frontend.review_ui.st.file_uploader", side_effect=file_uploader):
            app.run()
        self.assertFalse(app.exception)
        self.assertEqual(app.text_area[0].value, CV.strip())
        self.assertNotEqual(app.text_area[0].key, original_key)
