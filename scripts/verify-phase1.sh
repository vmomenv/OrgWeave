#!/usr/bin/env bash
# Phase 1 acceptance: auth, tenant, org, RBAC/RLS boundary, audit, web.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then set -a; source .env; set +a; fi
API="http://localhost:${API_PORT:-8000}"
WEB="http://localhost:3000"
SUFFIX="$(date +%s)-$RANDOM"
PASS=0
FAIL=0
pass() { printf '  \033[32mPASS\033[0m %s\n' "$1"; PASS=$((PASS + 1)); }
fail() { printf '  \033[31mFAIL\033[0m %s\n' "$1"; FAIL=$((FAIL + 1)); }
json() { python3 -c "import sys,json; d=json.load(sys.stdin); print(d$1)"; }

section() { printf '\n\033[1m%s\033[0m\n' "$1"; }

section "1. Phase 1 API availability"
if curl -fsS -m 10 "$API/api/v1/meta" | grep -q '"phase"'; then
  pass "API metadata"
else
  fail "API metadata"
fi

section "2. Register and authenticate"
EMAIL="verify-$SUFFIX@example.com"
REGISTER="$(curl -sS -m 15 -H 'content-type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"correct-horse-battery\",\"display_name\":\"验收用户\"}" \
  -w '\n%{http_code}' "$API/api/v1/auth/register")"
REG_BODY="${REGISTER%$'\n'*}"
REG_CODE="${REGISTER##*$'\n'}"
if [[ "$REG_CODE" == "201" ]]; then pass "register user"; else fail "register user ($REG_CODE)"; echo "$REG_BODY"; fi
TOKEN="$(printf '%s' "$REG_BODY" | json "['access_token']")"
USER_ID="$(printf '%s' "$REG_BODY" | json "['user']['id']")"

ME_CODE="$(curl -sS -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $TOKEN" "$API/api/v1/auth/me")"
[[ "$ME_CODE" == "200" ]] && pass "/auth/me" || fail "/auth/me ($ME_CODE)"

section "3. Tenant and current context"
TENANT_BODY="$(curl -sS -m 15 -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d "{\"name\":\"验收企业-$SUFFIX\"}" "$API/api/v1/tenants")"
TENANT_ID="$(printf '%s' "$TENANT_BODY" | json "['id']")"
if [[ -n "$TENANT_ID" ]]; then pass "create tenant"; else fail "create tenant"; fi

CONTEXT="$(curl -sS -m 15 -H "Authorization: Bearer $TOKEN" -H "X-Tenant-ID: $TENANT_ID" "$API/api/v1/tenant")"
ROLES="$(printf '%s' "$CONTEXT" | json "['role_keys']")"
if [[ "$ROLES" == "['owner']" ]]; then pass "owner role seeded"; else fail "owner role seeded ($ROLES)"; fi

section "4. Organization operations"
DEPT_BODY="$(curl -sS -m 15 -H "Authorization: Bearer $TOKEN" -H "X-Tenant-ID: $TENANT_ID" \
  -H 'content-type: application/json' -d '{"name":"研发部"}' "$API/api/v1/departments")"
DEPT_ID="$(printf '%s' "$DEPT_BODY" | json "['id']" 2>/dev/null || true)"
if [[ -n "$DEPT_ID" ]]; then pass "create department"; else fail "create department"; echo "$DEPT_BODY"; fi

AI_BODY="$(curl -sS -m 15 -H "Authorization: Bearer $TOKEN" -H "X-Tenant-ID: $TENANT_ID" \
  -H 'content-type: application/json' \
  -d "{\"member_type\":\"ai\",\"display_name\":\"AI CTO\",\"title\":\"CTO\",\"department_id\":\"$DEPT_ID\",\"role_keys\":[\"admin\"]}" \
  "$API/api/v1/members")"
