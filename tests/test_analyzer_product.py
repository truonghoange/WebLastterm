import re
import unittest
from unittest.mock import patch

from backend.config import Settings
from backend.exceptions import InvalidCVError, LLMUnavailableError
from backend.models import CVDocument
from backend.normalization import valid_evidence
from backend.services.analysis_service import AnalysisService
from backend.services.analyzer_review_service import AnalyzerReviewService, classify_skills
from backend.services.bullet_review_service import review_bullets, rewrite_bullets
from backend.services.report_service import generate_report
from tests.helpers import CV, JD, MockProvider, document, semantic_payload

STUDENT_CV = """Alex Example
Data Analyst Intern
alex@example.test | +84 912 345 678
Education
Current Bachelor of Information Technology, AI and Data coursework.
Projects
Data pipeline
• Built a data pipeline using Python, SQL, Pandas and FastAPI.
• Integrated Python processing with SQL storage and a FastAPI service.
Forecasting
• Evaluated a time-series forecasting model using Python and NumPy with chronological validation and RMSLE.
Skills
Python, SQL, Pandas, NumPy, FastAPI, Docker
"""


class AnalyzerProductTests(unittest.TestCase):
    def review(self, jd=None, payload=None, error=None, **options):
        provider = MockProvider(payload or semantic_payload(jd), error)
        service = AnalyzerReviewService(settings=Settings(), provider=provider)
        return service.analyze_cv(document(), jd, **options), provider

    def test_cv_review_keeps_original_score_and_makes_one_ai_call(self):
        review, provider = self.review()
        baseline = AnalysisService(settings=Settings(), provider=MockProvider(semantic_payload(None))).analyze_cv(document())
        self.assertEqual(review.analysis, baseline)
        self.assertEqual(review.cv_quality.overall_score, 83)
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(review.requirement_groups.matched + review.requirement_groups.partial + review.requirement_groups.missing, [])

    def test_job_match_keeps_original_score_and_separate_cv_quality(self):
        review, provider = self.review(JD)
        baseline = AnalysisService(settings=Settings(), provider=MockProvider()).analyze_cv(document(), JD)
        self.assertEqual(review.analysis, baseline)
        self.assertEqual(review.analysis.overall_score, 63)
        self.assertEqual(review.cv_quality.overall_score, 83)
        self.assertNotEqual(review.cv_quality.overall_score, review.analysis.overall_score)
        self.assertEqual(len(provider.calls), 1)

    def test_fallback_keeps_original_cv_and_job_scores(self):
        for jd in (None, JD):
            with self.subTest(jd=bool(jd)):
                error = LLMUnavailableError("safe")
                review, provider = self.review(jd, error=error)
                baseline = AnalysisService(settings=Settings(), provider=MockProvider(error=error)).analyze_cv(document(), jd)
                self.assertEqual(review.analysis, baseline)
                self.assertFalse(review.analysis.ai_available)
                self.assertTrue(review.skill_evidence)
                self.assertEqual(len(provider.calls), 1)

    def test_skill_evidence_distinguishes_multiple_single_and_listed_use(self):
        doc = CVDocument(raw_text=STUDENT_CV)
        items = {item.skill: item for item in classify_skills(doc, ["Python", "NumPy", "Docker"])}
        self.assertEqual(items["Python"].strength, "strong_evidence")
        self.assertEqual(items["NumPy"].strength, "some_evidence")
        self.assertEqual(items["Docker"].strength, "mention_only")
        self.assertEqual(items["Docker"].evidence, [])
        self.assertTrue(items["Docker"].mention_evidence)
        for item in items.values():
            self.assertEqual(valid_evidence(item.evidence, doc.raw_text), item.evidence)

    def test_repeated_quotes_do_not_become_strong_evidence(self):
        doc = document("Education\nBachelor degree\nProjects\n• Built a Python pipeline.\n• Built a Python pipeline.\nSkills\nPython")
        item = classify_skills(doc, ["Python"])[0]
        self.assertEqual(item.strength, "some_evidence")

    def test_existing_semantic_evidence_is_reused_without_new_request(self):
        review, provider = self.review()
        python = next(item for item in review.skill_evidence if item.skill == "Python")
        self.assertIn("Built data analysis project using Python.", python.evidence)
        self.assertEqual(len(provider.calls), 1)

    def test_three_requirement_states_stay_separate(self):
        review, _ = self.review(JD)
        for name in ("matched", "partial", "missing"):
            matches = getattr(review.requirement_groups, name)
            self.assertTrue(matches)
            self.assertTrue(all(match.status == name for match in matches))
        flattened = sum((getattr(review.requirement_groups, name) for name in ("matched", "partial", "missing")), [])
        self.assertCountEqual(flattened, review.analysis.requirement_matches)

    def test_no_industry_or_target_is_valid(self):
        review, _ = self.review(industry=None, target_position=None)
        self.assertEqual(review.analysis.mode, "cv_only")
        self.assertEqual(review.industry, "General / Auto")
        self.assertIsNone(review.analysis.scores.job_match)

    def test_cv_industry_is_presentation_only(self):
        first, first_provider = self.review(industry="Finance")
        second, second_provider = self.review(industry="Data Analyst")
        self.assertEqual(first.analysis, second.analysis)
        self.assertEqual(first_provider.calls[0][0], second_provider.calls[0][0])
        self.assertIn('"industry": null', first_provider.calls[0][0])

    def test_user_role_and_jd_title_fallback(self):
        review, _ = self.review(JD)
        self.assertEqual(review.target_role, "Data Analyst")
        review, _ = self.review(JD, target_position="Data Analyst Intern")
        self.assertEqual(review.target_role, "Data Analyst Intern")

    def test_cv_headline_fallback(self):
        provider = MockProvider(semantic_payload(None))
        service = AnalyzerReviewService(settings=Settings(), provider=provider)
        review = service.analyze_cv(CVDocument(raw_text=STUDENT_CV))
        self.assertEqual(review.target_role, "Data Analyst Intern")

    def test_recommendations_are_at_most_three_and_strengths_at_most_five(self):
        review, _ = self.review(JD)
        self.assertEqual(len(review.top_recommendations), 3)
        self.assertGreaterEqual(len(review.strengths), 3)
        self.assertLessEqual(len(review.strengths), 5)

    def test_improvement_areas_have_reason_and_action(self):
        review, _ = self.review()
        self.assertTrue(review.improvement_areas)
        for item in review.improvement_areas:
            self.assertTrue(item.issue and item.why_it_matters and item.recommended_action)

    def test_bullet_review_preserves_implementation_and_recognizes_evaluation(self):
        reviews = review_bullets(CVDocument(raw_text=STUDENT_CV))
        self.assertEqual(len(reviews), 3)
        self.assertTrue(any("outcome" in issue for issue in reviews[0].issues))
        self.assertFalse(any("outcome" in issue for issue in reviews[2].issues))
        self.assertTrue(all("Forecasting" not in item.original for item in reviews))

    def test_batched_rewrite_preserves_facts_and_never_fabricates_metrics(self):
        context = CVDocument(raw_text=STUDENT_CV)
        originals = [item.original for item in review_bullets(context)[:2]]
        with patch("backend.providers.gemini_provider.GeminiProvider.analyze") as ai:
            result = rewrite_bullets(originals, context)
        ai.assert_not_called()
        self.assertEqual(len(result), 2)
        for item in result:
            self.assertIn(item.original.rstrip(" ."), item.rewrite)
            self.assertEqual(re.findall(r"\d+(?:\.\d+)?", item.rewrite), re.findall(r"\d+(?:\.\d+)?", item.original))
            self.assertTrue(item.requires_user_input)
            self.assertIn("[", item.rewrite)

    def test_rewrite_rejects_bullets_not_in_the_cv(self):
        with self.assertRaises(InvalidCVError):
            rewrite_bullets(["Processed 1 million rows"], CVDocument(raw_text=STUDENT_CV))

    def test_too_short_cv_and_jd_fail_before_ai(self):
        provider = MockProvider()
        service = AnalyzerReviewService(settings=Settings(), provider=provider)
        for doc, jd in ((document("Too short"), None), (document(), "Python"),
                        (document(), "Requirements\nResponsibilities\nQualifications")):
            with self.subTest(jd=jd), self.assertRaises(InvalidCVError):
                service.analyze_cv(doc, jd)
        self.assertEqual(provider.calls, [])

    def test_technical_warnings_have_human_readable_presentation(self):
        payload = semantic_payload(None)
        payload["skill_quality"]["evidence"] = ["Not actually in CV"]
        review, _ = self.review(payload=payload)
        self.assertTrue(any("AI judgments lacked" in text for text in review.analysis.warnings))
        self.assertTrue(any("Some suggestions were excluded" in text for text in review.display_warnings))
        self.assertFalse(any("AI judgments lacked" in text for text in review.display_warnings))

    def test_report_contains_cv_sections_and_no_internal_metadata(self):
        review, _ = self.review()
        report = generate_report(review)
        for text in ("CV Score: 83/100", "CV score breakdown", "Your strengths", "Areas to improve", "Skills evidence", "Fix these first", "Bullet Review"):
            self.assertIn(text, report)
        for text in ("Gemini", "prompt_version", "scoring_version", "effective_weights", "mock-model", "Job Match Score"):
            self.assertNotIn(text, report)

    def test_summary_does_not_repeat_a_long_tool_inventory(self):
        payload = semantic_payload(None)
        payload["candidate_summary"] = "Candidate knows Python, SQL, Pandas, Power BI, PostgreSQL, Java and NumPy."
        review, _ = self.review(payload=payload)
        self.assertNotIn("Candidate knows", review.summary)
        self.assertIn("technical projects", review.summary)

    def test_invalid_document_has_a_controlled_input_error(self):
        service = AnalyzerReviewService(settings=Settings(), provider=MockProvider())
        with self.assertRaises(InvalidCVError):
            service.analyze_cv("not a CVDocument")

    def test_job_report_keeps_both_scores_and_three_requirement_groups(self):
        review, _ = self.review(JD)
        report = generate_report(review)
        for text in ("CV Quality Score: 83/100", "Job Match Score: 63/100", "Matched requirements", "Partial requirements", "Missing requirements"):
            self.assertIn(text, report)
