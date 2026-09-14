#!/usr/bin/env bash
#
# LocalMind one-command launcher (macOS / Linux).
#
# Boots the FastAPI backend and the Next.js frontend together, installing
# dependencies on first run. Ctrl-C stops both cleanly.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

BACKEND_HOST="${LOCALMIND_HOST:-127.0.0.1}"
BACKEND_PORT="${LOCALMIND_PORT:-8000}"

echo "▶ tanAI starting from $ROOT_DIR"

# --- Prerequisite checks -------------------------------------------------- #
# Find a Python interpreter that is at least 3.10 (the app uses 3.10+ syntax).
pick_python() {
  for candidate in python3.12 python3.11 python3.10 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
        echo "$candidate"
        return 0
      fi
    fi
  done
  return 1
}

PYTHON="$(pick_python || true)"
if [ -z "${PYTHON:-}" ]; then
  echo "✖ No Python 3.10+ found. Install one with:  brew install python@3.12"
  echo "  Then re-run this script."
  exit 1
fi
echo "▶ Using Python: $($PYTHON --version) ($PYTHON)"

if ! command -v npm >/dev/null 2>&1; then
  echo "✖ Node.js/npm not found. Install it with:  brew install node"
  echo "  Then re-run this script."
  exit 1
fi

# --- Apple Foundation Models (macOS 27+) ---------------------------------- #
# If the `fm` CLI exists, expose Apple's on-device LLM as an OpenAI-compatible
# API so it can be added as a provider in Settings.
FM_PORT="${FM_PORT:-1976}"
FM_PID=""
if command -v fm >/dev/null 2>&1; then
  echo "▶ Starting Apple Foundation Models API on port $FM_PORT"
  fm serve --port "$FM_PORT" >/dev/null 2>&1 &
  FM_PID=$!
fi

# --- Backend -------------------------------------------------------------- #
cd "$BACKEND_DIR"

# Recreate the venv if it is missing or was built with an incompatible Python.
venv_ok=false
if [ -d ".venv" ]; then
  if .venv/bin/python -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
    venv_ok=true
  else
    echo "▶ Existing virtual environment uses an old Python; recreating…"
    rm -rf .venv
  fi
fi
if [ "$venv_ok" = false ]; then
  echo "▶ Creating Python virtual environment…"
  "$PYTHON" -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate
echo "▶ Installing backend dependencies…"
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

echo "▶ Launching backend on http://$BACKEND_HOST:$BACKEND_PORT"
uvicorn app.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" &
BACKEND_PID=$!

# --- Frontend ------------------------------------------------------------- #
cd "$FRONTEND_DIR"
# Always run install (fast no-op when up to date) so newly added dependencies
# are picked up across updates without a manual step.
echo "▶ Installing frontend dependencies…"
npm install --no-audit --no-fund
if [ ! -f ".env.local" ]; then
  cp .env.local.example .env.local
fi

echo "▶ Launching frontend on http://localhost:3000"
npm run dev &
FRONTEND_PID=$!

# --- Cleanup -------------------------------------------------------------- #
cleanup() {
  echo ""
  echo "▶ Shutting down…"
  kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
  [ -n "$FM_PID" ] && kill "$FM_PID" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup INT TERM

echo ""
echo "✅ tanAI is running:"
echo "   • UI:      http://localhost:3000"
echo "   • API:     http://$BACKEND_HOST:$BACKEND_PORT/docs"
echo "   Press Ctrl-C to stop."
wait
