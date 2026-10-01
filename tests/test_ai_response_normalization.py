import json
import unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pydantic import ValidationError

from backend.ai_response_models import AISemanticResponse
from backend.analyzers.gemini_analyzer import GeminiAnalyzer
from backend.config import Settings
from backend.exceptions import LLMResponseError
from backend.models import AISemanticAnalysis, CVAnalysisResult, RequirementMatch
from backend.normalization import normalize_ai_response, normalize_requirement_status
from backend.providers.gemini_provider import GeminiProvider
from backend.providers.response_schema import build_gemini_schema
from backend.services.analysis_service import AnalysisService
from tests.helpers import JD, MockProvider, document, semantic_payload


class AIResponseNormalizationTests(unittest.TestCase):
    def normalize(self, payload=None, job_match=True):
        return normalize_ai_response(AISemanticResponse.model_validate(payload or semantic_payload()), job_match=job_match)

    def test_matched_status(self):
        self.assertEqual(normalize_requirement_status("matched"), "matched")

    def test_partially_matched_status(self):
        payload = semantic_payload()
        payload["requirements"][0]["status"] = "partially_matched"
        self.assertEqual(self.normalize(payload).requirements[0].status, "partial")

    def test_fully_matched_status(self):
        payload = semantic_payload()
        payload["requirements"][0]["status"] = "fully_matched"
        self.assertEqual(self.normalize(payload).requirements[0].status, "matched")

    def test_not_demonstrated_status(self):
        payload = semantic_payload()
        payload["requirements"][0]["status"] = "not_demonstrated"
        self.assertEqual(self.normalize(payload).requirements[0].status, "missing")

    def test_all_requested_status_aliases(self):
        groups = {"matched": ["matched", "match", "fully_matched", "clearly_demonstrated"],
                  "partial": ["partial", "partially_matched", "partially_demonstrated", "some_evidence"],
                  "missing": ["missing", "not_found", "not_demonstrated", "no_evidence", "unknown"]}
        for expected, values in groups.items():
            for value in values:
                with self.subTest(value=value):
                    self.assertEqual(normalize_requirement_status(value), expected)
        self.assertEqual(normalize_requirement_status(" FULLY-MATCHED "), "matched")
        self.assertEqual(normalize_requirement_status("some evidence"), "partial")

    def test_unknown_null_or_omitted_status_is_missing(self):
        for status in ("unknown", None):
            self.assertEqual(normalize_requirement_status(status), "missing")
        payload = semantic_payload()
        del payload["requirements"][0]["status"]
        self.assertEqual(self.normalize(payload).requirements[0].status, "missing")

    def test_arbitrary_status_is_a_safe_error(self):
        with self.assertRaises(LLMResponseError):
            normalize_requirement_status("perfect")

    def test_null_evidence_at_all_nesting_levels(self):
        payload = semantic_payload()
        payload["requirements"][0]["evidence"] = None
        payload["content_quality"]["evidence"] = None
        payload["recommendations"] = [{"category": "skills", "evidence": None}]
        result = self.normalize(payload)
        self.assertEqual(result.requirements[0].evidence, [])
        self.assertEqual(result.content_quality.evidence, [])
        self.assertEqual(result.recommendations[0].evidence, [])

    def test_omitted_evidence_at_all_nesting_levels(self):
        payload = semantic_payload()
        del payload["requirements"][0]["evidence"]
        del payload["content_quality"]["evidence"]
        payload["recommendations"] = [{"category": "skills"}]
        result = self.normalize(payload)
        self.assertEqual(result.requirements[0].evidence, [])
        self.assertEqual(result.content_quality.evidence, [])
        self.assertEqual(result.recommendations[0].evidence, [])

    def test_all_omitted_list_fields_default_to_empty(self):
        payload = semantic_payload()
        for field in ("detected_skills", "strengths", "weaknesses", "requirements", "recommendations"):
            del payload[field]
        result = self.normalize(payload)
        for field in ("detected_skills", "strengths", "weaknesses", "requirements", "recommendations"):
            self.assertEqual(getattr(result, field), [])

    def test_all_null_list_fields_normalize_to_empty(self):
        payload = semantic_payload()
        for field in ("detected_skills", "strengths", "weaknesses", "requirements", "recommendations"):
            payload[field] = None
        result = self.normalize(payload)
        for field in ("detected_skills", "strengths", "weaknesses", "requirements", "recommendations"):
            self.assertEqual(getattr(result, field), [])

    def test_omitted_and_null_optional_semantic_fields(self):
        payload = semantic_payload(None)
        for field in ("role_relevance", "experience_relevance", "project_relevance", "education_relevance"):
            payload.pop(field, None)
        payload["project_quality"] = None
        del payload["experience_quality"]
        result = self.normalize(payload, job_match=False)
        self.assertIsNone(result.role_relevance)
        self.assertIsNone(result.experience_relevance)
        self.assertEqual(result.project_quality.quality, "unknown")
        self.assertEqual(result.experience_quality.quality, "unknown")
        self.assertEqual(result.requirements, [])

    def test_cv_only_clears_job_specific_fields(self):
        result = self.normalize(semantic_payload(), job_match=False)
        self.assertEqual(result.requirements, [])
        self.assertIsNone(result.experience_relevance)
        self.assertIsNone(result.education_relevance)

    def test_bare_quality_and_labels_normalize(self):
        payload = semantic_payload()
        payload["content_quality"] = " STRONG "
        payload["project_quality"]["quality"] = "medium"
        result = self.normalize(payload)
        self.assertEqual(result.content_quality.quality, "strong")
        self.assertEqual(result.content_quality.evidence, [])
        self.assertEqual(result.project_quality.quality, "adequate")

    def test_new_levels_and_legacy_aliases_normalize_to_strict_scale(self):
        for value, expected in (("exceptional", "exceptional"), ("strong", "strong"),
                                ("adequate", "adequate"), ("limited", "limited"),
                                ("weak", "weak"), ("insufficient", "insufficient"),
                                ("moderate", "adequate"), ("medium", "adequate"), ("high", "strong")):
            payload = semantic_payload()
            payload["content_quality"]["quality"] = value
            with self.subTest(value=value):
                self.assertEqual(self.normalize(payload).content_quality.quality, expected)

    def test_priorities_clamped_and_optional_advice_defaults(self):
        payload = semantic_payload()
        payload["recommendations"] = [{"category": "SKILLS", "priority": 50}, {"category": "skills", "priority": None}]
        result = self.normalize(payload)
        self.assertEqual([r.priority for r in result.recommendations], [10, 3])
        self.assertTrue(all(isinstance(r.action, str) for r in result.recommendations))
        self.assertEqual(result.recommendations[0].category, "skills")

    def test_invalid_list_or_element_still_rejected(self):
        for value in ("Python", {"skill": "Python"}, [42], [None]):
            payload = semantic_payload()
            payload["detected_skills"] = value
            with self.subTest(value=value), self.assertRaises(ValidationError):
                AISemanticResponse.model_validate(payload)

    def test_list_defaults_are_independent(self):
        first = AISemanticResponse(candidate_summary="Synthetic summary")
        second = AISemanticResponse(candidate_summary="Synthetic summary")
        first.detected_skills.append("Python")
        self.assertEqual(second.detected_skills, [])

    def test_strict_internal_status_never_accepts_aliases_or_arbitrary_values(self):
        for value in ("fully_matched", "partially_matched", "not_demonstrated", "perfect", "unknown"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                RequirementMatch(requirement="Python", status=value)
        match = RequirementMatch(requirement="Python", status="matched")
        with self.assertRaises(ValidationError):
            match.status = "arbitrary"

    def test_internal_lists_stay_strict(self):
        payload = semantic_payload()
        payload["detected_skills"] = None
        with self.assertRaises(ValidationError):
            AISemanticAnalysis.model_validate(payload)

    def test_final_internal_result_stays_strict(self):
        result = AnalysisService(provider=MockProvider()).analyze_cv(document(), JD)
        payload = result.model_dump()
        payload["requirement_matches"][0]["status"] = "fully_matched"
        with self.assertRaises(ValidationError):
            CVAnalysisResult.model_validate(payload)

    def test_llm_score_never_enters_internal_model(self):
        payload = semantic_payload()
        payload["overall_score"] = 999
        result = self.normalize(payload)
        self.assertNotIn("overall_score", result.model_dump())

    def test_response_without_semantic_signals_is_invalid(self):
        for payload in ({"candidate_summary": "Summary only"}, {"candidate_summary": "", "content_quality": "unknown"}):
            with self.subTest(payload=payload), self.assertRaises(LLMResponseError):
                self.normalize(payload)


class TwoStagePipelineTests(unittest.TestCase):
    def run_pipeline(self, payload, jd=JD):
        client = MagicMock()
        client.models.generate_content.return_value = SimpleNamespace(text=json.dumps(payload))
        provider = GeminiProvider(Settings(gemini_api_key="test-only"), client=client)
        return AnalysisService(provider=provider).analyze_cv(document(), jd), client

    def test_variations_go_through_actual_provider_normalizer_service(self):
        for status, expected in (("matched", "matched"), ("fully_matched", "matched"),
                                 ("partially_matched", "partial"), ("not_demonstrated", "missing")):
            payload = semantic_payload()
            next(item for item in payload["requirements"] if item["requirement"] == "SQL")["status"] = status
            for field in ("strengths", "weaknesses", "recommendations"):
                payload.pop(field, None)
            with self.subTest(status=status):
                result, client = self.run_pipeline(payload)
                self.assertTrue(result.ai_available)
                self.assertEqual(next(r for r in result.requirement_matches if r.requirement == "SQL").status, expected)
                client.models.generate_content.assert_called_once()

    def test_null_evidence_keeps_ai_available_but_cannot_raise_score(self):
        payload = semantic_payload()
        next(item for item in payload["requirements"] if item["requirement"] == "SQL")["evidence"] = None
        result, _ = self.run_pipeline(payload)
        self.assertTrue(result.ai_available)
        self.assertEqual(next(r for r in result.requirement_matches if r.requirement == "SQL").status, "missing")

    def test_cv_only_omissions_do_not_trigger_fallback(self):
        payload = semantic_payload(None)
        for field in ("role_relevance", "experience_relevance", "education_relevance", "project_relevance",
                      "requirements", "recommendations", "strengths", "weaknesses", "detected_skills"):
            payload.pop(field, None)
        result, _ = self.run_pipeline(payload, jd=None)
        self.assertTrue(result.ai_available)
        self.assertEqual(result.mode, "cv_only")
        self.assertEqual(result.requirement_matches, [])

    def test_raw_ai_score_is_ignored_and_service_owns_the_calibrated_score(self):
        payload = semantic_payload(None)
        payload["overall_score"] = 100
        payload["experience_quality"]["quality"] = "weak"
        result, client = self.run_pipeline(payload, jd=None)
        self.assertTrue(result.ai_available)
        self.assertEqual(result.mode, "cv_only")
        self.assertIsNone(result.scores.job_match)
        self.assertEqual(result.scores.content, 82)
        self.assertEqual(result.scores.experience, 35)
        self.assertEqual(result.scores.projects, 82)
        self.assertEqual(result.overall_score, 79)
        metadata = result.analysis_metadata
        self.assertEqual(metadata.scoring_version, "2.0")
        self.assertAlmostEqual(sum(metadata.effective_weights.values()), 1.0)
        self.assertEqual(metadata.scoring_components, result.scores.model_dump(exclude_none=True))
        expected = round(sum(metadata.scoring_components[k] * w for k, w in metadata.effective_weights.items()))
        self.assertEqual(result.overall_score, expected)
        client.models.generate_content.assert_called_once()

    def test_all_exceptional_still_does_not_produce_100(self):
        payload = semantic_payload(None)
        for field in ("content_quality", "skill_quality", "experience_quality", "project_quality", "education_quality"):
            payload[field]["quality"] = "exceptional"
        result, _ = self.run_pipeline(payload, jd=None)
        self.assertTrue(result.ai_available)
        self.assertEqual(result.overall_score, 93)

    def test_exceptional_without_evidence_is_not_credited(self):
        payload = semantic_payload(None)
        payload["experience_quality"] = {"quality": "exceptional", "evidence": None}
        result, _ = self.run_pipeline(payload, jd=None)
        self.assertTrue(result.ai_available)
        self.assertEqual(result.scores.experience, 0)
        self.assertEqual(result.overall_score, 74)

    def test_invalid_wire_and_internal_normalization_trigger_controlled_fallback(self):
        invalid_wire = semantic_payload()
        invalid_wire["requirements"][0]["evidence"] = {"invented": "shape"}
        unknown_status = semantic_payload()
        unknown_status["requirements"][0]["status"] = "perfect"
        empty_requirement = semantic_payload()
        empty_requirement["requirements"][0]["requirement"] = " "
        for payload in ({}, [], {"candidate_summary": "Summary only"}, invalid_wire, unknown_status, empty_requirement):
            with self.subTest(payload=payload):
                with self.assertLogs("backend", level="WARNING") as logs:
                    result, client = self.run_pipeline(payload)
                self.assertFalse(result.ai_available)
                self.assertTrue(result.basic_checks.has_email)
                self.assertTrue(any("AI schema validation failed" in line for line in logs.output))
                client.models.generate_content.assert_called_once()

    def test_wire_and_internal_errors_log_models_fields_without_values(self):
        wire = semantic_payload()
        wire["requirements"][0]["evidence"] = "private student@example.test"
        internal = semantic_payload()
        internal["requirements"][0]["requirement"] = ""
        for payload, stage, model, field in (
            (wire, "response_model", "AISemanticResponse", "evidence"),
            (internal, "internal_model", "AISemanticAnalysis", "requirement"),
        ):
            with self.subTest(stage=stage), self.assertLogs("backend", level="WARNING") as logs:
                result, _ = self.run_pipeline(payload)
            text = " ".join(logs.output)
            self.assertFalse(result.ai_available)
            self.assertIn(stage, text)
            self.assertIn(model, text)
            self.assertIn(field, text)
            self.assertNotIn("student@example.test", text)


class GeminiWireSchemaTests(unittest.TestCase):
    def test_outgoing_schema_is_simple_and_canonical(self):
        schema = build_gemini_schema(AISemanticResponse)
        unsupported = {"$defs", "$ref", "anyOf", "oneOf", "allOf", "default", "additionalProperties", "minLength"}

        def walk(node):
            if isinstance(node, dict):
                self.assertFalse(unsupported.intersection(node))
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)

        walk(schema)
        self.assertEqual(schema["properties"]["content_quality"]["type"], "object")
        self.assertTrue(schema["properties"]["role_relevance"]["nullable"])
        self.assertEqual(schema["properties"]["requirements"]["type"], "array")
        self.assertEqual(schema["required"], ["candidate_summary"])

    def test_schema_projection_never_changes_internal_schema(self):
        before = deepcopy(AISemanticAnalysis.model_json_schema())
        build_gemini_schema(AISemanticResponse)
        self.assertEqual(AISemanticAnalysis.model_json_schema(), before)

    def test_real_sdk_request_serialization_with_mocked_http(self):
        # Uses the installed SDK's complete request/response path. HTTP alone is
        # mocked; this is an offline compatibility test, not a live API claim.
        from google import genai
        response = semantic_payload()
        next(item for item in response["requirements"] if item["requirement"] == "SQL")["status"] = "fully_matched"
        body = {"candidates": [{"content": {"role": "model", "parts": [{"text": json.dumps(response)}]},
                                "finishReason": "STOP"}]}
        client = genai.Client(api_key="test-only")
        provider = GeminiProvider(Settings(gemini_api_key="test-only"), client=client)
        try:
            with patch.object(client._api_client, "request", return_value=SimpleNamespace(body=json.dumps(body), headers={})) as request:
                result = AnalysisService(provider=provider).analyze_cv(document(), JD)
            self.assertTrue(result.ai_available)
            self.assertEqual(result.matched_skills, ["Python", "SQL"])
            request.assert_called_once()
            sent = request.call_args.args[2]
            self.assertEqual(sent["generationConfig"]["responseSchema"]["type"], "OBJECT")
            self.assertNotIn("$defs", json.dumps(sent["generationConfig"]["responseSchema"]))
        finally:
            provider.close()
