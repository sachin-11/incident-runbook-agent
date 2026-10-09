"""Typed runtime settings. Region and model IDs always come from env, never code."""

from __future__ import annotations

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

Stage = Literal["dev", "staging", "prod"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="IRA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    # AWS and models: required, no defaults in code.
    aws_region: str = Field(min_length=1)
    agent_model_id: str = Field(min_length=1)
    embedding_model_id: str = Field(min_length=1)

    # Produced by the CDK stacks in later modules; unset until they are deployed.
    knowledge_base_id: str | None = Field(default=None, min_length=1)
    agent_id: str | None = Field(default=None, min_length=1)
    agent_alias_id: str | None = Field(default=None, min_length=1)

    stage: Stage = "dev"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # Budget caps, enforced per incident and per month.
    max_tokens_per_incident: int = Field(default=50_000, gt=0)
    max_cost_usd_per_incident: float = Field(default=0.50, gt=0)
    monthly_budget_usd: float = Field(default=20.0, gt=0)

    # Timeouts in seconds. Lambda caps a single invocation at 900 s.
    tool_timeout_s: float = Field(default=10.0, gt=0, le=900)
    agent_timeout_s: float = Field(default=120.0, gt=0, le=900)


def load_settings() -> Settings:
    """Load settings from env / .env; raises pydantic.ValidationError if incomplete."""
    return Settings()
