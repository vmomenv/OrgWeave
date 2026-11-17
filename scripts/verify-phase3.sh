#!/usr/bin/env bash
# Phase 3 acceptance: agent config, sessions, queued runs, cancel, web.
# Set ORGWEAVE_MODEL_E2E=1 to additionally wait for a real model-backed run.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ -f .env ]]; then set -a; source .env; set +a; fi
API="http://localhost:${API_PORT:-8000}"
WEB="http://localhost:3000"
SUFFIX="$(date +%s)-$RANDOM"
PASS=0; FAIL=0
pass() { printf '  \033[32mPASS\033[0m %s\n' "$1"; PASS=$((PASS + 1)); }
fail() { printf '  \033[31mFAIL\033[0m %s\n' "$1"; FAIL=$((FAIL + 1)); }
json() { python3 -c "import sys,json; d=json.load(sys.stdin); print(d$1)"; }
section() { printf '\n\033[1m%s\033[0m\n' "$1"; }

section "1. Setup"
REG=$(curl -sS -H 'content-type: application/json' \
  -d "{\"email\":\"agent-verify-$SUFFIX@example.com\",\"password\":\"correct-horse-battery\",\"display_name\":\"Agent 验收\"}" \
  "$API/api/v1/auth/register")
TOKEN=$(printf '%s' "$REG" | json "['access_token']")
TENANT=$(curl -sS -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d "{\"name\":\"Agent 验收-$SUFFIX\"}" "$API/api/v1/tenants" | json "['id']")
AI=$(curl -sS -H "Authorization: Bearer $TOKEN" -H "X-Tenant-ID: $TENANT" -H 'content-type: application/json' \
  -d '{"member_type":"ai","display_name":"CTO-AI","title":"CTO","role_keys":["admin"]}' \
  "$API/api/v1/members" | json "['id']")
[[ -n "$AI" ]] && pass "AI member created" || fail "AI member created"

section "2. Agent configuration"
AGENT_BODY=$(curl -sS -H "Authorization: Bearer $TOKEN" -H "X-Tenant-ID: $TENANT" "$API/api/v1/agents")
AGENT=$(printf '%s' "$AGENT_BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d[0]['id'])")
ALLOWED=$(printf '%s' "$AGENT_BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(','.join(d[0]['allowed_tools']))")
[[ "$ALLOWED" == *"get_current_time"* ]] && pass "auto config with tools" || fail "auto config with tools ($ALLOWED)"
STEPS=$(printf '%s' "$AGENT_BODY" | json "[0]['max_steps']")
[[ "$STEPS" == "8" ]] && pass "default execution limit" || fail "default execution limit ($STEPS)"

section "3. Independent session"
SESSION_BODY=$(curl -sS -H "Authorization: Bearer $TOKEN" -H "X-Tenant-ID: $TENANT" -H 'content-type: application/json' \
  -d '{"title":"验收会话"}' "$API/api/v1/agents/$AGENT/sessions")
SESSION=$(printf '%s' "$SESSION_BODY" | json "['id']")
[[ -n "$SESSION" ]] && pass "session created" || fail "session created ($SESSION_BODY)"

section "4. Run queue and cancel"
RUN_BODY=$(curl -sS -H "Authorization: Bearer $TOKEN" -H "X-Tenant-ID: $TENANT" -H 'content-type: application/json' \
  -d '{"input":"输出一份实施计划"}' "$API/api/v1/sessions/$SESSION/runs")
RUN=$(printf '%s' "$RUN_BODY" | json "['id']")
RUN_STATUS=$(printf '%s' "$RUN_BODY" | json "['status']")
[[ "$RUN_STATUS" == "queued" ]] && pass "run queued" || fail "run queued ($RUN_BODY)"
CANCEL_BODY=$(curl -sS -H "Authorization: Bearer $TOKEN" -H "X-Tenant-ID: $TENANT" -X POST \
  "$API/api/v1/runs/$RUN/cancel")
CANCEL_STATUS=$(printf '%s' "$CANCEL_BODY" | json "['status']")
[[ "$CANCEL_STATUS" == "cancelled" ]] && pass "run cancelled" || fail "run cancelled ($CANCEL_BODY)"
MESSAGES=$(curl -sS -H "Authorization: Bearer $TOKEN" -H "X-Tenant-ID: $TENANT" \
  "$API/api/v1/sessions/$SESSION/messages" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))")
[[ "$MESSAGES" == "0" ]] && pass "cancelled run did not execute" || fail "cancelled run executed ($MESSAGES)"

section "5. Web"
CODE=$(curl -sS -o /dev/null -w '%{http_code}' "$WEB/workspace")
[[ "$CODE" == "200" ]] && pass "workspace page" || fail "workspace page ($CODE)"

if [[ "${ORGWEAVE_MODEL_E2E:-0}" == "1" ]]; then
  section "6. Real model end-to-end"
  E2E=$(curl -sS -H "Authorization: Bearer $TOKEN" -H "X-Tenant-ID: $TENANT" -H 'content-type: application/json' \
    -d '{"input":"请调用工具获取当前时间，然后用一句话回答。"}' \
    "$API/api/v1/sessions/$SESSION/runs")
  E2E_RUN=$(printf '%s' "$E2E" | json "['id']")
  E2E_STATUS="queued"
  for _ in $(seq 1 120); do
    E2E_BODY=$(curl -sS -H "Authorization: Bearer $TOKEN" -H "X-Tenant-ID: $TENANT" \
      "$API/api/v1/runs/$E2E_RUN")
    E2E_STATUS=$(printf '%s' "$E2E_BODY" | json "['status']")
    [[ "$E2E_STATUS" != "queued" && "$E2E_STATUS" != "running" ]] && break
    sleep 2
  done
  if [[ "$E2E_STATUS" == "completed" ]]; then
    pass "real model run completed"
    printf '    输出: %s\n' "$(printf '%s' "$E2E_BODY" | json "['output']")"
    printf '    steps=%s tools=%s tokens=%s\n' \
      "$(printf '%s' "$E2E_BODY" | json "['steps']")" \
      "$(printf '%s' "$E2E_BODY" | json "['tool_calls_count']")" \
      "$(printf '%s' "$E2E_BODY" | json "['token_usage']")"
  else
    fail "real model run completed (status=$E2E_STATUS: $(printf '%s' "$E2E_BODY" | json "['error']"))"
  fi
fi

printf '\n%s\n' "----------------------------------------"
printf 'Phase 3 verification: \033[32m%s passed\033[0m, \033[31m%s failed\033[0m\n' "$PASS" "$FAIL"
[[ "$FAIL" -eq 0 ]]
