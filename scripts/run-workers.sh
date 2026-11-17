#!/usr/bin/env bash
# Start all four workers natively for local development.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

LOG_DIR="$ROOT/.data/logs"
PID_DIR="$ROOT/.data/pids"
mkdir -p "$LOG_DIR" "$PID_DIR"

PY="$ROOT/.venv/bin/python"
[[ -x "$PY" ]] || { echo "ERROR: run 'make install' first" >&2; exit 1; }

start() {
  local name="$1" module="$2"
  local pid_file="$PID_DIR/$name.pid"
  if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
    echo "[$name] already running (pid $(cat "$pid_file"))"
    return
  fi
  WORKER_NAME="$name" nohup "$PY" -m "$module" >"$LOG_DIR/$name.log" 2>&1 &
  echo $! >"$pid_file"
  echo "[$name] started (pid $!) -> $LOG_DIR/$name.log"
}

start agent-worker orgweave_agent_worker
start temporal-worker orgweave_temporal_worker
start skill-runner orgweave_skill_runner
start watchdog-worker orgweave_watchdog_worker
