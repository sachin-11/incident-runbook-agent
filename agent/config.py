"""Typed runtime settings. Region and model IDs always come from env, never code."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

Stage = Literal["dev", "staging", "prod"]


class InfraSettings(BaseSettings):
    """What the CDK app and the ops scripts need. No agent model required."""

    model_config = SettingsConfigDict(
        env_prefix="IRA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    # AWS and models: required, no defaults in code.
    aws_region: str = Field(min_length=1)
    embedding_model_id: str = Field(min_length=1)
    # Must be a size the embedding model supports (Titan Text v2: 256, 512 or 1024).
    embedding_dimensions: int = Field(default=1024, gt=0)

    stage: Stage = "dev"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # Produced by KnowledgeBaseStack; scripts fall back to the stack outputs when unset.
    knowledge_base_id: str | None = Field(default=None, min_length=1)

    # Lambda timeout for every tool. Lambda caps a single invocation at 900 s.
    tool_timeout_s: float = Field(default=10.0, gt=0, le=900)
    # Simulator scenario the tool Lambdas serve when a request does not pick one.
    sim_scenario_id: str = Field(default="healthy", pattern=r"^[a-z0-9_]+$")


class Settings(InfraSettings):
    agent_model_id: str = Field(min_length=1)

    # Produced by AgentStack in a later module; unset until it is deployed.
    agent_id: str | None = Field(default=None, min_length=1)
    agent_alias_id: str | None = Field(default=None, min_length=1)

    # Budget caps, enforced per incident and per month.
    max_tokens_per_incident: int = Field(default=50_000, gt=0)
    max_cost_usd_per_incident: float = Field(default=0.50, gt=0)
    monthly_budget_usd: float = Field(default=20.0, gt=0)

    # Seconds. Lambda caps a single invocation at 900 s.
    agent_timeout_s: float = Field(default=120.0, gt=0, le=900)


def load_settings() -> Settings:
    """Load settings from env / .env; raises pydantic.ValidationError if incomplete."""
    return Settings()


def load_infra_settings(env_file: Path | None = None) -> InfraSettings:
    """Infra/ops subset. Pass `env_file` when running outside the repo root (e.g. from infra/)."""
    if env_file is None:
        return InfraSettings()
    return InfraSettings(_env_file=env_file)
