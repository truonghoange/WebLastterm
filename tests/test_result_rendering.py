from pathlib import Path
import unittest

from streamlit.testing.v1 import AppTest

from backend.config import Settings
from backend.models import ScoreBreakdown
from backend.services.analysis_service import AnalysisService
from backend.services.scoring_service import ScoringService
from backend.services.analyzer_review_service import AnalyzerReviewService
from constants import CV_SCORE_LABELS
from tests.helpers import JD, MockProvider, document, semantic_payload


class ResultRenderingTests(unittest.TestCase):
    def result(self, jd=None):
        return AnalyzerReviewService(settings=Settings(), provider=MockProvider(semantic_payload(jd))).analyze_cv(document(), jd)

    def render(self, result):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"))
        app.session_state["page"] = "Results"
        app.session_state["analysis_result"] = result.analysis
        app.session_state["review_result"] = result
        app.session_state["cv_document"] = document()
        app.run(timeout=20)
        self.assertFalse(app.exception)
        return "\n".join(item.value for item in app.markdown)

    def test_cv_only_shows_quality_label_and_correct_result_field(self):
        result = self.result()
        output = self.render(result)
        self.assertIn("CV score", output)
        self.assertIn(f"{result.analysis.overall_score}/100", output)
        self.assertIn("🟢 Strong", output)
        self.assertNotIn("Very Strong Match", output)
        self.assertNotIn("Match score", output)

    def test_reported_input_renders_the_recomputed_overall_and_breakdown(self):
        scores = ScoreBreakdown(content=100, skills=100, experience=25,
                                education=100, structure=100, projects=100)
        scoring = ScoringService().score_cv_only(scores)
        result = self.result()
        result.analysis.overall_score = scoring.overall_score
        result.analysis.scores = scoring.scores
        result.cv_quality = scoring
        output = self.render(result)
        self.assertIn('class="cv-metric">91/100', output)
        self.assertIn("🟢 Exceptional", output)
        self.assertIn("**Experience** · 25/100", output)
        self.assertIn("**Projects** · 100/100", output)
        self.assertNotIn("Very Strong Match", output)

    def test_job_match_keeps_separate_match_labels(self):
        result = self.result(JD)
        output = self.render(result)
        self.assertIn("Job Match Score", output)
        self.assertIn("CV Quality Score", output)
        self.assertIn(f"{result.analysis.overall_score}/100", output)
        self.assertIn("Moderate Match", output)
        self.assertNotIn("CV score", output)

    def test_cv_quality_bands_cover_all_scores_exactly_once(self):
        examples = {0: "Needs Improvement", 59: "Needs Improvement", 60: "Fair", 69: "Fair",
                    70: "Solid", 79: "Solid", 80: "Strong", 89: "Strong", 90: "Exceptional", 100: "Exceptional"}
        for score in range(101):
            labels = [label for lo, hi, label, _ in CV_SCORE_LABELS if lo <= score <= hi]
            self.assertEqual(len(labels), 1)
            self.assertNotIn("Match", labels[0])
            if score in examples:
                self.assertEqual(labels[0], examples[score])
