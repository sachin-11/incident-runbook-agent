# tools/

Typed tools the agent can call. Each one is a Lambda (one folder, one handler) backed by a
simulated environment. AgentCore Gateway will expose them as MCP tools in the agent module.

| Tool | Group | Input | Notes |
|---|---|---|---|
| `get_logs` | diagnostics | service, window_minutes, level, limit | newest first, sanitized, 8 KB text budget |
| `get_service_health` | diagnostics | service | status, replicas, checks, last restart |
| `get_recent_deploys` | diagnostics | service, limit | newest first |
| `get_metrics` | diagnostics | service, metric, window_minutes | at most 60 points + min/max/avg/last/change |
| `restart_service` | remediation (**risky**) | service, reason, request_id, approval_token, dry_run | see below |

**Contract.** The Lambda event is the tool's arguments as a JSON object, the same shape AgentCore
Gateway sends. Inputs are pydantic models with `extra="forbid"`. The output is the tool's model or
`{"error": {"code", "message"}}`. Error codes: `invalid_input`, `unknown_service`,
`unknown_scenario`, `internal_error`. Every call logs one JSON `tool_result` line with
`request_id`, `trace_id` and latency.

**Untrusted text.** Every string that comes from the environment goes through
`common/sanitize.py`. That strips ANSI, control and invisible/bidi characters, caps the length
per field and per response, and flags instruction-like content. Flagged items have
`flagged: true`, and the response sets `untrusted_content` and `untrusted_flags`. The text is
kept as evidence, never followed.

**restart_service rules** (`restart_service/handler.py`):
- **Approval:** needs an HMAC-signed `approval_token` (`common/approval.py`). The token is
  bound to the service and action, expires in at most 1 h, and the key lives in Secrets
  Manager. Issue one with `scripts/issue_approval_token.py`.
- **Single-use token:** the token's `jti` is claimed in DynamoDB together with the request.
  Using it for another request returns `token_replayed`.
- **Idempotent:** the same `request_id` with the same input returns the stored result
  (`idempotent_replay: true`). The same id with different input returns `idempotency_conflict`.
- **Audit:** every attempt is written to the audit table (`common/audit.py`). The role can only
  PutItem and GetItem, so the table is append-only.
- **Dry run:** `dry_run: true` validates everything and returns `would_execute`. It restarts
  nothing and does not use the token.

**Simulator** (`sim/`): scenarios in `sim/scenarios/*.json` override a healthy baseline:
`healthy`, `crashloop_after_deploy`, `db_pool_exhaustion`, `memory_leak` and `log_injection`.
The Lambda default comes from `SIM_SCENARIO_ID` (`IRA_SIM_SCENARIO_ID`). Tests and scripts can
pass `scenario_id`, but it is hidden from the schema, so the model cannot choose it.

**Schemas:** `schemas/diagnostics.openapi.json` and `schemas/remediation.openapi.json` (OpenAPI
3.1) are generated from the models with `make schemas`. A test fails if they drift.

**Build and deploy:** run `make build-lambda` (builds the arm64 bundle in `build/lambda`, no
Docker needed), then `make deploy-tools` and `make invoke-tools`.
