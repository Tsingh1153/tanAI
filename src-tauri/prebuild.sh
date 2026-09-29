#!/usr/bin/env bash
#
# Runs before `tauri build`: freeze the backend into a self-contained binary,
# then build the static frontend that Tauri embeds.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"

bash "$HERE/build-backend.sh"

echo "▶ Building the static frontend…"
npm --prefix "$ROOT/frontend" run build

echo "✅ Prebuild complete."