AI_ROLE="$(printf '%s' "$AI_BODY" | json "['roles'][0]['key']" 2>/dev/null || true)"
if [[ "$AI_ROLE" == "admin" ]]; then pass "create AI member with role"; else fail "create AI member"; echo "$AI_BODY"; fi

INVITE_EMAIL="invitee-$SUFFIX@example.com"
INVITE_BODY="$(curl -sS -m 15 -H "Authorization: Bearer $TOKEN" -H "X-Tenant-ID: $TENANT_ID" \
  -H 'content-type: application/json' -d "{\"email\":\"$INVITE_EMAIL\",\"role_key\":\"member\"}" \
  "$API/api/v1/invitations")"
INVITE_TOKEN="$(printf '%s' "$INVITE_BODY" | json "['token']" 2>/dev/null || true)"
if [[ -n "$INVITE_TOKEN" ]]; then pass "create invitation"; else fail "create invitation"; echo "$INVITE_BODY"; fi

INVITEE_BODY="$(curl -sS -m 15 -H 'content-type: application/json' \
  -d "{\"email\":\"$INVITE_EMAIL\",\"password\":\"correct-horse-battery\",\"display_name\":\"受邀成员\"}" \
  "$API/api/v1/auth/register")"
INVITEE_TOKEN="$(printf '%s' "$INVITEE_BODY" | json "['access_token']" 2>/dev/null || true)"
ACCEPT_BODY="$(curl -sS -m 15 -H "Authorization: Bearer $INVITEE_TOKEN" \
  -H 'content-type: application/json' -d "{\"token\":\"$INVITE_TOKEN\"}" \
  "$API/api/v1/invitations/accept")"
ACCEPTED_TENANT="$(printf '%s' "$ACCEPT_BODY" | json "['tenant_id']" 2>/dev/null || true)"
if [[ "$ACCEPTED_TENANT" == "$TENANT_ID" ]]; then pass "invitation accepted"; else fail "invitation accepted"; echo "$ACCEPT_BODY"; fi

section "5. Tenant isolation boundary"
OUTSIDER_BODY="$(curl -sS -m 15 -H 'content-type: application/json' \
  -d "{\"email\":\"outsider-$SUFFIX@example.com\",\"password\":\"correct-horse-battery\",\"display_name\":\"外部用户\"}" \
  "$API/api/v1/auth/register")"
OUTSIDER_TOKEN="$(printf '%s' "$OUTSIDER_BODY" | json "['access_token']" 2>/dev/null || true)"
FOREIGN_CODE="$(curl -sS -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $OUTSIDER_TOKEN" \
  -H "X-Tenant-ID: $TENANT_ID" "$API/api/v1/members")"
[[ "$FOREIGN_CODE" == "403" ]] && pass "foreign tenant rejected" || fail "foreign tenant rejected ($FOREIGN_CODE)"

section "6. Audit"
AUDIT_BODY="$(curl -sS -m 15 -H "Authorization: Bearer $TOKEN" -H "X-Tenant-ID: $TENANT_ID" "$API/api/v1/audit")"
if printf '%s' "$AUDIT_BODY" | grep -q 'department.created'; then pass "audit events"; else fail "audit events"; fi

section "7. Web application"
LOGIN_CODE="$(curl -sS -o /dev/null -w '%{http_code}' "$WEB/login")"
[[ "$LOGIN_CODE" == "200" ]] && pass "login page" || fail "login page ($LOGIN_CODE)"
WORKSPACE_CODE="$(curl -sS -o /dev/null -w '%{http_code}' "$WEB/workspace")"
[[ "$WORKSPACE_CODE" == "200" ]] && pass "workspace page" || fail "workspace page ($WORKSPACE_CODE)"

printf '\n%s\n' "----------------------------------------"
printf 'Phase 1 verification: \033[32m%s passed\033[0m, \033[31m%s failed\033[0m\n' "$PASS" "$FAIL"
[[ "$FAIL" -eq 0 ]]
