import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from backend.config import Settings
from backend.exceptions import InvalidCVError, LLMResponseError, LLMUnavailableError
from backend.models import CVAnalysisResult
from backend.providers.gemini_provider import GeminiProvider
from backend.services.analysis_service import AI_FALLBACK_WARNING, AnalysisService
from tests.helpers import CV, JD, POWERBI_QUOTE, MockProvider, document, semantic_payload


class AnalysisServiceTests(unittest.TestCase):
    def service(self, payload=None, error=None):
        return AnalysisService(provider=MockProvider(payload, error))

    def test_cv_only_normalized_and_job_fields_empty(self):
        result = self.service(semantic_payload(None)).analyze_cv(document())
        self.assertIsInstance(result, CVAnalysisResult)
        self.assertEqual(result.mode, "cv_only")
        self.assertTrue(result.ai_available)
        self.assertIsNone(result.scores.job_match)
        self.assertEqual(result.matched_skills + result.missing_skills + result.partially_matched_skills, [])
        self.assertEqual(result.requirement_matches, [])
        self.assertGreaterEqual(result.overall_score, 0)
        self.assertLessEqual(result.overall_score, 100)

    def test_whitespace_jd_is_cv_only(self):
        self.assertEqual(self.service().analyze_cv(document(), " \n").mode, "cv_only")

    def test_job_match_skills_and_partial_requirement(self):
        result = self.service().analyze_cv(document(), JD)
        self.assertEqual(result.mode, "job_match")
        self.assertIn("Python", result.matched_skills)
        self.assertIn("SQL", result.matched_skills)
        self.assertIn("communication", result.missing_skills)
        self.assertIn("Power BI", result.partially_matched_skills)
        duration = next(m for m in result.requirement_matches if "2 years" in m.requirement)
        self.assertEqual(duration.status, "partial")
        self.assertEqual(duration.evidence, [POWERBI_QUOTE])
        self.assertEqual(result.scores.education, 82)
        self.assertEqual(result.scores.experience, 50)
        self.assertEqual(result.scores.job_match, result.overall_score)
        self.assertTrue(result.ai_available)

    def test_failures_fall_back(self):
        for error in (LLMUnavailableError("safe"), LLMResponseError("safe"), TimeoutError(), ConnectionError()):
            with self.subTest(error=type(error).__name__):
                result = self.service(error=error).analyze_cv(document(), JD)
                self.assertFalse(result.ai_available)
                self.assertIn(AI_FALLBACK_WARNING, result.warnings)
                self.assertTrue(result.basic_checks.has_email)
                self.assertIn("Python", result.detected_skills)
                self.assertTrue(result.requirement_matches)
                self.assertGreaterEqual(result.overall_score, 0)
                self.assertLessEqual(result.overall_score, 100)

    def test_missing_key_default_pipeline(self):
        result = AnalysisService(settings=Settings()).analyze_cv(document())
        self.assertFalse(result.ai_available)
        self.assertIsNone(result.analysis_metadata.model)

    def test_malformed_provider_response_fallback_end_to_end(self):
        client = MagicMock()
        client.models.generate_content.return_value = SimpleNamespace(text="broken json")
        provider = GeminiProvider(Settings(gemini_api_key="test-only"), client=client)
        self.assertFalse(AnalysisService(provider=provider).analyze_cv(document(), JD).ai_available)

    def test_invalid_cv_and_input_size(self):
        with self.assertRaises(InvalidCVError):
            self.service().analyze_cv(document(" "))
        with self.assertRaises(InvalidCVError):
            AnalysisService(settings=Settings(max_document_chars=2)).analyze_cv(document())
        with self.assertRaises(InvalidCVError):
            self.service().analyze_cv(document(), jd_text=42)

    def test_missing_jd_skills_never_added_to_candidate(self):
        payload = semantic_payload()
        payload["detected_skills"].extend(["Java", "Kubernetes"])
        result = self.service(payload).analyze_cv(document(), JD + "\nJava required")
        self.assertNotIn("Java", result.detected_skills)
        self.assertNotIn("Kubernetes", result.detected_skills)
        self.assertIn("Java", result.missing_skills)

    def test_hallucinated_evidence_cannot_raise_score(self):
        payload = semantic_payload()
        for judgment in ("content_quality", "skill_quality", "education_quality"):
            payload[judgment]["evidence"] = ["Invented evidence"]
        for match in payload["requirements"]:
            if match["requirement"] == "Python":
                match["evidence"] = ["Invented evidence"]
        result = self.service(payload).analyze_cv(document(), JD)
        python = next(m for m in result.requirement_matches if m.requirement == "Python")
        self.assertEqual(python.status, "missing")
        self.assertEqual(python.evidence, [])
        self.assertEqual(result.scores.content, 0)
        self.assertTrue(any("verifiable" in warning for warning in result.warnings))

    def test_skill_listing_alone_is_partial(self):
        payload = semantic_payload("Python required")
        payload["requirements"][0] = {"requirement": "Python", "status": "matched", "evidence": ["Python"]}
        result = self.service(payload).analyze_cv(document("Skills\nPython"), "Python required")
        self.assertEqual(result.requirement_matches[0].status, "partial")
        self.assertEqual(result.overall_score, 50)

    def test_project_does_not_fulfill_professional_years(self):
        payload = semantic_payload()
        match = next(m for m in payload["requirements"] if "2 years" in m["requirement"])
        match["status"] = "matched"
        result = self.service(payload).analyze_cv(document(), JD)
        self.assertEqual(next(m for m in result.requirement_matches if "2 years" in m.requirement).status, "partial")

    def test_recommendations_use_safe_backend_actions(self):
        payload = semantic_payload()
        payload["recommendations"] = [{"priority": 1, "category": "experience", "title": "Invent a job",
            "reason": "Invent metrics", "action": "Add five years of work and 200% growth.",
            "evidence": [POWERBI_QUOTE]}]
        result = self.service(payload).analyze_cv(document(), JD)
        self.assertNotIn("200%", json.dumps([r.model_dump() for r in result.recommendations]))
        self.assertNotIn("Invent", json.dumps([r.model_dump() for r in result.recommendations]))
        gap = next(r for r in result.recommendations if "communication" in r.title)
        self.assertIn("If you genuinely", gap.action)

    def test_ai_cannot_add_requirements_outside_jd(self):
        payload = semantic_payload()
        payload["requirements"].append({"requirement": "Kubernetes", "status": "missing", "evidence": []})
        self.assertFalse(any(m.requirement == "Kubernetes" for m in self.service(payload).analyze_cv(document(), JD).requirement_matches))

    def test_omitted_and_duplicate_requirements_use_local_evidence(self):
        payload = semantic_payload()
        payload["requirements"] = [payload["requirements"][1]] * 3
        result = self.service(payload).analyze_cv(document(), JD)
        self.assertEqual(next(m for m in result.requirement_matches if m.requirement == "Python").status, "matched")
        self.assertEqual(next(m for m in result.requirement_matches if m.requirement == "SQL").status, "matched")

    def test_low_extraction_warning_survives_ai(self):
        doc = document()
        doc.extraction_quality = "low"
        result = self.service().analyze_cv(doc)
        self.assertIn(result.basic_checks.extraction_warning, result.warnings)

    def test_serialization_round_trip_and_metadata(self):
        result = self.service().analyze_cv(document(), JD)
        self.assertEqual(CVAnalysisResult.model_validate_json(result.model_dump_json()), result)
        self.assertEqual(result.analysis_metadata.model, "mock-model")
        self.assertAlmostEqual(sum(result.analysis_metadata.effective_weights.values()), 1)

    def test_no_ui_dependency_and_no_sensitive_logging(self):
        from pathlib import Path
        for path in Path("backend").rglob("*.py"):
            self.assertNotIn("import streamlit", path.read_text(encoding="utf-8"))
        with self.assertLogs("backend", level="INFO") as logs:
            self.service(error=LLMUnavailableError("student@example.test private-key")).analyze_cv(document(), JD)
        output = " ".join(logs.output)
        self.assertNotIn("student@example.test", output)
        self.assertNotIn("private-key", output)

    def test_fallback_explicit_years_and_field(self):
        result = self.service(error=LLMUnavailableError()).analyze_cv(
            document("Experience\n3 years Power BI professional experience\nEducation\nBachelor degree in History"),
            "2 years Power BI experience required\nBachelor degree in Computer Science required")
        self.assertEqual(result.requirement_matches[0].status, "matched")
        self.assertEqual(result.requirement_matches[1].status, "partial")

    def test_unrelated_work_not_evidence_of_required_skill(self):
        result = self.service(error=LLMUnavailableError()).analyze_cv(
            document("Experience\n3 years selling products"), "2 years Power BI experience")
        self.assertEqual(result.requirement_matches[0].status, "missing")
        self.assertEqual(result.requirement_matches[0].evidence, [])

    def test_fallback_uses_relevant_project_quote_for_duration(self):
        result = self.service(error=LLMUnavailableError()).analyze_cv(document(), "2 years Power BI experience")
        self.assertEqual(result.requirement_matches[0].status, "partial")
        self.assertEqual(result.requirement_matches[0].evidence, [POWERBI_QUOTE])
