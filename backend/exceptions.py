"""Safe, public error messages; never attach provider responses or CV text."""
from enum import Enum


class LLMFailureReason(str, Enum):
    MISSING_KEY = "missing_api_key"
    AUTHENTICATION = "authentication"
    QUOTA = "quota_or_rate_limit"
    TIMEOUT = "timeout"
    NETWORK = "network"
    MODEL_UNAVAILABLE = "model_unavailable"
    REQUEST_REJECTED = "request_rejected"
    SERVICE_UNAVAILABLE = "service_unavailable"
    INVALID_RESPONSE = "invalid_response"
    UNKNOWN = "unknown"


class DocumentParseError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


class InvalidCVError(ValueError):
    pass


class LLMError(RuntimeError):
    pass


class LLMUnavailableError(LLMError):
    def __init__(self, message="AI request could not be completed.", *, reason=LLMFailureReason.UNKNOWN):
        self.reason = LLMFailureReason(reason)
        super().__init__(message)


class LLMResponseError(LLMError):
    pass
