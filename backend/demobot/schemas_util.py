"""JSON-schema helpers for structured output."""

from typing import Any

from pydantic import BaseModel


def strict_schema_dict(schema: dict[str, Any]) -> dict[str, Any]:
    """Inline every $ref, drop defaults and titles, and make every object strict: all properties
    required and additionalProperties false (what strict structured-output modes accept)."""
    defs = schema.get("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, list):
            return [walk(v) for v in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            target = defs[node["$ref"].split("/")[-1]]
            merged = {**target, **{k: v for k, v in node.items() if k != "$ref"}}
            return walk(merged)
        out = {k: walk(v) for k, v in node.items() if k not in ("$defs", "default", "title")}
        if out.get("type") == "object" and "properties" in out:
            out["additionalProperties"] = False
            out["required"] = list(out["properties"])
        return out

    return walk(schema)


def strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    return strict_schema_dict(model.model_json_schema())
