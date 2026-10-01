import unittest

from backend.analyzers.basic_analyzer import BasicAnalyzer
from backend.config import CV_ONLY_WEIGHTS, JOB_MATCH_WEIGHTS, QUALITY_POINTS
from backend.models import AISemanticAnalysis, RequirementMatch, ScoreBreakdown
from backend.parsers.cv_parser import CVParser
from backend.parsers.jd_parser import JDParser
from backend.services.scoring_service import ScoringService, bounded
from tests.helpers import document, semantic_payload


class ScoringTests(unittest.TestCase):
    def setUp(self):
        self.profile = CVParser().parse(document())
        self.checks = BasicAnalyzer().analyze(document(), self.profile)
        self.semantic = AISemanticAnalysis.model_validate(semantic_payload())
        self.scorer = ScoringService()

    def test_cv_only_exact_weights(self):
        result = self.scorer.score(self.profile, self.checks, self.semantic)
        self.assertEqual(result.overall_score, 83)  # 82*.725 + 70*.125 + 100*.15
        self.assertEqual(result.components["experience"], 70)
        self.assertEqual(result.components["projects"], 82)
        self.assertEqual(result.effective_weights, CV_ONLY_WEIGHTS)
        self.assertIsNone(result.scores.job_match)
        self.assertAlmostEqual(sum(result.effective_weights.values()), 1)

    def test_missing_match_is_zero_and_no_keyword_double_count(self):
        jd = JDParser().parse("Python required; SQL required")
        matches = [RequirementMatch(requirement="Python", status="matched"), RequirementMatch(requirement="SQL", status="missing")]
        result = self.scorer.score(self.profile, self.checks, jd=jd, matches=matches)
        self.assertEqual(result.overall_score, 50)
        self.assertEqual(result.effective_weights, {"hard_skills": 1.0})

    def test_partial_credit(self):
        jd = JDParser().parse("Python required")
        result = self.scorer.score(self.profile, self.checks, jd=jd,
            matches=[RequirementMatch(requirement="Python", status="partial")])
        self.assertEqual(result.overall_score, 50)

    def test_preferred_is_lower_weight(self):
        jd = JDParser().parse("Python required; SQL preferred")
        matches = [RequirementMatch(requirement="Python", status="matched"), RequirementMatch(requirement="SQL", status="missing")]
        self.assertEqual(self.scorer.score(self.profile, self.checks, jd=jd, matches=matches).overall_score, 67)

    def test_experience_and_education_relevance_affect_score(self):
        jd = JDParser().parse("2 years Power BI experience\nBachelor degree in Computer Science")
        matches = [RequirementMatch(requirement=r.requirement, status="matched") for r in jd.requirements]
        result = self.scorer.score(self.profile, self.checks, self.semantic, jd, matches)
        self.assertEqual(result.scores.experience, 70)
        self.assertEqual(result.scores.education, 82)
        self.assertEqual(result.overall_score, 74)

    def test_high_semantic_rating_cannot_override_missing_requirement(self):
        jd = JDParser().parse("2 years experience")
        matches = [RequirementMatch(requirement=jd.requirements[0].requirement, status="missing")]
        self.assertEqual(self.scorer.score(self.profile, self.checks, self.semantic, jd, matches).overall_score, 0)

    def test_weights_replaceable(self):
        weights = dict(self.scorer.cv_weights)
        weights.update(content=1, experience=0, projects=0, skills=0, structure=0, education=0)
        self.assertEqual(ScoringService(cv_weights=weights).score(self.profile, self.checks, self.semantic).effective_weights, {"content": 1.0})

    def test_all_job_components_use_declared_weights(self):
        jd = JDParser().parse("Data Analyst\nPython required\n2 years Python experience\nPython project required\nBachelor degree required\nCommunication required")
        statuses = {"hard_skill": "matched", "experience": "partial", "project": "matched",
                    "education": "matched", "role": "missing", "other": "missing"}
        matches = [RequirementMatch(requirement=r.requirement, status=statuses[r.category]) for r in jd.requirements]
        result = self.scorer.score(self.profile, self.checks, jd=jd, matches=matches)
        self.assertEqual(result.overall_score, 70)  # 35 + 10 + 15 + 10 + 0 + 0
        self.assertEqual(result.effective_weights, self.scorer.job_weights)

    def test_invalid_weights(self):
        for weights in ({}, {k: 0 for k in self.scorer.cv_weights}, {k: float("nan") for k in self.scorer.cv_weights}):
            with self.assertRaises(ValueError):
                ScoringService(cv_weights=weights)

    def test_bounded_and_empty_jd(self):
        self.assertEqual(bounded(-50), 0)
        self.assertEqual(bounded(500), 100)
        result = self.scorer.score(self.profile, self.checks, jd=JDParser().parse(""))
        self.assertEqual(result.overall_score, 0)

    def test_reported_cv_only_regression(self):
        scores = ScoreBreakdown(content=100, skills=100, experience=25,
                                education=100, structure=100, projects=100)
        result = self.scorer.score_cv_only(scores)
        self.assertEqual(result.overall_score, 91)  # raw weighted sum = 90.625
        self.assertLess(result.overall_score, 100)
        self.assertEqual(result.components, scores.model_dump(exclude_none=True))
        self.assertAlmostEqual(sum(result.effective_weights.values()), 1.0)
        self.assertAlmostEqual(sum(result.components[k] * w for k, w in result.effective_weights.items()), 90.625)

    def test_each_cv_category_independently_affects_the_overall(self):
        for category, weight in CV_ONLY_WEIGHTS.items():
            with self.subTest(category=category):
                scores = ScoreBreakdown(**{name: 80 for name in CV_ONLY_WEIGHTS})
                self.assertEqual(self.scorer.score_cv_only(scores).overall_score, 80)
                setattr(scores, category, 0)
                result = self.scorer.score_cv_only(scores)
                self.assertEqual(result.overall_score, round(80 - 80 * weight))
                self.assertLess(result.overall_score, 80)

    def test_missing_experience_is_zero_and_does_not_disappear(self):
        self.semantic.experience_quality.quality = "unknown"
        result = self.scorer.score(self.profile, self.checks, self.semantic)
        self.assertEqual(result.scores.experience, 0)
        self.assertEqual(result.effective_weights["experience"], .125)
        self.assertEqual(result.overall_score, 74)

    def test_default_weights_are_fractional_and_sum_to_one(self):
        for weights in (CV_ONLY_WEIGHTS, JOB_MATCH_WEIGHTS):
            self.assertAlmostEqual(sum(weights.values()), 1.0)
            self.assertTrue(all(0 <= value <= 1 for value in weights.values()))

    def test_percent_weights_and_wrong_totals_rejected(self):
        for factor in (100, .5):
            with self.subTest(factor=factor), self.assertRaises(ValueError):
                ScoringService(cv_weights={k: v * factor for k, v in CV_ONLY_WEIGHTS.items()})

    def test_invalid_scores_are_rejected_instead_of_clamped(self):
        for value in (10000, -1, float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.scorer.weighted({"content": value}, {"content": 1.0})

    def test_cv_aggregation_requires_all_categories(self):
        with self.assertRaises(ValueError):
            self.scorer.score_cv_only(ScoreBreakdown(content=100))

    def test_semantic_levels_use_the_calibrated_backend_scale(self):
        for level, expected in (("exceptional", 92), ("strong", 82), ("adequate", 70),
                                ("limited", 52), ("weak", 35), ("insufficient", 15), ("unknown", 0)):
            with self.subTest(level=level):
                for field in ("content_quality", "skill_quality", "experience_quality", "project_quality", "education_quality"):
                    getattr(self.semantic, field).quality = level
                result = self.scorer.score(self.profile, self.checks, self.semantic)
                for field in ("content", "skills", "experience", "projects", "education"):
                    self.assertEqual(getattr(result.scores, field), expected)
                self.assertEqual(result.scores.structure, 100)
                self.assertEqual(result.overall_score, round(expected * .85 + 100 * .15))
                self.assertLessEqual(result.overall_score, 93)

    def test_fallback_keywords_and_bullets_cannot_produce_semantic_excellence(self):
        result = self.scorer.score(self.profile, self.checks)
        self.assertLessEqual(result.scores.content, QUALITY_POINTS["adequate"])
        for field in ("skills", "experience", "education", "projects"):
            self.assertLessEqual(getattr(result.scores, field), QUALITY_POINTS["limited"])
