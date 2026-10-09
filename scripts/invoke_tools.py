"""Invoke every deployed tool Lambda with sample payloads and print the results.

    uv run python scripts/invoke_tools.py [--full]

Runs the read tools against simulator scenarios, then walks restart_service through its rules:
no token (rejected), dry run, approved restart, same request again (idempotent), token reuse
(replay rejected). Uses your credentials for lambda:InvokeFunction and to issue the token.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from typing import Any

from agent.config import load_infra_settings
from scripts.issue_approval_token import signing_key, tools_stack_name
from scripts.kb_common import client, stack_outputs
from tools.common.approval import issue_token

READ_SAMPLES: list[tuple[str, dict[str, Any]]] = [
    (
        "get_service_health",
        {"service": "checkout-api", "scenario_id": "crashloop_after_deploy"},
    ),
    (
        "get_recent_deploys",
        {"service": "checkout-api", "limit": 2, "scenario_id": "crashloop_after_deploy"},
    ),
    (
        "get_logs",
        {
            "service": "checkout-api",
            "level": "ERROR",
            "window_minutes": 15,
            "limit": 3,
            "scenario_id": "crashloop_after_deploy",
        },
    ),
    (
        "get_metrics",
        {
            "service": "checkout-api",
            "metric": "db_connections",
            "window_minutes": 30,
            "scenario_id": "db_pool_exhaustion",
        },
    ),
    (
        "get_logs",
        {"service": "payments-svc", "level": "ERROR", "scenario_id": "log_injection"},
    ),
]


def _pascal(name: str) -> str:
    return "".join(part.title() for part in name.split("_"))


def invoke(lam: Any, fn: str, payload: dict[str, Any]) -> dict[str, Any]:
    resp = lam.invoke(FunctionName=fn, Payload=json.dumps(payload).encode())
    body: dict[str, Any] = json.loads(resp["Payload"].read())
    if resp.get("FunctionError"):
        body = {"FUNCTION_ERROR": resp["FunctionError"], **body}
    return body


def show(title: str, payload: dict[str, Any], out: dict[str, Any], full: bool) -> None:
    shown = dict(out)
    if not full and isinstance(shown.get("points"), list):
        pts = shown["points"]
        shown["points"] = [*pts[:2], f"... {len(pts) - 4} more ...", *pts[-2:]]
    print(f"\n=== {title}")
    print(f"payload: {json.dumps(payload)}")
    print(json.dumps(shown, indent=2, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", action="store_true", help="print full metric series")
    args = parser.parse_args(argv)

    settings = load_infra_settings()
    outputs = stack_outputs(client(settings, "cloudformation"), tools_stack_name(settings.stage))
    names = {
        k.removesuffix("FunctionName"): v for k, v in outputs.items() if k.endswith("FunctionName")
    }
    lam = client(settings, "lambda")
    ok = True

    for tool, payload in READ_SAMPLES:
        out = invoke(lam, names[_pascal(tool)], payload)
        ok &= "error" not in out and "FUNCTION_ERROR" not in out
        show(tool, payload, out, args.full)

    restart = names["RestartService"]
    base = {
        "service": "checkout-api",
        "reason": "New pods crashloop after 4.12.0 (missing DATABASE_URL); restart after fix",
        "scenario_id": "crashloop_after_deploy",
    }
    req_a, req_b = f"demo-{uuid.uuid4().hex[:12]}", f"demo-{uuid.uuid4().hex[:12]}"
    token = issue_token(signing_key(settings), service="checkout-api", approver="invoke-script")
    steps: list[tuple[str, dict[str, Any], str]] = [
        ("restart_service WITHOUT token", {**base, "request_id": req_a}, "rejected"),
        (
            "restart_service dry run with token",
            {**base, "request_id": req_a, "approval_token": token, "dry_run": True},
            "dry_run",
        ),
        (
            "restart_service with valid token",
            {**base, "request_id": req_a, "approval_token": token},
            "restarted",
        ),
        (
            "restart_service same request_id again (idempotent)",
            {**base, "request_id": req_a, "approval_token": token},
            "restarted",
        ),
        (
            "restart_service token reused for a new request (replay)",
            {**base, "request_id": req_b, "approval_token": token},
            "rejected",
        ),
    ]
    for title, payload, expected in steps:
        out = invoke(lam, restart, payload)
        ok &= out.get("status") == expected
        shown = (
            {**payload, "approval_token": "<redacted>"} if "approval_token" in payload else payload
        )
        show(f"{title} (expect {expected})", shown, out, args.full)

    print("\nALL AS EXPECTED" if ok else "\nSOME RESULTS WERE UNEXPECTED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
