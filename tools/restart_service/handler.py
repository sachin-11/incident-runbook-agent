"""restart_service(service, reason, approval_token, request_id, dry_run): RISKY, needs approval.

Rules:
- Refuses without a valid approval token (HMAC-signed, unexpired, bound to this service and
  action). Tokens are single use: a token already claimed by another request is rejected.
- Idempotent: the same `request_id` with the same input returns the stored result; with
  different input it is rejected as an idempotency conflict.
- Every attempt (accepted, rejected, dry run, replay) writes an audit event to DynamoDB.
- `dry_run` validates everything and reports `would_execute`, but restarts nothing and does not
  use up the token.

The restart itself is simulated. The request and token are claimed atomically *before* acting,
so a real implementation never restarts twice for one approval.
"""

from __future__ import annotations

import hashlib
import json
import os
from functools import cache
from typing import Literal

import boto3
from botocore.config import Config
from pydantic import Field

from tools.common.approval import ApprovalClaims, TokenError, verify_token
from tools.common.audit import AlreadyClaimed, AuditStore
from tools.common.handler import make_handler
from tools.common.models import ServiceName, ToolInput, ToolOutput
from tools.common.sanitize import clean
from tools.sim.access import backend_for

NAME = "restart_service"
DESCRIPTION = (
    "RISKY. Rolling restart of one service. Requires an approval_token issued by a human "
    "approver for this service; without it the call is rejected. Use dry_run=true to check "
    "what would happen. Reuse the same request_id when retrying."
)


class RestartServiceInput(ToolInput):
    service: ServiceName = Field(description="Service to restart, e.g. checkout-api.")
    reason: str = Field(min_length=10, max_length=500, description="Why the restart is needed.")
    request_id: str = Field(
        pattern=r"^[A-Za-z0-9_-]{8,64}$",
        description="Idempotency key. Retries of the same action must reuse it.",
    )
    approval_token: str | None = Field(
        default=None, max_length=2048, description="Token from the human approval step."
    )
    dry_run: bool = Field(default=False, description="Validate only; restart nothing.")


class RestartServiceOutput(ToolOutput):
    status: Literal["restarted", "dry_run", "rejected"]
    service: str
    request_id: str
    message: str
    reason_code: str | None = Field(
        default=None,
        description="Why it was rejected or would not execute (missing_token, expired, ...).",
    )
    would_execute: bool | None = Field(default=None, description="Dry run only.")
    approver: str | None = None
    idempotent_replay: bool = False
    simulated: bool = True
    audit_event_id: str | None = None


_BOTO = Config(connect_timeout=2, read_timeout=3, retries={"max_attempts": 2})


@cache
def signing_key() -> bytes:
    sm = boto3.client("secretsmanager", config=_BOTO)
    return sm.get_secret_value(SecretId=os.environ["APPROVAL_SECRET_ARN"])["SecretString"].encode()


@cache
def audit_store() -> AuditStore:
    return AuditStore.from_env()


def _input_hash(req: RestartServiceInput) -> str:
    body = json.dumps({"service": req.service, "reason": req.reason, "dry_run": req.dry_run})
    return hashlib.sha256(body.encode()).hexdigest()[:32]


def restart_service(req: RestartServiceInput) -> RestartServiceOutput:  # noqa: PLR0911
    store = audit_store()
    backend = backend_for(req.service, req.scenario_id)
    input_hash = _input_hash(req)
    reason = clean(req.reason)
    base = {"service": req.service, "request_id": req.request_id}

    def audit(outcome: str, code: str | None = None, claims: ApprovalClaims | None = None) -> str:
        return store.record_event(
            tool=NAME,
            outcome=outcome,
            reason_code=code,
            reason=reason,
            dry_run=req.dry_run,
            approver=claims.approver if claims else None,
            jti=claims.jti if claims else None,
            scenario_id=backend.scenario.id,
            **base,
        )

    def reject(
        code: str, message: str, claims: ApprovalClaims | None = None
    ) -> RestartServiceOutput:
        return RestartServiceOutput(
            status="rejected",
            reason_code=code,
            message=message,
            audit_event_id=audit("rejected", code, claims),
            **base,
        )

    def replay(stored: dict[str, object]) -> RestartServiceOutput:
        if stored["input_hash"] != input_hash:
            return reject("idempotency_conflict", "request_id was already used with other input")
        out = RestartServiceOutput.model_validate(stored["result"])
        return out.model_copy(
            update={"idempotent_replay": True, "audit_event_id": audit("idempotent_replay")}
        )

    if not req.dry_run and (stored := store.get_request(req.request_id)):
        return replay(stored)

    if not req.approval_token:
        if req.dry_run:
            return RestartServiceOutput(
                status="dry_run",
                would_execute=False,
                reason_code="missing_token",
                message="Would be rejected: an approval_token from a human approver is required.",
                audit_event_id=audit("dry_run", "missing_token"),
                **base,
            )
        return reject("missing_token", "restart_service requires an approval_token from a human.")

    try:
        claims = verify_token(
            signing_key(), req.approval_token, service=req.service, action="restart_service"
        )
    except TokenError as exc:
        if req.dry_run:
            return RestartServiceOutput(
                status="dry_run",
                would_execute=False,
                reason_code=exc.code,
                message=f"Would be rejected: {exc.message}.",
                audit_event_id=audit("dry_run", exc.code),
                **base,
            )
        return reject(exc.code, exc.message)

    health = backend.health(req.service)
    if req.dry_run:
        used = store.token_used(claims.jti)
        return RestartServiceOutput(
            status="dry_run",
            would_execute=not used,
            reason_code="token_replayed" if used else None,
            approver=claims.approver,
            message=(
                "Would be rejected: approval token was already used."
                if used
                else f"Would restart {req.service} ({health.ready_replicas}/"
                f"{health.desired_replicas} ready, status {health.status})."
            ),
            audit_event_id=audit("dry_run", "token_replayed" if used else None, claims),
            **base,
        )

    result = RestartServiceOutput(
        status="restarted",
        approver=claims.approver,
        message=(
            f"Simulated rolling restart of {req.service} started "
            f"(before: {health.ready_replicas}/{health.desired_replicas} ready, "
            f"status {health.status})."
        ),
        **base,
    )
    try:
        store.claim(
            request_id=req.request_id,
            jti=claims.jti,
            record={"input_hash": input_hash, "result": result.model_dump(mode="json")},
        )
    except AlreadyClaimed:
        if stored := store.get_request(req.request_id):  # lost a race with our own retry
            return replay(stored)
        return reject(
            "token_replayed", "approval token was already used for another request", claims
        )
    return result.model_copy(update={"audit_event_id": audit("restarted", None, claims)})


handler = make_handler(NAME, RestartServiceInput, restart_service)
