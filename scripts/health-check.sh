#!/usr/bin/env bash
# Verify every Phase 0 service's health endpoint. Reports all failures.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  # shellcheck disable=SC1091
  set -a; source .env; set +a
fi

API_BASE="${API_PUBLIC_URL:-http://localhost:${API_PORT:-8000}}"
WEB_BASE="${WEB_PUBLIC_URL:-http://localhost:3000}"
LITELLM_BASE="${LITELLM_BASE_URL:-http://localhost:4000}"
MINIO_BASE="http://localhost:9000"
TEMPORAL_UI="http://localhost:8080"

PASS=0
FAIL=0

check() {
  local name="$1" url="$2" expected="${3:-200}"
  local code
  code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 10 "$url" 2>/dev/null || echo 000)"
  if [[ "$code" == "$expected" ]]; then
    printf '  \033[32mPASS\033[0m %-22s %s (%s)\n' "$name" "$url" "$code"
    PASS=$((PASS + 1))
  else
    printf '  \033[31mFAIL\033[0m %-22s %s (got %s, expected %s)\n' "$name" "$url" "$code" "$expected"
    FAIL=$((FAIL + 1))
  fi
}

echo "OrgWeave Phase 0 health checks"
check "API liveness" "$API_BASE/api/v1/health/live"
check "API readiness" "$API_BASE/api/v1/health/ready"
check "Web" "$WEB_BASE"
check "LiteLLM liveness" "$LITELLM_BASE/health/liveliness"
check "MinIO liveness" "$MINIO_BASE/minio/health/live"
check "Temporal UI" "$TEMPORAL_UI"

echo
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  echo "Container status:"
  docker compose ps --format 'table {{.Name}}\t{{.Service}}\t{{.Status}}' || true
fi

echo
echo "Passed: $PASS  Failed: $FAIL"
[[ "$FAIL" -eq 0 ]]
