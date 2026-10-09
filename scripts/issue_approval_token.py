"""Issue a restart_service approval token (the human approval step, until Module 4 automates it).

    uv run python scripts/issue_approval_token.py --service checkout-api --approver sachin

Reads the signing key from the Tools stack's secret with YOUR credentials. The agent never has
this permission. Prints only the token, so it can be piped.
"""

from __future__ import annotations

import argparse
import sys

from agent.config import InfraSettings, load_infra_settings
from scripts.kb_common import client, stack_outputs
from tools.common.approval import issue_token


def tools_stack_name(stage: str) -> str:
    return f"Ira-{stage}-Tools"


def signing_key(settings: InfraSettings) -> bytes:
    outputs = stack_outputs(client(settings, "cloudformation"), tools_stack_name(settings.stage))
    sm = client(settings, "secretsmanager")
    secret: str = sm.get_secret_value(SecretId=outputs["ApprovalSecretArn"])["SecretString"]
    return secret.encode()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", required=True)
    parser.add_argument("--approver", required=True)
    parser.add_argument("--ttl", type=int, default=900, help="seconds, max 3600")
    args = parser.parse_args(argv)
    settings = load_infra_settings()
    print(
        issue_token(
            signing_key(settings), service=args.service, approver=args.approver, ttl_s=args.ttl
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
