# tools/

Lambda tools for read-only diagnostics (logs, health, deploys, metrics). AgentCore Gateway
exposes them to the agent as MCP tools; AgentCore Policy decides which calls are allowed.

Rules: typed inputs and outputs, read-only, a timeout from `Settings.tool_timeout_s`, JSON logs
via `observability.logging` inside `log_context()`.

Status: empty.
