SHELL := /bin/bash
.DEFAULT_GOAL := help

PYTHON ?= python3
VENV := .venv
PIP := $(VENV)/bin/pip
PY := $(VENV)/bin/python
DC ?= docker compose
COMPOSE_FILE := docker-compose.yml

.PHONY: help bootstrap install env infra up down restart logs ps health migrate migrate-down \
        db-bootstrap test test-unit test-integration lint format api web workers workers-stop temporal-test verify verify-phase1 clean

help: ## Show available commands
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

bootstrap: ## Create .env, virtualenv, install all dependencies
	@bash scripts/bootstrap.sh

install: ## Install Python + Node dependencies
	@bash scripts/ensure-venv.sh
	$(PIP) install --upgrade pip
	$(PIP) install -e packages/shared-python -e packages/agent-sdk -e packages/skill-sdk -e apps/api
	$(PIP) install -e workers/agent-worker -e workers/temporal-worker -e workers/skill-runner -e workers/watchdog-worker
	$(PIP) install -r requirements-dev.txt
	pnpm install

env: ## Copy .env.example to .env when missing
	@test -f .env || (cp .env.example .env && echo "Created .env from .env.example")

infra: ## Start dependency services (Postgres, Redis, Temporal, LiteLLM, MinIO)
	$(DC) -f $(COMPOSE_FILE) up -d postgres redis temporal temporal-ui litellm minio

up: ## Build and start the full stack
	$(DC) -f $(COMPOSE_FILE) up -d --build

down: ## Stop the stack (keeps volumes)
	$(DC) -f $(COMPOSE_FILE) down

restart: ## Restart the full stack
	$(DC) -f $(COMPOSE_FILE) restart

logs: ## Follow logs for all services
	$(DC) -f $(COMPOSE_FILE) logs -f --tail=100

ps: ## Show service status
	$(DC) -f $(COMPOSE_FILE) ps

health: ## Check all service health endpoints
	@bash scripts/health-check.sh

migrate: ## Apply Alembic migrations
	cd apps/api && ../../$(VENV)/bin/alembic upgrade head

db-bootstrap: ## Ensure the non-superuser application role exists
	@bash scripts/db-bootstrap.sh

migrate-down: ## Roll back the latest migration
	cd apps/api && ../../$(VENV)/bin/alembic downgrade -1

test: ## Run the complete Python test suite
	$(PY) -m pytest

test-unit: ## Run fast unit tests only
	$(PY) -m pytest -m "not integration"

test-integration: ## Run integration tests (requires make infra)
	$(PY) -m pytest -m integration

lint: ## Run backend lint plus frontend lint/typecheck
	$(VENV)/bin/ruff check apps/api packages workers scripts conftest.py
	$(VENV)/bin/ruff format --check apps/api packages workers scripts conftest.py
	pnpm lint
	pnpm typecheck

format: ## Format Python code
	$(VENV)/bin/ruff format apps/api packages workers scripts
	$(VENV)/bin/ruff check --fix apps/api packages workers scripts

api: ## Run API natively (requires make infra and make migrate)
	cd apps/api && ../../$(VENV)/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

web: ## Run web app natively
	pnpm --filter @orgweave/web dev

workers: ## Run all workers natively in the background (logs in .data/logs)
	@bash scripts/run-workers.sh

workers-stop: ## Stop natively running workers
	@bash scripts/stop-workers.sh

temporal-test: ## Execute the Phase 0 Temporal ping workflow end-to-end
	$(PY) scripts/temporal_smoke.py

verify: ## Full Phase 0 acceptance verification
	@bash scripts/verify-phase0.sh

verify-phase1: ## Phase 1 acceptance (auth, org, RLS boundary, web)
	@bash scripts/verify-phase1.sh

clean: ## Remove build artifacts and caches (keeps .env and volumes)
	rm -rf .pytest_cache .ruff_cache .data/logs
	find apps packages workers -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf apps/web/.next apps/web/node_modules node_modules
