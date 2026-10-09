.PHONY: help install lint typecheck test format synth precommit check

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

test:  ## pytest
	uv run pytest

format:  ## Auto-fix lint issues and format
	uv run ruff check --fix .
	uv run ruff format .

synth:  ## cdk synth (needs Node; no AWS credentials)
	cd infra && npx --yes aws-cdk@2 synth --quiet

precommit:  ## Run every pre-commit hook on all files
	uv run pre-commit run --all-files

check: lint typecheck test  ## What CI runs
