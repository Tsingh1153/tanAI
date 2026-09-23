#!/usr/bin/env bash
#
# Build a double-click macOS launcher (tanAI.app) on your Desktop.
#
# Run this once. After that, double-click "tanAI" on the Desktop to start
# everything and open the app in your browser — no terminal needed.

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

# The launcher script. REPO_DIR is baked in now; everything else stays literal.
cat >"$MACOS_DIR/tanAI" <<LAUNCH
#!/usr/bin/env bash
REPO="$REPO_DIR"
URL="http://localhost:3000"
LOG="\$HOME/Library/Logs/tanAI.log"

# Already running? Just bring it up in the browser.
if curl -s -o /dev/null "\$URL"; then
  open "\$URL"
  exit 0
fi

if [ ! -d "\$REPO" ]; then
  osascript -e 'display dialog "Could not find the tanAI project folder at $REPO_DIR" buttons {"OK"} default button "OK" with icon caution'
  exit 1
fi

# Start the backend + frontend detached, logging to ~/Library/Logs/tanAI.log.
cd "\$REPO"
nohup ./scripts/start.sh >"\$LOG" 2>&1 &
echo \$! >"\$HOME/.tanai.pid"

# Wait up to ~90s for the frontend, then open the browser.
for _ in \$(seq 1 90); do
  curl -s -o /dev/null "\$URL" && break
  sleep 1
done
open "\$URL"
LAUNCH
chmod +x "$MACOS_DIR/tanAI"

echo "✅ Created $APP"
echo "   Double-click tanAI on your Desktop to launch (first start takes ~30–60s)."
echo "   To stop it later:  kill \$(cat ~/.tanai.pid)"
