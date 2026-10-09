"""Bedrock Knowledge Base over the runbooks and postmortems in kb/. Empty for now."""

from __future__ import annotations

from typing import Any

from aws_cdk import Stack
from constructs import Construct


class KnowledgeBaseStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs: Any) -> None:
        super().__init__(scope, construct_id, **kwargs)
