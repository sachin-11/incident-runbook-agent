"""Append-only audit trail for risky tools, in DynamoDB.

Item kinds, all in one table keyed by `pk`:
- `req#<request_id>`: the outcome of an executed request; makes the tool idempotent.
- `tok#<jti>`: marks an approval token as used; makes tokens single-use.
- `evt#<uuid>`: every attempt (accepted, rejected, dry run) for the audit log.

The Lambda role may only PutItem/GetItem, so nothing can be edited or deleted after the fact.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

_BOTO = Config(connect_timeout=2, read_timeout=3, retries={"max_attempts": 2})


class AlreadyClaimed(Exception):  # noqa: N818
    """The request id or the token was already used."""


class AuditStore:
    def __init__(self, table_name: str, client: Any = None) -> None:
        self.table = table_name
        self.client = client or boto3.client("dynamodb", config=_BOTO)

    @classmethod
    def from_env(cls) -> AuditStore:
        return cls(os.environ["AUDIT_TABLE"])

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    def record_event(self, **fields: Any) -> str:
        event_id = uuid.uuid4().hex
        item = {"pk": {"S": f"evt#{event_id}"}, "ts": {"S": self._now()}}
        item["body"] = {"S": json.dumps(fields, default=str, sort_keys=True)}
        item["outcome"] = {"S": str(fields.get("outcome", ""))}
        self.client.put_item(TableName=self.table, Item=item)
        return event_id

    def get_request(self, request_id: str) -> dict[str, Any] | None:
        resp = self.client.get_item(
            TableName=self.table, Key={"pk": {"S": f"req#{request_id}"}}, ConsistentRead=True
        )
        item = resp.get("Item")
        if not item:
            return None
        stored: dict[str, Any] = json.loads(item["body"]["S"])
        return stored

    def token_used(self, jti: str) -> bool:
        resp = self.client.get_item(
            TableName=self.table, Key={"pk": {"S": f"tok#{jti}"}}, ConsistentRead=True
        )
        return "Item" in resp

    def claim(self, *, request_id: str, jti: str, record: dict[str, Any]) -> None:
        """Atomically store the request outcome and mark the token used, or raise AlreadyClaimed."""
        ts = self._now()
        body = json.dumps(record, default=str, sort_keys=True)
        condition = "attribute_not_exists(pk)"
        try:
            self.client.transact_write_items(
                TransactItems=[
                    {
                        "Put": {
                            "TableName": self.table,
                            "Item": {
                                "pk": {"S": f"req#{request_id}"},
                                "ts": {"S": ts},
                                "body": {"S": body},
                            },
                            "ConditionExpression": condition,
                        }
                    },
                    {
                        "Put": {
                            "TableName": self.table,
                            "Item": {
                                "pk": {"S": f"tok#{jti}"},
                                "ts": {"S": ts},
                                "request_id": {"S": request_id},
                            },
                            "ConditionExpression": condition,
                        }
                    },
                ]
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "TransactionCanceledException":
                raise AlreadyClaimed(request_id) from None
            raise
