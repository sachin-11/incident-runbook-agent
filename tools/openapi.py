"""Generate one OpenAPI 3.1 document per action group from the tools' pydantic models.

OpenAPI 3.1 matches the JSON Schema dialect pydantic emits, so the models are the single source
of truth. `scripts/gen_tool_schemas.py` writes tools/schemas/<group>.openapi.json and a test
fails if the committed files drift from the models.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from tools.common.models import ToolError
from tools.registry import ActionGroup, tools_in

SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"
REF = "#/components/schemas/{model}"


def _add_model(
    components: dict[str, Any],
    model: type[BaseModel],
    mode: Literal["validation", "serialization"],
) -> dict[str, str]:
    schema = model.model_json_schema(ref_template=REF, mode=mode)
    components.update(schema.pop("$defs", {}))
    components[model.__name__] = schema
    return {"$ref": REF.format(model=model.__name__)}


def build_openapi(group: ActionGroup) -> dict[str, Any]:
    components: dict[str, Any] = {}
    paths: dict[str, Any] = {}
    error_ref = _add_model(components, ToolError, "serialization")
    for tool in tools_in(group):
        operation: dict[str, Any] = {
            "operationId": tool.name,
            "summary": tool.name.replace("_", " "),
            "description": tool.description,
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": _add_model(components, tool.input_model, "validation")
                    }
                },
            },
            "responses": {
                "200": {
                    "description": "Tool result, or an error object.",
                    "content": {
                        "application/json": {
                            "schema": {
                                "oneOf": [
                                    _add_model(components, tool.output_model, "serialization"),
                                    error_ref,
                                ]
                            }
                        }
                    },
                }
            },
        }
        if tool.risky:
            # Bedrock-style hint; enforcement is the approval token + AgentCore Policy.
            operation["x-requireConfirmation"] = "ENABLED"
        paths[f"/{tool.name}"] = {"post": operation}
    return {
        "openapi": "3.1.0",
        "info": {
            "title": f"incident-runbook-agent {group} tools",
            "version": "1.0.0",
            "description": (
                "Read-only diagnostics." if group == "diagnostics" else "Risky remediation tools."
            ),
        },
        "paths": paths,
        "components": {"schemas": dict(sorted(components.items()))},
    }


def schema_path(group: ActionGroup) -> Path:
    return SCHEMA_DIR / f"{group}.openapi.json"
