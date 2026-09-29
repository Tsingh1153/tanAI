#!/usr/bin/env bash
#
# Tauri validates the backend-bin resource glob even during `tauri dev`, where
# the backend runs from source (via a virtualenv) instead of the frozen binary.
# Ensure the folder exists with a file so the glob resolves.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$HERE/backend-bin"
[ -e "$HERE/backend-bin/.keep" ] || touch "$HERE/backend-bin/.keep"
