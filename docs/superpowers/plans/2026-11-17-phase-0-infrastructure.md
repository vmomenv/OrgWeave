# OrgWeave Phase 0 — Infrastructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline, user-selected) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a runnable monorepo development platform: Next.js web, FastAPI API, PostgreSQL+pgvector, Redis, Temporal, LiteLLM, MinIO, four worker skeletons, Alembic, health checks, tests, CI, and architecture docs.

**Architecture:** Modular monolith API plus independently deployable workers in one pnpm/Python monorepo. Infrastructure dependencies run in Docker Compose; app services are also containerized and runnable natively for development. No Phase 1+ business features are implemented.

**Tech Stack:** Next.js 15 (App Router, TypeScript, Tailwind, shadcn/ui), FastAPI, SQLAlchemy 2 async, Pydantic v2, Alembic, PostgreSQL 16 + pgvector, Redis 7, Temporal, LiteLLM, MinIO, pytest, ruff, GitHub Actions.

**Spec:** `docs/IMPLEMENTATION_MASTER_PROMPT.md` (Phase 0 section, lines 1066–1113 and 1291–1330).

## Global Constraints

- Only Phase 0; no tenant/auth/agent business features.
- No mocks presented as completed functionality; no fake API keys.
- All API routes under `/api/v1`; WebSocket under `/ws/v1`.
- Secrets only via `.env`; `.env.example` contains placeholders.
- Alembic owns the database schema.
- Every service has a real health/liveness signal and starts without external model keys.
- Tests must pass against real PostgreSQL, Redis, Temporal, MinIO, and LiteLLM containers.

## File Structure

```
.
├── apps/
│   ├── api/                     FastAPI app, Alembic, pytest
│   └── web/                     Next.js 15 app
├── workers/
│   ├── agent-worker/            queue consumer + Redis heartbeat
│   ├── temporal-worker/         Temporal worker + ping workflow
│   ├── skill-runner/            FastAPI skill execution service skeleton
│   └── watchdog-worker/         heartbeat staleness monitor
├── packages/
│   ├── shared-types/            TypeScript API contract types + API client
│   ├── agent-sdk/               Python agent tool contracts
│   ├── skill-sdk/               Python skill manifest contracts
│   └── shared-python/           settings, Redis, health, worker loop utilities
├── infra/
│   ├── docker/                  Dockerfiles for API, web, workers
│   ├── postgres/init/           extension bootstrap
│   ├── temporal/                dynamic config
│   ├── litellm/config.yaml      model gateway config
│   └── monitoring/README.md     monitoring plan (no fake service)
├── docs/                        architecture + subsystem docs
├── scripts/                     bootstrap, health-check, wait-for-services
├── .github/workflows/ci.yml
├── docker-compose.yml
├── Makefile
├── .env.example
└── README.md
```

## Review Focus

- Running `make up` twice must not corrupt volumes or fail on existing resources.
- A missing optional model API key must not stop LiteLLM/API/workers from starting.
- Readiness must report the specific failing dependency, not a generic 500.
- Redis/HTTP clients must use timeouts so health checks cannot hang.
- Worker shutdown must be graceful and must not leave stale heartbeat state uncontested.

---

### Task 1: Repository foundation

**Files:** `.gitignore`, `.env.example`, `package.json`, `pnpm-workspace.yaml`, `tsconfig.base.json`, `Makefile`, `scripts/bootstrap.sh`, `scripts/health-check.sh`

**Interfaces:**
- Produces: `make install`, `make up`, `make down`, `make test`, `make lint`, `make migrate`, `make health`, `make dev-api`, `make dev-web`; env contract `DATABASE_URL`, `REDIS_URL`, `TEMPORAL_HOST`, `LITELLM_BASE_URL`, `LITELLM_MASTER_KEY`, `MINIO_*`, `S3_*`, `API_BASE_URL`, `NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_WS_BASE_URL`.

- [ ] Write root workspace files and env template.
- [ ] Write bootstrap/health scripts with timeouts and non-zero failure exits.
- [ ] Verify `bash -n` on scripts and `make help`.
- [ ] Commit.

### Task 2: Infrastructure Compose

**Files:** `docker-compose.yml`, `infra/postgres/init/01-extensions.sql`, `infra/temporal/dynamicconfig/development-sql.yaml`, `infra/litellm/config.yaml`, `infra/minio/init.sh`

**Interfaces:**
- Produces services: `postgres:5432`, `redis:6379`, `temporal:7233`, `temporal-ui:8080`, `litellm:4000`, `minio:9000/9001`, `minio-init`, `api:8000`, `web:3000`, workers (no ports), with stable healthchecks.

- [ ] Write pinned infrastructure services and named volumes.
- [ ] Add app/worker build targets (profile-free) and dependency health ordering.
- [ ] Verify `docker compose config -q`.
- [ ] Start infrastructure and verify healthchecks.
- [ ] Commit.

### Task 3: Shared Python package

**Files:** `packages/shared-python/pyproject.toml`, `src/orgweave_shared/{__init__,settings,redis,health,worker}.py`, tests.

**Interfaces:**
- Produces: `OrgWeaveSettings` (env-driven), `create_redis(settings)`, `heartbeat_loop(...)`, `WorkerHeartbeat`, `run_worker_loop(handler,...)`.

