"""Project typed wire schemas onto a small Gemini-compatible schema vocabulary."""
from pydantic import BaseModel


def build_gemini_schema(model: type[BaseModel]) -> dict[str, object]:
    """Inline local references, omit validation metadata, and prefer object judgments.

    Tolerance is for incoming responses. The outgoing schema requests one canonical
    shape, using objects/arrays/primitives and nullable for optional fields. Internal
    application models and their validators are never changed by this projection.
    """
    source = model.model_json_schema()
    definitions = source.get("$defs", {})

    def project(node, ancestors=()):
        if "$ref" in node:
            ref = node["$ref"]
            prefix = "#/$defs/"
            if not ref.startswith(prefix) or ref in ancestors:
                raise ValueError("The response schema contains an unsupported reference.")
            return project(definitions[ref[len(prefix):]], ancestors + (ref,))
        if "anyOf" in node:
            nullable = any(choice.get("type") == "null" for choice in node["anyOf"])
            choices = [project(choice, ancestors) for choice in node["anyOf"] if choice.get("type") != "null"]
            if len(choices) == 1:
                result = choices[0]
            else:
                objects = [choice for choice in choices if choice.get("type") == "object"]
                if len(objects) != 1 or any(choice.get("type") not in {"object", "string"} for choice in choices):
                    raise ValueError("The response schema contains an unsupported union.")
                result = objects[0]
            if nullable:
                result = {**result, "nullable": True}
            return result
        result = {key: node[key] for key in ("type", "description", "enum") if key in node}
        if "properties" in node:
            result["properties"] = {key: project(value, ancestors) for key, value in node["properties"].items()}
        if "required" in node:
            result["required"] = node["required"]
        if "items" in node:
            result["items"] = project(node["items"], ancestors)
        return result

    return project(source)
