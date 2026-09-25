#!/usr/bin/env bash
#
# Copy the backend source into src-tauri/backend so Tauri can bundle it as a
# resource. Runs before both `tauri dev` and `tauri build` (the resource glob is
# validated in both). Excludes dev cruft and anything user-specific.

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
