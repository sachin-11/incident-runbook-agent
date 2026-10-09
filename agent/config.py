"""Typed runtime settings. Region and model IDs always come from env, never code."""

from __future__ import annotations

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="IRA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    aws_region: str = Field(min_length=1)
    agent_model_id: str = Field(min_length=1)
    embedding_model_id: str = Field(min_length=1)
    env: Literal["dev", "staging", "prod"] = "dev"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"


def load_settings() -> Settings:
    """Load settings from env / .env; raises pydantic.ValidationError if incomplete."""
    return Settings()
