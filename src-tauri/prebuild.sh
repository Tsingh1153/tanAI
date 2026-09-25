#!/usr/bin/env bash
#
# Runs before `tauri build`: sync the backend into the bundle, then build the
# static frontend that Tauri will embed.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"

bash "$HERE/sync-backend.sh"

echo "▶ Building the static frontend…"
npm --prefix "$ROOT/frontend" run build

echo "✅ Prebuild complete."
