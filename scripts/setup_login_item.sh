#!/bin/bash
# Speed-X Launch Agent Configurator
set -e

PLIST_DIR="$HOME/Library/LaunchAgents"
PLIST_PATH="$PLIST_DIR/com.festomanolo.speedx.plist"
APP_PATH="/Applications/SpeedX.app/Contents/MacOS/SpeedX"

if [ ! -f "$APP_PATH" ]; then
    # Fallback to local build if not installed in /Applications
    DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    APP_PATH="$DIR/dist/SpeedX.app/Contents/MacOS/SpeedX"
fi

ACTION="${1:-enable}"

mkdir -p "$PLIST_DIR"

if [ "$ACTION" == "disable" ]; then
    echo "Disabling Speed-X Launch Agent..."
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
    rm -f "$PLIST_PATH"
    echo "[OK] Speed-X login item removed."
    exit 0
fi

echo "Installing Speed-X Launch Agent at $PLIST_PATH..."
cat << EOF > "$PLIST_PATH"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.festomanolo.speedx</string>
    <key>ProgramArguments</key>
    <array>
        <string>$APP_PATH</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>ProcessType</key>
    <string>Interactive</string>
</dict>
</plist>
EOF

launchctl unload "$PLIST_PATH" 2>/dev/null || true
launchctl load "$PLIST_PATH"
echo "[OK] Speed-X is configured to launch automatically at login."
