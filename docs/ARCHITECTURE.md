# Architecture

> Status after Module 3: settings, logging, CI, the Knowledge Base stack and the Tools stack are
> built and deployed in ap-south-1. KB ingestion is blocked by the account's Bedrock throttling.
> Everything marked *(planned)* is the target design. Since 2026-10-09 the agent layer targets
> **Amazon Bedrock AgentCore** instead of Bedrock Agents. This diagram is updated each module.

## Request flow (target)

```
 Alert (CloudWatch alarm / webhook)                                         (planned)
        |
        v
 +------------------------------ AgentStack (AgentCore) ------------------------------+
 |                                                                                     |
 |  AgentCore Runtime: Strands agent (model via Bedrock)          AgentCore Memory     |
 |     |                      |                        |          (incident history)   |
 |     | retrieve             | tool calls (MCP)       | risky fix?                    |
 |     v                      v                        v                               |
 |  Knowledge Base       AgentCore Gateway        Approval step                         |
 |  (KnowledgeBase-        |  AgentCore Policy     -> human approves / rejects          |
 |   Stack, built)         |  (Cedar): read-only    -> only then may Policy allow a     |
 |                         |  allowed, writes need      state-changing tool             |
 |                         |  an approval                                               |
 |                         v                                                           |
 |       ToolsStack Lambdas: logs, health, deploys, metrics, restart (token + audit)   |
 +-------------------------------------------------------------------------------------+
       ^
  kb/docs (runbooks + postmortems) -> S3 -> Titan v2 embeddings -> S3 Vectors index

 JSON logs (request_id / trace_id) + AgentCore Observability (OTel -> CloudWatch)
        |
        v
 ObservabilityStack: traces, dashboards, cost + latency, alarms              (planned)
 evals/: golden incidents -> RAGAS (CI gate) + AgentCore Evaluations          (planned)
```

## Stacks

All stack names are `Ira-<stage>-<Name>`, with stage `dev | staging | prod`.

| Stack | Depends on | Holds | Status |
|---|---|---|---|
| `KnowledgeBaseStack` | - | Bedrock KB, S3 docs bucket, S3 Vectors bucket + index, data source | built, deployed (ap-south-1) |
| `ToolsStack` | - | 5 tool Lambdas (4 read-only + risky restart), audit table, approval signing key | built, deployed (ap-south-1) |
| `AgentStack` | KB, Tools | AgentCore Runtime, Gateway + Lambda targets, Policy, Memory | empty |
| `ObservabilityStack` | Agent | AgentCore Observability, dashboards, alarms, budgets | empty |

## Why AgentCore

| Need | AgentCore piece | Replaces |
|---|---|---|
| Host the agent | Runtime (Strands, any model) | Bedrock Agent + alias |
| Expose tools | Gateway (Lambda to MCP) | Action groups |
| Read-only and approval enforcement | Policy (Cedar, checked on every tool call) | Return-of-control + checks in code |
| Tracing | Observability (OTel to CloudWatch) | Custom X-Ray wiring |
| Online quality scoring | Evaluations | Runs alongside the RAGAS CI gate |
| Incident history and feedback | Memory | Custom store |

Constraint: AgentCore still calls models through Bedrock, so the Bedrock quota blocker applies to
it as well. The Runtime can also call a non-Bedrock model API if that becomes necessary.

## Cross-cutting pieces (built)

- **Settings** (`agent/config.py`): `KbSettings` (region, embedding model, dimensions, stage, KB
  ID) and `Settings` (adds the agent model and agent IDs, budget caps and timeouts). Everything
  comes from `IRA_*` env vars or `.env`. Region and model IDs have no defaults in code.
- **Logging** (`observability/logging.py`): one JSON object per line. `log_context()` binds
  `request_id` and `trace_id` (taken from the X-Ray header when running in Lambda).
- **KB content and config**: `kb/docs` has 26 docs with metadata. `kb/chunking.yaml` is the
  versioned chunking config.
- **Quality gate**: ruff, mypy (strict), pytest and pre-commit locally; the same checks plus
  `cdk synth` in GitHub Actions.
