# kb/

Source documents for the Bedrock Knowledge Base.

```
kb/
  chunking.yaml                 # versioned chunking config, read by infra at synth time
  docs/runbooks/rb-0NN-*.md     # 20 runbooks
  docs/postmortems/pm-0NN-*.md  # 6 postmortems
  docs/**/<doc>.md.metadata.json
```

**Template** (checked by `tests/test_kb_docs.py`): `# Runbook: <title>` or `# Postmortem: <title>`,
then these sections in order: Symptoms, Impact, Diagnosis steps, Mitigation, Rollback, Escalation,
Related alerts. Postmortems also have Summary, Timeline, Root cause, Action items.

**Metadata** (`<doc>.md.metadata.json`, Bedrock format) used for retrieval filters:
`doc_id`, `doc_type` (runbook|postmortem), `title`, `service`, `severity` (sev1-4),
`alert_names` (must equal the "Related alerts" list).

**Workflow:** edit docs, run `make test`, then `make ingest`. Changing `chunking.yaml` requires bumping
`version`, redeploying (`make deploy-kb`) and re-ingesting.
