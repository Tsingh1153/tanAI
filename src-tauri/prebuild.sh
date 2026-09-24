#!/usr/bin/env bash
#
# Runs before `tauri build`. Tauri sets the working directory to src-tauri/.
# Copies the backend source into the bundle (minus dev cruft and user data) and
# builds the static frontend that Tauri will embed.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"

echo "▶ Syncing backend into the bundle…"
rm -rf "$HERE/backend"
mkdir -p "$HERE/backend"
rsync -a \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude '.pytest_cache' \
  --exclude '.ruff_cache' \
  --exclude 'tests' \
  --exclude 'data' \
  --exclude '*.db' \
  --exclude '*.db-journal' \
  --exclude '.env' \
  "$ROOT/backend/" "$HERE/backend/"

echo "▶ Building the static frontend…"
npm --prefix "$ROOT/frontend" run build

echo "✅ Prebuild complete."
