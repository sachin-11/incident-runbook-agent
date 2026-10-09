"""Approval tokens for risky tools: HMAC-SHA256 signed, short-lived, bound to service and action.

Format: `v1.<base64url(claims json)>.<base64url(signature)>`. The signing key lives in Secrets
Manager. Only the approval flow (a human, via scripts/issue_approval_token.py for now) can issue
tokens; the agent never sees the key. Single use is enforced by restart_service's audit table
(the token's `jti` can be claimed once).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

VERSION = "v1"
MAX_TTL_S = 3600
CLOCK_SKEW_S = 30
Action = Literal["restart_service"]


class ApprovalClaims(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    service: str
    action: Action
    approver: str = Field(min_length=1, max_length=100)
    jti: str = Field(min_length=16, max_length=64)
    iat: int
    exp: int


class TokenError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(key: bytes, payload: str) -> str:
    return _b64(hmac.new(key, f"{VERSION}.{payload}".encode(), hashlib.sha256).digest())


def issue_token(  # noqa: PLR0913 (all but key are keyword-only)
    key: bytes,
    *,
    service: str,
    approver: str,
    action: Action = "restart_service",
    ttl_s: int = 900,
    now: float | None = None,
) -> str:
    if not 0 < ttl_s <= MAX_TTL_S:
        raise ValueError(f"ttl_s must be in 1..{MAX_TTL_S}")
    iat = int(now if now is not None else time.time())
    claims = ApprovalClaims(
        service=service,
        action=action,
        approver=approver,
        jti=secrets.token_hex(16),
        iat=iat,
        exp=iat + ttl_s,
    )
    payload = _b64(json.dumps(claims.model_dump(), separators=(",", ":"), sort_keys=True).encode())
    return f"{VERSION}.{payload}.{_sign(key, payload)}"


def verify_token(
    key: bytes, token: str, *, service: str, action: Action, now: float | None = None
) -> ApprovalClaims:
    """Return the claims or raise TokenError(code) with code in:
    malformed, bad_signature, expired, not_yet_valid, ttl_too_long, wrong_service, wrong_action.
    """
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != VERSION:
        raise TokenError("malformed", "approval token has an unknown format")
    _, payload, signature = parts
    if not hmac.compare_digest(_sign(key, payload), signature):
        raise TokenError("bad_signature", "approval token signature is invalid")
    try:
        claims = ApprovalClaims.model_validate_json(_unb64(payload))
    except (ValidationError, ValueError):
        raise TokenError("malformed", "approval token claims are invalid") from None
    t = now if now is not None else time.time()
    if claims.exp - claims.iat > MAX_TTL_S:
        raise TokenError("ttl_too_long", "approval token lifetime exceeds the maximum")
    if t >= claims.exp:
        raise TokenError("expired", "approval token has expired")
    if claims.iat > t + CLOCK_SKEW_S:
        raise TokenError("not_yet_valid", "approval token is not valid yet")
    if claims.action != action:
        raise TokenError("wrong_action", "approval token was issued for another action")
    if claims.service != service:
        raise TokenError("wrong_service", "approval token was issued for another service")
    return claims
