# Architecture

> Status after Module 1: only the skeleton exists (settings, logging, CI, empty CDK stacks).
> Everything marked *(planned)* is the target design and gets filled in by later modules. This
> diagram is updated at the end of each module.

## Request flow (target)

```
 Alert (CloudWatch alarm / webhook)                                     (planned)
        |
        v
 +--------------------------- AgentStack ---------------------------+
 |  Bedrock Agent (alias per stage)  +  Guardrails                   |
 |     |                    |                         |              |
 |     | retrieve           | invoke action group     | risky fix?   |
 |     v                    v                         v              |
 |  Knowledge Base     ToolsStack Lambdas        Return of control   |
 |  (KnowledgeBase-    (read-only: logs,         -> human approves   |
 |   Stack)             health, deploys,           or rejects        |
 |     ^                metrics; timeouts)                           |
 +-----|-------------------------------------------------------------+
       |
  kb/ runbooks + postmortems -> S3 -> embeddings -> vector store

 Every step logs JSON with request_id / trace_id
        |
        v
 ObservabilityStack: traces, dashboards, cost + latency, alarms     (planned)
 evals/: golden incidents -> RAGAS + custom scores -> CI gate        (planned)
```

## Stacks

All stack names are `Ira-<stage>-<Name>`, with stage `dev | staging | prod`.

| Stack | Depends on | Holds | Status |
|---|---|---|---|
| `KnowledgeBaseStack` | - | KB, S3 source bucket, vector store | empty |
| `ToolsStack` | - | Diagnostic Lambdas | empty |
| `AgentStack` | KB, Tools | Agent, alias, action groups, guardrails | empty |
| `ObservabilityStack` | Agent | Dashboards, alarms, budgets | empty |

## Cross-cutting pieces (built)

- **Settings** (`agent/config.py`): region, model IDs, KB/agent IDs, stage, budget caps and
  timeouts. Everything comes from `IRA_*` env vars or `.env`. Region and model IDs have no
  defaults in code.
- **Logging** (`observability/logging.py`): one JSON object per line. `log_context()` binds
  `request_id` (generated if missing) and `trace_id` (taken from Lambda's X-Ray header if present)
  to every line in a block.
- **Quality gate**: ruff, mypy (strict), pytest and pre-commit locally; the same checks plus
  `cdk synth` in GitHub Actions.