- [ ] Write failing tests for settings defaults/URL validation and heartbeat payload.
- [ ] Implement package.
- [ ] Run `pytest packages/shared-python/tests`.
- [ ] Commit.

### Task 4: FastAPI backend + Alembic

**Files:** `apps/api/pyproject.toml`, `app/main.py`, `app/core/{config,logging,db}.py`, `app/infrastructure/health/{postgres,redis,minio,temporal,litellm}.py`, `app/api/v1/{router,health,meta}.py`, `app/ws/v1.py`, `alembic.ini`, `alembic/env.py`, `alembic/versions/0001_phase0_baseline.py`, tests.

**Interfaces:**
- `GET /api/v1/health/live` → 200 `{status, service, version, timestamp}`.
- `GET /api/v1/health/ready` → 200/503 `{status, checks: [{name,status,latency_ms,detail?}]}`.
- `GET /api/v1/meta` → API name/version/prefixes.
- `WS /ws/v1` → hello + heartbeat frames.
- Alembic baseline creates `vector` extension and `system_settings` table.
- Consumes `orgweave_shared` settings/Redis helpers.

- [ ] Write failing unit tests for live endpoint, readiness aggregation with failing dependency, and settings.
- [ ] Implement app and health probes with timeouts.
- [ ] Write integration tests (Postgres/Redis/MinIO/Temporal/LiteLLM) gated by `ORGWEAVE_INTEGRATION=1`.
- [ ] Run migrations against real Postgres; verify pgvector + table.
- [ ] Run pytest (unit + integration) with infra up.
- [ ] Commit.

### Task 5: Worker skeletons

**Files:** each worker `pyproject.toml`, package modules, Dockerfiles; tests for agent job envelope, watchdog stale detection, Temporal workflow.

**Interfaces:**
- Agent worker: consumes JSON jobs from Redis list `orgweave:agent:jobs`, validates `AgentJob` envelope, handles `system.ping`, dead-letters invalid/unsupported jobs, heartbeat key `orgweave:worker:agent-worker:heartbeat`.
- Temporal worker: task queue `orgweave-phase0`, workflow `PingWorkflow`, activity `ping_activity` returning ISO timestamp; heartbeat key.
- Skill runner: FastAPI `/health/live`, `/health/ready` checking Redis only; no execution endpoint claimed.
- Watchdog: scans `orgweave:worker:*:heartbeat`, emits stale alerts to Redis channel and log; heartbeat key.

- [ ] Write failing tests for envelope validation/dead-letter routing and stale detection.
- [ ] Implement worker packages.
- [ ] Start all four workers against real infra; verify heartbeats.
- [ ] Run Temporal `PingWorkflow` end-to-end via client script/test.
- [ ] Commit.

### Task 6: Next.js web

**Files:** `apps/web/package.json`, `next.config.ts`, `tailwind.config.ts`, `app/{layout,page}.tsx`, `app/globals.css`, `components/ui/{button,badge,card,separator}.tsx`, `lib/{api,cn}.ts`, `components/system-status.tsx`, `components/theme-toggle.tsx`, tests or lint config.

**Interfaces:**
- Consumes `@orgweave/shared-types` (`HealthReady`, `ApiEnvelope`).
- Server-side fetch of `${API_INTERNAL_URL}/api/v1/health/ready` and `/meta` with timeout; renders real dependency status, dark/light theme toggle.

- [ ] Scaffold Next.js/Tailwind/shadcn base.
- [ ] Implement status dashboard from live API.
- [ ] Run lint, typecheck, production build; open page with API running.
- [ ] Commit.

### Task 7: CI, docs, final verification

**Files:** `.github/workflows/ci.yml`, `docs/{ARCHITECTURE,DATABASE,API,SECURITY,AGENT_RUNTIME,TAKEOVER,ROADMAP}.md`, `README.md`, `scripts/verify-phase0.sh`.

**Interfaces:**
- CI jobs: `compose-config`, `backend` (Postgres/Redis services, migrations, pytest), `frontend` (pnpm lint/typecheck/build), `workers` (unit tests).

- [ ] Write CI workflow and docs (Phase 0 status honest, future phases marked planned).
- [ ] Run full `scripts/verify-phase0.sh`: compose config, service health, migrations, pytest, web build.
- [ ] Record actual results and remaining gaps in README.
- [ ] Commit.

## Verification Matrix

| Acceptance item | Command |
|---|---|
| compose config | `sg docker -c "docker compose config -q"` |
| infra starts | `sg docker -c "docker compose up -d postgres redis temporal temporal-ui litellm minio minio-init"` |
| web opens | `curl -fsS http://localhost:3000` |
| API health | `curl -fsS http://localhost:8000/api/v1/health/ready` |
| pgvector | `psql -c "SELECT extversion FROM pg_extension WHERE extname='vector'"` |
| Redis | `redis-cli PING` |
| Temporal | `temporal operator cluster health` via container |
| LiteLLM | `curl /health/liveliness` |
| MinIO | `curl /minio/health/live` |
| Alembic | `alembic upgrade head` / `downgrade base` / `upgrade head` |
| pytest | `pytest` (unit + integration) |
| frontend | `pnpm lint && pnpm typecheck && pnpm build` |
