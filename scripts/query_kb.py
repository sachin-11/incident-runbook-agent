"""Retrieve the top-k chunks for a query and show scores and source citations.

    uv run python scripts/query_kb.py "pods restarting repeatedly after deploy"
    uv run python scripts/query_kb.py "slow checkout" -k 3 --service checkout-api --doc-type runbook
    uv run python scripts/query_kb.py "cert problem" --alert TLSCertExpired --json

Filters combine with AND. `--alert` matches docs whose `alert_names` list contains the value.
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
from typing import Any

from pydantic import BaseModel

from agent.config import load_kb_settings
from scripts.kb_common import client, kb_stack_name, load_stack_outputs

INDENT = "    "


class Hit(BaseModel):
    rank: int
    score: float
    doc_id: str
    title: str
    source_uri: str
    text: str


def build_filter(
    *,
    service: str | None = None,
    severity: str | None = None,
    doc_type: str | None = None,
    alert: str | None = None,
) -> dict[str, Any] | None:
    """Bedrock retrieval filter for the metadata in kb/docs/*.metadata.json."""
    clauses: list[dict[str, Any]] = [
        {"equals": {"key": key, "value": value}}
        for key, value in (("service", service), ("severity", severity), ("doc_type", doc_type))
        if value
    ]
    if alert:
        clauses.append({"listContains": {"key": "alert_names", "value": alert}})
    if not clauses:
        return None
    return clauses[0] if len(clauses) == 1 else {"andAll": clauses}


def to_hits(results: list[dict[str, Any]]) -> list[Hit]:
    hits = []
    for rank, r in enumerate(results, start=1):
        meta = r.get("metadata", {})
        hits.append(
            Hit(
                rank=rank,
                score=float(r.get("score", 0.0)),
                doc_id=str(meta.get("doc_id", "?")),
                title=str(meta.get("title", "?")),
                source_uri=r.get("location", {}).get("s3Location", {}).get("uri", "?"),
                text=r["content"]["text"],
            )
        )
    return hits


def retrieve(
    agent_runtime: Any, kb_id: str, query: str, k: int, flt: dict[str, Any] | None
) -> list[Hit]:
    search: dict[str, Any] = {"numberOfResults": k}
    if flt:
        search["filter"] = flt
    resp = agent_runtime.retrieve(
        knowledgeBaseId=kb_id,
        retrievalQuery={"text": query},
        retrievalConfiguration={"vectorSearchConfiguration": search},
    )
    return to_hits(resp["retrievalResults"])


def render(query: str, hits: list[Hit]) -> str:
    lines = [f'Query: "{query}"  ({len(hits)} results)', ""]
    for h in hits:
        lines.append(f"#{h.rank}  score={h.score:.4f}  [{h.doc_id}] {h.title}")
        lines.append(f"    source: {h.source_uri}")
        excerpt = " ".join(h.text.split())[:240]
        wrapped = textwrap.wrap(excerpt, width=96, initial_indent=INDENT, subsequent_indent=INDENT)
        lines.extend(wrapped)
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query")
    parser.add_argument("-k", type=int, default=5, help="number of chunks (default 5)")
    parser.add_argument("--service")
    parser.add_argument("--severity")
    parser.add_argument("--doc-type", choices=["runbook", "postmortem"])
    parser.add_argument("--alert", help="alert name that must be in the doc's alert_names")
    parser.add_argument("--json", action="store_true", help="print hits as JSON")
    args = parser.parse_args(argv)

    settings = load_kb_settings()
    kb_id = (
        settings.knowledge_base_id
        or load_stack_outputs(
            client(settings, "cloudformation"), kb_stack_name(settings.stage)
        ).knowledge_base_id
    )
    flt = build_filter(
        service=args.service, severity=args.severity, doc_type=args.doc_type, alert=args.alert
    )
    hits = retrieve(client(settings, "bedrock-agent-runtime"), kb_id, args.query, args.k, flt)
    if args.json:
        print(json.dumps([h.model_dump() for h in hits], indent=2))
    else:
        print(render(args.query, hits))
    return 0 if hits else 1


if __name__ == "__main__":
    sys.exit(main())
