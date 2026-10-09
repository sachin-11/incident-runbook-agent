"""Input/output building blocks shared by every tool."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from pydantic.json_schema import SkipJsonSchema

ServiceName = Annotated[
    str, StringConstraints(pattern=r"^[a-z][a-z0-9-]{1,40}$", strip_whitespace=True)
]
ScenarioId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9_]{1,40}$")]


class ToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    # Simulator only: lets tests and the invoke script pick a scenario. Hidden from the schema
    # the model sees, so the agent cannot choose its own failure scenario.
    scenario_id: SkipJsonSchema[ScenarioId | None] = None


class ToolOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # True when any returned text matched an instruction-like pattern; see `untrusted_flags`.
    untrusted_content: bool = False
    untrusted_flags: list[str] = Field(default_factory=list)


class ToolErrorBody(BaseModel):
    code: str
    message: str


class ToolError(BaseModel):
    error: ToolErrorBody


class ToolFailure(Exception):  # noqa: N818 (domain name, carries a code for the caller)
    """Expected failure the tool reports to the caller as a ToolError (not a crash)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
