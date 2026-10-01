"""Useful schema diagnostics without logging input values, contexts or error text."""
import logging

from pydantic import BaseModel, ValidationError


def log_schema_error(logger: logging.Logger, *, stage: str, model: type[BaseModel], error: ValidationError):
    allowed_names = set()

    def collect(node):
        if isinstance(node, dict):
            allowed_names.update(node.get("properties", {}))
            for value in node.values():
                collect(value)
        elif isinstance(node, list):
            for value in node:
                collect(value)

    collect(model.model_json_schema())
    errors = error.errors(include_url=False, include_context=False, include_input=False)
    fields = [".".join(str(part) if isinstance(part, int) or part in allowed_names else "?"
                       for part in item["loc"]) or "<root>" for item in errors]
    logger.warning("AI schema validation failed (stage=%s, model=%s, fields=%s, types=%s)",
                   stage, model.__name__, ",".join(fields), ",".join(item["type"] for item in errors))
