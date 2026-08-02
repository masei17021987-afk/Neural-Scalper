#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
export PATH="$HOME/.local/bin:$PATH"
"$ROOT/start.sh" --prepare-only

if command -v uv >/dev/null 2>&1; then
  uv pip install --python "$ROOT/.venv/bin/python" -r requirements-dev.txt
else
  if ! "$ROOT/.venv/bin/python" -m pip --version >/dev/null 2>&1; then
    "$ROOT/.venv/bin/python" -m ensurepip --upgrade
  fi
  "$ROOT/.venv/bin/python" -m pip install -r requirements-dev.txt
fi

TEST_VAR="$(mktemp -d)"
cleanup() { rm -rf "$TEST_VAR"; }
trap cleanup EXIT
export NEUROSCALPER_VAR_DIR="$TEST_VAR"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
"$ROOT/.venv/bin/python" -m pytest "$@"
