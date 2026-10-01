"""Provider-independent semantic analysis; validates even injected providers."""
import logging

from pydantic import ValidationError

from backend.exceptions import LLMResponseError
from backend.ai_response_models import AISemanticResponse
from backend.models import AISemanticAnalysis, CVDocument
from backend.normalization import normalize_ai_response
from backend.parsers.jd_parser import JDParser
from backend.prompts.cv_analysis_prompt import build_cv_only_prompt, build_job_match_prompt
from backend.providers.base_llm import LLMProvider
from backend.schema_validation import log_schema_error

logger = logging.getLogger(__name__)


class GeminiAnalyzer:
    def __init__(self, provider: LLMProvider, jd_parser=None):
        self.provider = provider
        self.jd_parser = jd_parser or JDParser()

    def analyze(self, cv_document: CVDocument, jd_text=None, target_position=None, industry=None) -> AISemanticAnalysis:
        if jd_text and jd_text.strip():
            prompt = build_job_match_prompt(cv_document, self.jd_parser.parse(jd_text), target_position, industry)
        else:
            prompt = build_cv_only_prompt(cv_document, target_position, industry)
        try:
            response = self.provider.analyze(prompt, AISemanticResponse)
            # Revalidate to enforce the contract at this boundary, including mocks.
            if isinstance(response, AISemanticResponse):
                response = response.model_dump()
            wire_response = AISemanticResponse.model_validate(response)
        except ValidationError as error:
            log_schema_error(logger, stage="response_model", model=AISemanticResponse, error=error)
            raise LLMResponseError("AI returned an invalid structured response.") from None
        except (TypeError, ValueError):
            logger.warning("AI schema validation failed (stage=response_model)")
            raise LLMResponseError("AI returned an invalid structured response.") from None
        try:
            return normalize_ai_response(wire_response, job_match=bool(jd_text and jd_text.strip()))
        except LLMResponseError:
            logger.warning("AI schema validation failed (stage=normalization)")
            raise
        except ValidationError as error:
            log_schema_error(logger, stage="internal_model", model=AISemanticAnalysis, error=error)
            raise LLMResponseError("AI returned an invalid structured response.") from None
        except (TypeError, ValueError):
            logger.warning("AI schema validation failed (stage=internal_model)")
            raise LLMResponseError("AI returned an invalid structured response.") from None
