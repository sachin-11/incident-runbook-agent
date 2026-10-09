# agent/

- `config.py` holds the typed settings (pydantic-settings, `IRA_` prefix). `KbSettings` is the
  subset that infra and the KB scripts use; `Settings` adds the agent fields. See `.env.example`.

Planned (agent module): a Strands Agents app that AgentCore Runtime hosts. It retrieves from the
KB, calls diagnostic tools through AgentCore Gateway, and stops at an approval step before
proposing any state-changing action. AgentCore Policy refuses unapproved calls at the Gateway.

Status: settings only.
