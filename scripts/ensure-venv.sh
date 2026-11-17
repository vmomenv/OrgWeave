#!/usr/bin/env bash
# Create a usable Python virtualenv even on systems without ensurepip.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python3}"
VENV="${VENV:-.venv}"

if [[ -x "$VENV/bin/python" ]]; then
  echo "[venv] reusing $VENV ($("$VENV/bin/python" --version))"
  exit 0
fi

command -v "$PYTHON" >/dev/null 2>&1 || {
  echo "ERROR: $PYTHON not found" >&2
  exit 1
}

rm -rf "$VENV"

if "$PYTHON" -m venv "$VENV" >/dev/null 2>&1; then
  echo "[venv] created $VENV with $PYTHON -m venv"
  exit 0
fi

echo "[venv] ensurepip unavailable; trying virtualenv fallback" >&2
rm -rf "$VENV"

if "$PYTHON" -m virtualenv -q -p "$PYTHON" "$VENV" >/dev/null 2>&1; then
  echo "[venv] created $VENV with python -m virtualenv"
  exit 0
fi

if command -v virtualenv >/dev/null 2>&1 && virtualenv -q -p "$PYTHON" "$VENV" >/dev/null 2>&1; then
  echo "[venv] created $VENV with virtualenv"
  exit 0
fi

echo "ERROR: cannot create a Python virtualenv." >&2
echo "Install the venv package, for example:" >&2
echo "  sudo apt install python$(python3 -c 'import sys; print(f\"{sys.version_info.major}.{sys.version_info.minor}\")')-venv" >&2
echo "or install virtualenv: pip install --user virtualenv" >&2
exit 1
