"""Pure scoring: semantic levels/requirement states -> reproducible bounded scores."""
from collections.abc import Mapping
import math

from backend.config import (CV_ONLY_WEIGHTS, JOB_MATCH_WEIGHTS, MATCH_POINTS,
                            PREFERRED_REQUIREMENT_WEIGHT, QUALITY_POINTS)
from backend.models import (AISemanticAnalysis, BasicChecks, CandidateProfile,
                            JobDescription, RequirementMatch, ScoreBreakdown, ScoringOutcome)
from cv_checker import _analyze_bullets


def bounded(value: float) -> int:
    return max(0, min(100, round(value)))


class ScoringService:
    def __init__(self, cv_weights: Mapping[str, float] | None = None,
                 job_weights: Mapping[str, float] | None = None):
        self.cv_weights = self._weights(cv_weights if cv_weights is not None else CV_ONLY_WEIGHTS, CV_ONLY_WEIGHTS)
        self.job_weights = self._weights(job_weights if job_weights is not None else JOB_MATCH_WEIGHTS, JOB_MATCH_WEIGHTS)

    @staticmethod
    def _weights(weights, expected):
        if (set(weights) != set(expected)
                or any(not math.isfinite(v) or v < 0 for v in weights.values())
                or not math.isclose(sum(weights.values()), 1.0, rel_tol=0, abs_tol=1e-9)):
            raise ValueError("Scoring weights must cover all components, be finite and nonnegative, and sum to 1.0.")
        return dict(weights)

    @staticmethod
    def weighted(components, weights):
        if any(value is not None and (not math.isfinite(value) or not 0 <= value <= 100)
               for value in components.values()):
            raise ValueError("Scoring components must be finite scores between 0 and 100.")
        active = {key: weights[key] for key, value in components.items() if value is not None and weights[key] > 0}
        total = sum(active.values())
        effective = {key: weight / total for key, weight in active.items()} if total else {}
        # A convex weighted mean is already bounded. Never clamp an oversized sum
        # into a plausible score and conceal a scoring/configuration error.
        return round(sum(components[key] * weight for key, weight in effective.items())), effective

    def score_cv_only(self, scores: ScoreBreakdown) -> ScoringOutcome:
        components = {name: getattr(scores, name) for name in self.cv_weights}
        if any(value is None for value in components.values()):
            raise ValueError("CV-only scoring requires all six category scores; missing evidence scores zero.")
        overall, effective = self.weighted(components, self.cv_weights)
        return ScoringOutcome(overall_score=overall, scores=scores,
                              components=components, effective_weights=effective)

    @staticmethod
    def structure(checks: BasicChecks):
        flags = [checks.has_email, checks.has_phone, "education" in checks.sections_detected,
                 "skills" in checks.sections_detected,
                 bool({"experience", "projects"}.intersection(checks.sections_detected))]
        return bounded(100 * sum(flags) / len(flags))

    def score(self, profile: CandidateProfile, checks: BasicChecks,
              semantic: AISemanticAnalysis | None = None, jd: JobDescription | None = None,
              matches: list[RequirementMatch] | None = None) -> ScoringOutcome:
        bullets = _analyze_bullets(profile.experience + profile.projects)
        strong_bullets = sum(item["classification"] == "impact-oriented" for item in bullets)
        # Fallback heuristics provide conservative proxies, not semantic excellence.
        content = bounded(QUALITY_POINTS["adequate"] * strong_bullets / len(bullets)) if bullets else 0
        skills = QUALITY_POINTS["limited"] if profile.skills else 0
        experience = QUALITY_POINTS["limited"] if profile.experience else 0
        projects = QUALITY_POINTS["limited"] if profile.projects else 0
        education = QUALITY_POINTS["limited"] if profile.education else 0
        if semantic:
            content = QUALITY_POINTS[semantic.content_quality.quality]
            skills = QUALITY_POINTS[semantic.skill_quality.quality]
            experience = QUALITY_POINTS[semantic.experience_quality.quality]
            projects = QUALITY_POINTS[semantic.project_quality.quality]
            education = QUALITY_POINTS[semantic.education_quality.quality]
        structure = self.structure(checks)
        breakdown = ScoreBreakdown(content=content, skills=skills, experience=experience,
                                   education=education, structure=structure, projects=projects)
        if jd is None:
            return self.score_cv_only(breakdown)
        else:
            # Each requirement contributes to exactly one component, never again as a keyword.
            match_index = {match.requirement: match for match in matches or []}
            categories = {"hard_skills": "hard_skill", "experience": "experience", "projects": "project",
                          "education": "education", "role": "role", "other": "other"}
            components = {}
            for component, category in categories.items():
                requirements = [r for r in jd.requirements if r.category == category]
                if not requirements:
                    components[component] = None
                    continue
                numerator = denominator = 0
                for requirement in requirements:
                    weight = PREFERRED_REQUIREMENT_WEIGHT if requirement.preferred else 1
                    status = match_index[requirement.requirement].status if requirement.requirement in match_index else "missing"
                    numerator += MATCH_POINTS[status] * weight
                    denominator += weight
                # Evidence-backed matches already express relevance, including years and field.
                # A global 'strong' AI rating cannot override a missing concrete requirement.
                components[component] = bounded(numerator / denominator)
                if semantic and component in {"experience", "projects", "education", "role"}:
                    judgment = getattr(semantic, {"experience": "experience_relevance", "projects": "project_relevance",
                                                 "education": "education_relevance", "role": "role_relevance"}[component])
                    if judgment and judgment.evidence and judgment.quality != "unknown":
                        components[component] = min(components[component], QUALITY_POINTS[judgment.quality])
            overall, effective = self.weighted(components, self.job_weights)
            breakdown.skills = components["hard_skills"]
            breakdown.experience = components["experience"]
            breakdown.projects = components["projects"]
            breakdown.education = components["education"]
            breakdown.role = components["role"]
            breakdown.other_keywords = components["other"]
            breakdown.job_match = overall
        return ScoringOutcome(overall_score=overall, scores=breakdown,
                              components={key: value for key, value in components.items() if value is not None},
                              effective_weights=effective)
