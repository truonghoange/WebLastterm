from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel

ResponseModel = TypeVar("ResponseModel", bound=BaseModel)


class LLMProvider(ABC):
    @abstractmethod
    def analyze(self, prompt: str, schema: type[ResponseModel]) -> ResponseModel:
        """Return a validated model, or raise LLMUnavailableError/LLMResponseError."""
