#!/usr/bin/env bash
#
# Build a double-click macOS launcher (tanAI.app) on your Desktop.
#
# Run this once. After that, double-click "tanAI" on the Desktop and tanAI opens
# in its own app window (no browser tabs or address bar) — no terminal needed.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="$HOME/Desktop/tanAI.app"
MACOS_DIR="$APP/Contents/MacOS"

echo "▶ Building $APP"
rm -rf "$APP"
mkdir -p "$MACOS_DIR"

cat >"$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>tanAI</string>
  <key>CFBundleDisplayName</key><string>tanAI</string>
  <key>CFBundleIdentifier</key><string>com.tanai.launcher</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>tanAI</string>
  <key>LSUIElement</key><true/>
</dict>
</plist>
PLIST

# Main executable: hand off to the worker and exit immediately, so macOS never
# sees the app hang (that caused the "tanAI is not responding" error).
cat >"$MACOS_DIR/tanAI" <<'MAIN'
#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
nohup "$DIR/worker.sh" >/dev/null 2>&1 &
exit 0
MAIN
chmod +x "$MACOS_DIR/tanAI"

# Worker: starts the stack (if needed) and opens tanAI in its own app window.
# REPO_DIR is baked in; all runtime variables stay literal.
cat >"$MACOS_DIR/worker.sh" <<WORKER
#!/bin/bash
REPO="$REPO_DIR"
URL="http://localhost:3000"
LOG="\$HOME/Library/Logs/tanAI.log"

# Open tanAI in a standalone, chrome-less window (feels like a native app) using
# whichever Chromium browser is installed; fall back to the default browser.
open_window() {
  local chrome="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
  local edge="/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"
  local brave="/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
  if [ -x "\$chrome" ]; then
    "\$chrome" --app="\$URL" >/dev/null 2>&1 &
  elif [ -x "\$edge" ]; then
    "\$edge" --app="\$URL" >/dev/null 2>&1 &
  elif [ -x "\$brave" ]; then
    "\$brave" --app="\$URL" >/dev/null 2>&1 &
  else
    open "\$URL"
  fi
}

# Already running? Just open the window.
if curl -s -o /dev/null "\$URL"; then
  open_window
  exit 0
fi

if [ ! -d "\$REPO" ]; then
  osascript -e 'display dialog "Could not find the tanAI project folder at $REPO_DIR" buttons {"OK"} default button "OK" with icon caution'
  exit 1
fi

cd "\$REPO"
nohup ./scripts/start.sh >"\$LOG" 2>&1 &
echo \$! >"\$HOME/.tanai.pid"

# Wait up to ~2 min for the frontend to come up, then open the window.
for _ in \$(seq 1 120); do
  curl -s -o /dev/null "\$URL" && break
  sleep 1
done
open_window
WORKER
chmod +x "$MACOS_DIR/worker.sh"

echo "✅ Created $APP"
echo "   Double-click tanAI on your Desktop to launch (first start takes ~30–60s)."
echo "   To stop it later:  kill \$(cat ~/.tanai.pid)"
