#!/usr/bin/env bash
#
# tanAI production launcher (macOS / Linux).
#
# Builds the frontend once and serves the optimized production build, and runs
# the backend without auto-reload. Slower to start than ./scripts/start.sh, but
# faster and lighter at runtime — use this for daily driving.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

BACKEND_HOST="${LOCALMIND_HOST:-127.0.0.1}"
BACKEND_PORT="${LOCALMIND_PORT:-8000}"

echo "▶ tanAI (production) starting from $ROOT_DIR"

# --- Prerequisites (reuse the same detection as the dev launcher) --------- #
pick_python() {
  for candidate in python3.12 python3.11 python3.10 python3; do
    if command -v "$candidate" >/dev/null 2>&1 &&
      "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}
PYTHON="$(pick_python || true)"
if [ -z "${PYTHON:-}" ]; then
  echo "✖ No Python 3.10+ found. Install with: brew install python@3.12"
  exit 1
fi
if ! command -v npm >/dev/null 2>&1; then
  echo "✖ Node.js/npm not found. Install with: brew install node"
  exit 1
fi

# Apple Foundation Models (macOS 27+): expose the on-device LLM over an
# OpenAI-compatible API when the `fm` CLI is available.
FM_PORT="${FM_PORT:-1976}"
FM_PID=""
if command -v fm >/dev/null 2>&1; then
  echo "▶ Starting Apple Foundation Models API on port $FM_PORT"
  fm serve --port "$FM_PORT" >/dev/null 2>&1 &
  FM_PID=$!
fi

# --- Backend -------------------------------------------------------------- #
cd "$BACKEND_DIR"
if [ ! -d ".venv" ] ||
  ! .venv/bin/python -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
  rm -rf .venv
  "$PYTHON" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

echo "▶ Launching backend (production) on http://$BACKEND_HOST:$BACKEND_PORT"
uvicorn app.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" --workers 1 &
BACKEND_PID=$!

# --- Frontend (build + serve) --------------------------------------------- #
cd "$FRONTEND_DIR"
echo "▶ Installing frontend dependencies…"
npm install --no-audit --no-fund
if [ ! -f ".env.local" ]; then
  cp .env.local.example .env.local
fi
echo "▶ Building optimized production bundle (this can take a minute)…"
npm run build
echo "▶ Serving production build on http://localhost:3000"
npm run start &
FRONTEND_PID=$!

cleanup() {
  echo ""
  echo "▶ Shutting down…"
  kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
  [ -n "$FM_PID" ] && kill "$FM_PID" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup INT TERM

echo ""
echo "✅ tanAI (production) is running:"
echo "   • UI:  http://localhost:3000"
echo "   • API: http://$BACKEND_HOST:$BACKEND_PORT/docs"
echo "   Press Ctrl-C to stop."
wait
