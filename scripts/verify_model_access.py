"""Verify the configured Bedrock models are usable in the configured region.

Uses bedrock:GetFoundationModelAvailability (shape verified against botocore 1.43.110).
Exit code 0 = all models ready, 1 = at least one not ready / check failed.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from pydantic import BaseModel

from agent.config import load_settings
from observability.logging import get_logger

if TYPE_CHECKING:
    from mypy_boto3_bedrock import BedrockClient

log = get_logger("verify_model_access")


class ModelAccess(BaseModel):
    model_id: str
    ready: bool
    detail: str


def check_model(client: BedrockClient, model_id: str) -> ModelAccess:
    try:
        resp: Any = client.get_foundation_model_availability(modelId=model_id)
    except (ClientError, BotoCoreError) as exc:
        return ModelAccess(model_id=model_id, ready=False, detail=f"check failed: {exc}")
    statuses = {
        "authorization": resp["authorizationStatus"],
        "entitlement": resp["entitlementAvailability"],
        "region": resp["regionAvailability"],
        "agreement": resp["agreementAvailability"]["status"],
    }
    ready = statuses == {
        "authorization": "AUTHORIZED",
        "entitlement": "AVAILABLE",
        "region": "AVAILABLE",
        "agreement": "AVAILABLE",
    }
    return ModelAccess(model_id=model_id, ready=ready, detail=str(statuses))


def main() -> int:
    settings = load_settings()
    client = boto3.client(
        "bedrock",
        region_name=settings.aws_region,
        config=Config(connect_timeout=5, read_timeout=10, retries={"max_attempts": 3}),
    )
    results = [
        check_model(client, mid) for mid in (settings.agent_model_id, settings.embedding_model_id)
    ]
    for r in results:
        log.info("model_access", extra={"region": settings.aws_region, **r.model_dump()})
    return 0 if all(r.ready for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
