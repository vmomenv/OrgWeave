#!/usr/bin/env bash
# Bootstrap a local OrgWeave development environment.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

fail() { echo "ERROR: $*" >&2; exit 1; }
info() { echo "[bootstrap] $*"; }

command -v python3 >/dev/null || fail "python3 is required (>=3.11)"
PY_VERSION="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
info "Python $PY_VERSION"

if [[ ! -f .env ]]; then
  cp .env.example .env
  info "Created .env from .env.example"
fi
# shellcheck disable=SC1091
set -a; source .env; set +a

if ! command -v pnpm >/dev/null; then
  if command -v corepack >/dev/null; then
    info "pnpm not found; trying corepack"
    corepack enable >/dev/null 2>&1 || true
  fi
fi
command -v pnpm >/dev/null || fail "pnpm >=9 is required (https://pnpm.io/installation)"

if ! command -v docker >/dev/null; then
  fail "docker is required; see https://docs.docker.com/engine/install/"
fi
if ! docker info >/dev/null 2>&1; then
  fail "Cannot reach the Docker daemon. Ensure it is running and your user can access it (e.g. 'newgrp docker')."
fi
docker compose version >/dev/null 2>&1 || fail "docker compose v2 plugin is required"

info "Installing dependencies"
make install

info "Starting infrastructure"
make infra

info "Waiting for PostgreSQL and Redis"
for _ in $(seq 1 60); do
  if docker compose exec -T postgres pg_isready -U "${POSTGRES_USER:-orgweave}" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

info "Ensuring application database role"
bash scripts/db-bootstrap.sh

info "Applying database migrations"
make migrate

info "Bootstrap complete. Run 'make api', 'make web', and 'make workers'."
