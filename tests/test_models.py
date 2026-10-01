import unittest

from pydantic import ValidationError

from backend.config import Settings
from backend.models import AISemanticAnalysis, CandidateProfile, RequirementMatch, ScoreBreakdown
from backend.normalization import normalize_skill, skill_in_text, valid_evidence
from tests.helpers import semantic_payload


class ModelTests(unittest.TestCase):
    def test_valid_semantic_model(self):
        self.assertEqual(AISemanticAnalysis.model_validate(semantic_payload()).content_quality.quality, "strong")

    def test_incomplete_semantic_response_rejected(self):
        with self.assertRaises(ValidationError):
            AISemanticAnalysis.model_validate({"candidate_summary": "Student"})

    def test_llm_overall_score_rejected(self):
        payload = semantic_payload()
        payload["overall_score"] = 100
        with self.assertRaises(ValidationError):
            AISemanticAnalysis.model_validate(payload)

    def test_status_normalized_and_invalid_rejected(self):
        self.assertEqual(RequirementMatch(requirement="Python", status=" MATCHED ").status, "matched")
        with self.assertRaises(ValidationError):
            RequirementMatch(requirement="Python", status="perfect")

    def test_score_bounds(self):
        for value in (-1, 101):
            with self.assertRaises(ValidationError):
                ScoreBreakdown(content=value)

    def test_mutable_defaults_are_independent(self):
        first, second = CandidateProfile(), CandidateProfile()
        first.skills.append("Python")
        self.assertEqual(second.skills, [])

    def test_key_not_in_settings_repr(self):
        self.assertNotIn("private-key", repr(Settings(gemini_api_key="private-key")))

    def test_aliases_and_database_distinctions(self):
        for source, expected in [("Python3", "Python"), ("MS Excel", "Excel"),
                                 ("Microsoft Excel", "Excel"), ("PowerBI", "Power BI"),
                                 ("PostgreSQL", "PostgreSQL")]:
            self.assertEqual(normalize_skill(source), expected)
        self.assertFalse(skill_in_text("SQL", "PostgreSQL"))
        self.assertFalse(skill_in_text("R", "Requirements"))

    def test_evidence_validation(self):
        self.assertEqual(valid_evidence(["Built Python", "Invented project"], "Built   Python"), ["Built Python"])
