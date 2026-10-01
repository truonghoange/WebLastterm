"""Run with python -m examples.service_checks. Makes no Gemini API calls."""
from backend.config import Settings
from backend.exceptions import LLMUnavailableError
from backend.services.analysis_service import AnalysisService
from tests.helpers import JD, MockProvider, document, semantic_payload


def main():
    cases = [
        ("CV only", AnalysisService(provider=MockProvider(semantic_payload(None))), None),
        ("CV + JD", AnalysisService(provider=MockProvider()), JD),
        ("Gemini unavailable", AnalysisService(settings=Settings(),
            provider=MockProvider(error=LLMUnavailableError("Synthetic outage"))), JD),
    ]
    for label, service, jd in cases:
        result = service.analyze_cv(document(), jd_text=jd, target_position="Data Analyst")
        print(f"{label}: mode={result.mode}, score={result.overall_score}, ai_available={result.ai_available}")
        print(f"  matched={result.matched_skills}, partial={result.partially_matched_skills}, missing={result.missing_skills}")
        if result.warnings:
            print("  warnings=" + " | ".join(result.warnings))
        assert 0 <= result.overall_score <= 100
        if jd is None:
            assert result.mode == "cv_only" and result.scores.job_match is None
            assert not result.requirement_matches
        if label == "Gemini unavailable":
            assert not result.ai_available and result.basic_checks.has_email
        service.close()


if __name__ == "__main__":
    main()
