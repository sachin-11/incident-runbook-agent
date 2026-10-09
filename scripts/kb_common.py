"""Shared helpers for the KB scripts: stack naming, stack outputs, boto3 clients."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import boto3
from botocore.config import Config
from pydantic import BaseModel

from agent.config import KbSettings

if TYPE_CHECKING:
    from mypy_boto3_cloudformation import CloudFormationClient

BOTO_CONFIG = Config(connect_timeout=5, read_timeout=30, retries={"max_attempts": 5})


class KbStackOutputs(BaseModel):
    knowledge_base_id: str
    data_source_id: str
    docs_bucket_name: str
    docs_prefix: str


def kb_stack_name(stage: str) -> str:
    return f"Ira-{stage}-KnowledgeBase"


def client(settings: KbSettings, service: str) -> Any:
    # The service name is a runtime value, so the typed per-service overloads cannot match.
    return boto3.client(  # type: ignore[call-overload]
        service, region_name=settings.aws_region, config=BOTO_CONFIG
    )


def load_stack_outputs(cfn: CloudFormationClient, stack_name: str) -> KbStackOutputs:
    stack = cfn.describe_stacks(StackName=stack_name)["Stacks"][0]
    outputs = {o["OutputKey"]: o["OutputValue"] for o in stack.get("Outputs", [])}
    return KbStackOutputs(
        knowledge_base_id=outputs["KnowledgeBaseId"],
        data_source_id=outputs["DataSourceId"],
        docs_bucket_name=outputs["DocsBucketName"],
        docs_prefix=outputs["DocsPrefix"],
    )
