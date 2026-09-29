#!/usr/bin/env bash
#
# Freeze the Python backend into a self-contained executable with PyInstaller,
# so the packaged app runs without any Python installed on the user's machine.
# Output lands in src-tauri/backend-bin/, which Tauri bundles as a resource.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
BACKEND="$ROOT/backend"
OUT="$HERE/backend-bin"
BUILD_VENV="$HERE/.build-venv"

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
  echo "✖ Need Python 3.10+ to build the app (only to build — the finished app won't need it)."
  echo "  Install it with:  brew install python@3.12"
  exit 1
fi

echo "▶ Preparing an isolated build environment…"
[ -d "$BUILD_VENV" ] || "$PYTHON" -m venv "$BUILD_VENV"
# shellcheck disable=SC1091
source "$BUILD_VENV/bin/activate"
pip install --quiet --upgrade pip
pip install --quiet -r "$BACKEND/requirements.txt" pyinstaller

echo "▶ Freezing the backend with PyInstaller (takes a minute or two)…"
cd "$BACKEND"
pyinstaller --clean --noconfirm tanai-backend.spec

echo "▶ Copying the frozen backend into the bundle…"
rm -rf "$OUT"
mkdir -p "$OUT"
cp -R "$BACKEND/dist/tanai-backend/." "$OUT/"
chmod +x "$OUT/tanai-backend"

echo "✅ Frozen backend ready at $OUT/tanai-backend"
