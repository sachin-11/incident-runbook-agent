.PHONY: help install lint typecheck test format synth precommit check deploy-kb ingest query teardown-kb build-lambda schemas deploy-tools invoke-tools

help:  ## List targets
	@grep -E "^[a-z-]+:.*##" $(MAKEFILE_LIST) | sed -E "s/:.*## /\t/"

install:  ## Install deps from the lockfile and the git hooks
	uv sync --locked
	uv run pre-commit install

lint:  ## Ruff lint and format check
	uv run ruff check .
	uv run ruff format --check .

typecheck:  ## mypy (strict)
	uv run mypy

test:  ## pytest, with coverage gate (>= 80%) on tools/
	uv run pytest --cov=tools --cov-report=term --cov-fail-under=80

format:  ## Auto-fix lint issues and format
	uv run ruff check --fix .
	uv run ruff format .

synth: build-lambda  ## cdk synth (needs Node; no AWS credentials)
	cd infra && npx --yes aws-cdk@2 synth --quiet

build-lambda:  ## Build the tool Lambda bundle in build/lambda (no Docker)
	uv run python scripts/build_lambda.py

schemas:  ## Regenerate tools/schemas/*.openapi.json from the tool models
	uv run python scripts/gen_tool_schemas.py

deploy-tools: build-lambda  ## Deploy the Tools stack (creates AWS resources)
	cd infra && npx --yes aws-cdk@2 deploy Ira-$${IRA_STAGE:-dev}-Tools --exclusively --require-approval never

invoke-tools:  ## Invoke every deployed tool Lambda with sample payloads
	uv run python scripts/invoke_tools.py

deploy-kb:  ## Deploy the KnowledgeBase stack (creates AWS resources)
	cd infra && npx --yes aws-cdk@2 deploy Ira-$${IRA_STAGE:-dev}-KnowledgeBase --exclusively --require-approval never

ingest:  ## Sync kb/docs to S3 and run a KB ingestion job
	uv run python scripts/ingest_kb.py

query:  ## make query Q="pods restarting after deploy"
	uv run python scripts/query_kb.py "$(Q)"

teardown-kb:  ## Destroy the KnowledgeBase stack
	bash scripts/teardown.sh

precommit:  ## Run every pre-commit hook on all files
	uv run pre-commit run --all-files

check: lint typecheck test  ## What CI runs
