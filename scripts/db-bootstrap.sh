#!/usr/bin/env bash
# Idempotently create the non-superuser application role on an existing volume.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  set -a; source .env; set +a
fi

DC="${DC:-docker compose}"
if ! $DC ps postgres 2>/dev/null | grep -q "Up"; then
  echo "ERROR: postgres container is not running; start 'make infra' first" >&2
  exit 1
fi

$DC exec -T postgres psql -v ON_ERROR_STOP=1 \
  -U "${POSTGRES_USER:-orgweave}" \
  -d "${POSTGRES_DB:-orgweave}" < infra/postgres/init/02-app-role.sql

echo "database roles ready"
