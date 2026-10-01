"""Gemini transport only: one request, finite timeout, safe errors, validation."""
import logging

from pydantic import ValidationError

from backend.config import Settings
from backend.exceptions import LLMFailureReason, LLMResponseError, LLMUnavailableError
from backend.providers.base_llm import LLMProvider, ResponseModel
from backend.providers.response_schema import build_gemini_schema
from backend.schema_validation import log_schema_error

logger = logging.getLogger(__name__)


def _failure_reason(error: Exception) -> LLMFailureReason:
    from google.genai.errors import APIError
    import httpx

    if isinstance(error, (TimeoutError, httpx.TimeoutException)):
        return LLMFailureReason.TIMEOUT
    if isinstance(error, (ConnectionError, httpx.TransportError)):
        return LLMFailureReason.NETWORK
    if isinstance(error, APIError):
        return {401: LLMFailureReason.AUTHENTICATION, 403: LLMFailureReason.AUTHENTICATION,
                429: LLMFailureReason.QUOTA, 404: LLMFailureReason.MODEL_UNAVAILABLE,
                400: LLMFailureReason.REQUEST_REJECTED,
                500: LLMFailureReason.SERVICE_UNAVAILABLE,
                502: LLMFailureReason.SERVICE_UNAVAILABLE,
                503: LLMFailureReason.SERVICE_UNAVAILABLE,
                504: LLMFailureReason.TIMEOUT}.get(error.code, LLMFailureReason.UNKNOWN)
    return LLMFailureReason.UNKNOWN


class GeminiProvider(LLMProvider):
    def __init__(self, settings: Settings | None = None, *, client=None):
        self.settings = settings or Settings.from_env()
        self._client = client

    @property
    def model_name(self):
        return self.settings.gemini_model

    def _get_client(self):
        if not self.settings.gemini_api_key:
            raise LLMUnavailableError("AI is not configured.", reason=LLMFailureReason.MISSING_KEY)
        if self._client is None:
            from google import genai
            from google.genai import types

            self._client = genai.Client(
                api_key=self.settings.gemini_api_key,
                http_options=types.HttpOptions(
                    timeout=self.settings.timeout_ms,
                    retry_options=types.HttpRetryOptions(attempts=1),
                ),
            )
        return self._client

    def analyze(self, prompt: str, schema: type[ResponseModel]) -> ResponseModel:
        logger.info("AI request started")
        try:
            response_schema = build_gemini_schema(schema)
        except (ValueError, TypeError, KeyError):
            logger.warning("AI schema validation failed (stage=request_schema)")
            raise LLMResponseError("AI response schema could not be prepared.") from None
        try:
            client = self._get_client()
            response = client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config={"response_mime_type": "application/json",
                        "response_schema": response_schema, "temperature": 0},
            )
        except LLMUnavailableError:
            raise
        except Exception as error:
            # Includes auth/quota/rate limits, timeout, network and unavailable models.
            # SDK exceptions can contain prompts/keys: never log or expose them.
            raise LLMUnavailableError(reason=_failure_reason(error)) from None
        try:
            if not response.text:
                raise LLMResponseError("AI returned an empty response.")
            result = schema.model_validate_json(response.text)
        except LLMResponseError:
            logger.warning("AI schema validation failed (stage=response_model)")
            raise
        except ValidationError as error:
            log_schema_error(logger, stage="response_model", model=schema, error=error)
            raise LLMResponseError("AI returned an invalid structured response.") from None
        except (ValueError, TypeError, AttributeError):
            logger.warning("AI schema validation failed (stage=response_model)")
            raise LLMResponseError("AI returned an invalid structured response.") from None
        logger.info("AI request completed")
        return result

    def close(self):
        if self._client is not None:
            self._client.close()
            self._client = None
