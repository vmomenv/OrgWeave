#!/usr/bin/env bash
# Phase 2 acceptance: groups, messages, mentions, attachments, realtime, web.
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
jsonlen() { python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d))"; }
section() { printf '\n\033[1m%s\033[0m\n' "$1"; }

section "1. Setup"
REG=$(curl -sS -H 'content-type: application/json' \
  -d "{\"email\":\"chat-verify-$SUFFIX@example.com\",\"password\":\"correct-horse-battery\",\"display_name\":\"聊天验收\"}" \
  "$API/api/v1/auth/register")
TOKEN=$(printf '%s' "$REG" | json "['access_token']")
TENANT=$(curl -sS -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d "{\"name\":\"聊天验收-$SUFFIX\"}" "$API/api/v1/tenants" | json "['id']")
[[ -n "$TENANT" ]] && pass "tenant ready" || fail "tenant ready"

AI=$(curl -sS -H "Authorization: Bearer $TOKEN" -H "X-Tenant-ID: $TENANT" -H 'content-type: application/json' \
  -d '{"member_type":"ai","display_name":"AI CTO","role_keys":["admin"]}' \
  "$API/api/v1/members" | json "['id']")
[[ -n "$AI" ]] && pass "AI member created" || fail "AI member created"

section "2. Groups"
GROUP_BODY=$(curl -sS -H "Authorization: Bearer $TOKEN" -H "X-Tenant-ID: $TENANT" -H 'content-type: application/json' \
  -d "{\"name\":\"验收群\",\"member_ids\":[\"$AI\"]}" "$API/api/v1/groups")
GROUP=$(printf '%s' "$GROUP_BODY" | json "['id']")
MEMBER_COUNT=$(printf '%s' "$GROUP_BODY" | python3 -c "import sys,json; print(len(json.load(sys.stdin)['members']))")
[[ "$MEMBER_COUNT" == "2" ]] && pass "group created with 2 members" || fail "group created ($GROUP_BODY)"

section "3. Messages and mentions"
MSG=$(curl -sS -H "Authorization: Bearer $TOKEN" -H "X-Tenant-ID: $TENANT" -H 'content-type: application/json' \
  -d '{"content":"请 @AI CTO 输出执行计划"}' "$API/api/v1/groups/$GROUP/messages")
MENTION=$(printf '%s' "$MSG" | json "['mentions'][0]['member_type']" 2>/dev/null || true)
[[ "$MENTION" == "ai" ]] && pass "AI mention recorded" || fail "AI mention recorded ($MSG)"
HISTORY_COUNT=$(curl -sS -H "Authorization: Bearer $TOKEN" -H "X-Tenant-ID: $TENANT" \
  "$API/api/v1/groups/$GROUP/messages" | jsonlen)
[[ "$HISTORY_COUNT" == "1" ]] && pass "message history" || fail "message history ($HISTORY_COUNT)"

section "4. Attachments"
echo "phase2 attachment" > /tmp/opencode/phase2-note.txt
ATT=$(curl -sS -H "Authorization: Bearer $TOKEN" -H "X-Tenant-ID: $TENANT" \
  -F 'file=@/tmp/opencode/phase2-note.txt;type=text/plain' \
  "$API/api/v1/groups/$GROUP/attachments" | json "['id']")
[[ -n "$ATT" ]] && pass "attachment uploaded" || fail "attachment uploaded"
DOWNLOAD=$(curl -sS -H "Authorization: Bearer $TOKEN" -H "X-Tenant-ID: $TENANT" \
  "$API/api/v1/attachments/$ATT")
[[ "$DOWNLOAD" == "phase2 attachment" ]] && pass "attachment download" || fail "attachment download"

section "5. Tenant isolation"
OUT=$(curl -sS -H 'content-type: application/json' \
  -d "{\"email\":\"chat-outsider-$SUFFIX@example.com\",\"password\":\"correct-horse-battery\",\"display_name\":\"外部\"}" \
  "$API/api/v1/auth/register")
OUT_TOKEN=$(printf '%s' "$OUT" | json "['access_token']")
OUT_CODE=$(curl -sS -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $OUT_TOKEN" \
  -H "X-Tenant-ID: $TENANT" "$API/api/v1/groups/$GROUP/messages")
[[ "$OUT_CODE" == "403" ]] && pass "foreign tenant rejected" || fail "foreign tenant rejected ($OUT_CODE)"

section "6. Web"
WS_CODE=$(curl -sS -o /dev/null -w '%{http_code}' "$WEB/workspace")
[[ "$WS_CODE" == "200" ]] && pass "workspace page" || fail "workspace page ($WS_CODE)"

printf '\n%s\n' "----------------------------------------"
printf 'Phase 2 verification: \033[32m%s passed\033[0m, \033[31m%s failed\033[0m\n' "$PASS" "$FAIL"
[[ "$FAIL" -eq 0 ]]
