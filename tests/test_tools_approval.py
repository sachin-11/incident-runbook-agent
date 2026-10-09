import base64
import json

import pytest

from tools.common.approval import MAX_TTL_S, TokenError, _b64, _sign, issue_token, verify_token

KEY = b"k" * 64
NOW = 1_800_000_000.0


def _verify(token, service="checkout-api", now=NOW + 10):
    return verify_token(KEY, token, service=service, action="restart_service", now=now)


def _code(fn):
    with pytest.raises(TokenError) as exc:
        fn()
    return exc.value.code


def test_round_trip():
    token = issue_token(KEY, service="checkout-api", approver="dana", ttl_s=600, now=NOW)
    claims = _verify(token)
    assert (claims.service, claims.approver, claims.action) == (
        "checkout-api",
        "dana",
        "restart_service",
    )
    assert claims.exp - claims.iat == 600
    assert len(claims.jti) == 32


def test_each_token_has_a_unique_jti():
    a = issue_token(KEY, service="s1", approver="a", now=NOW)
    b = issue_token(KEY, service="s1", approver="a", now=NOW)
    assert _verify(a, "s1").jti != _verify(b, "s1").jti


def test_expired():
    token = issue_token(KEY, service="checkout-api", approver="dana", ttl_s=60, now=NOW)
    assert _code(lambda: _verify(token, now=NOW + 60)) == "expired"


def test_not_yet_valid():
    token = issue_token(KEY, service="checkout-api", approver="dana", now=NOW + 3600)
    assert _code(lambda: _verify(token, now=NOW)) == "not_yet_valid"


def test_wrong_service():
    token = issue_token(KEY, service="payments-svc", approver="dana", now=NOW)
    assert _code(lambda: _verify(token, "checkout-api")) == "wrong_service"


def test_wrong_key_is_bad_signature():
    token = issue_token(b"other-key", service="checkout-api", approver="dana", now=NOW)
    assert _code(lambda: _verify(token)) == "bad_signature"


def test_tampered_claims_are_bad_signature():
    token = issue_token(KEY, service="payments-svc", approver="dana", now=NOW)
    version, payload, sig = token.split(".")
    claims = json.loads(base64.urlsafe_b64decode(payload + "=="))
    claims["service"] = "checkout-api"
    forged = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    assert _code(lambda: _verify(f"{version}.{forged}.{sig}")) == "bad_signature"


@pytest.mark.parametrize("token", ["", "garbage", "v2.a.b", "v1.only-two", "v1.a.b.c"])
def test_malformed(token):
    assert _code(lambda: _verify(token)) == "malformed"


def _sign_raw(claims: dict[str, object]) -> str:
    """Build a correctly signed token around arbitrary claims (to reach later checks)."""
    payload = _b64(json.dumps(claims).encode())
    return f"v1.{payload}.{_sign(KEY, payload)}"


def test_signed_but_invalid_claims_are_malformed():
    assert _code(lambda: _verify(_sign_raw({"service": "checkout-api"}))) == "malformed"


def test_ttl_longer_than_max_is_rejected_even_if_signed():
    claims = {
        "service": "checkout-api",
        "action": "restart_service",
        "approver": "dana",
        "jti": "j" * 32,
        "iat": int(NOW),
        "exp": int(NOW) + MAX_TTL_S + 1,
    }
    assert _code(lambda: _verify(_sign_raw(claims))) == "ttl_too_long"


def test_issue_rejects_bad_ttl():
    with pytest.raises(ValueError, match="ttl_s"):
        issue_token(KEY, service="s", approver="a", ttl_s=MAX_TTL_S + 1)
