#!/usr/bin/env bash
# Phase 0 acceptance verification. Requires the full stack to be running
# (`make up`) and Python/Node dependencies installed (`make install`).
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  set -a; source .env; set +a
fi

DC="${DC:-docker compose}"
VERIFY_LOG="$(mktemp -t orgweave-verify.XXXXXX.log)"
trap 'rm -f "$VERIFY_LOG"' EXIT
PASS=0
FAIL=0

pass() { printf '  \033[32mPASS\033[0m %s\n' "$1"; PASS=$((PASS + 1)); }
fail() { printf '  \033[31mFAIL\033[0m %s\n' "$1"; FAIL=$((FAIL + 1)); }
section() { printf '\n\033[1m%s\033[0m\n' "$1"; }

check_cmd() {
  local label="$1"; shift
  if "$@" >"$VERIFY_LOG" 2>&1; then
    pass "$label"
  else
    fail "$label"
    sed 's/^/    /' "$VERIFY_LOG" | tail -15
  fi
}

check_http() {
  local label="$1" url="$2" expected="${3:-200}"
  local code
  code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 "$url" 2>/dev/null || echo 000)"
  if [[ "$code" == "$expected" ]]; then
    pass "$label ($url -> $code)"
  else
    fail "$label ($url -> $code, expected $expected)"
  fi
}

section "1. Compose configuration"
check_cmd "docker compose config" $DC config -q

section "2. Service endpoints"
check_http "API liveness" "http://localhost:${API_PORT:-8000}/api/v1/health/live"
check_http "API readiness" "http://localhost:${API_PORT:-8000}/api/v1/health/ready"
check_http "Web" "http://localhost:3000"
check_http "LiteLLM liveness" "http://localhost:4000/health/liveliness"
check_http "MinIO liveness" "http://localhost:9000/minio/health/live"
check_http "Temporal UI" "http://localhost:8080"
check_http "Skill Runner" "http://localhost:8001/health/ready"

section "3. Data services"
check_cmd "pgvector extension" $DC exec -T postgres psql -U "${POSTGRES_USER:-orgweave}" -d "${POSTGRES_DB:-orgweave}" -tAc "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
check_cmd "Redis PING" $DC exec -T redis redis-cli ping
check_cmd "Temporal cluster health" $DC exec -T temporal temporal operator cluster health --address temporal:7233
check_cmd "MinIO bucket via API" bash -c "curl -fsS http://localhost:${API_PORT:-8000}/api/v1/health/ready | grep -q 'bucket=orgweave present=true'"

section "4. Database migration"
if [[ -x .venv/bin/alembic ]]; then
  check_cmd "alembic upgrade head" bash -c "cd apps/api && ../../.venv/bin/alembic upgrade head"
  check_cmd "alembic current" bash -c "cd apps/api && ../../.venv/bin/alembic current | grep 0001_phase0"
else
  check_cmd "alembic current (api container)" $DC exec -T api alembic current
fi

section "5. Python tests (unit + integration)"
if [[ -x .venv/bin/python ]]; then
  check_cmd "pytest" env ORGWEAVE_INTEGRATION=1 .venv/bin/python -m pytest -q
else
  fail "pytest (missing .venv; run 'make install')"
fi

section "6. Frontend checks"
if command -v pnpm >/dev/null 2>&1; then
  check_cmd "shared-types typecheck" pnpm --filter @orgweave/shared-types typecheck
  check_cmd "web lint" pnpm --filter @orgweave/web lint
  check_cmd "web typecheck" pnpm --filter @orgweave/web typecheck
  check_cmd "web build" pnpm --filter @orgweave/web build
else
  fail "pnpm not found; install pnpm >= 9"
fi

section "7. Temporal workflow smoke test"
if [[ -x .venv/bin/python ]]; then
  check_cmd "PingWorkflow end-to-end" .venv/bin/python scripts/temporal_smoke.py
else
  fail "Temporal smoke (missing .venv)"
fi

printf '\n%s\n' "----------------------------------------"
printf 'Phase 0 verification: \033[32m%s passed\033[0m, \033[31m%s failed\033[0m\n' "$PASS" "$FAIL"
[[ "$FAIL" -eq 0 ]]
