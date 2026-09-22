#!/bin/bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

echo "🔨 [1/4] Compiling Speed-X Swift UI Sources..."
mkdir -p bin dist
swiftc -O swift_ui/Sources/*.swift -o bin/SpeedX

echo "📦 [2/4] Assembling SpeedX.app Bundle..."
APP_BUNDLE="dist/SpeedX.app"
rm -rf "$APP_BUNDLE"
mkdir -p "$APP_BUNDLE/Contents/MacOS"
mkdir -p "$APP_BUNDLE/Contents/Resources"

cp bin/SpeedX "$APP_BUNDLE/Contents/MacOS/SpeedX"
chmod +x "$APP_BUNDLE/Contents/MacOS/SpeedX"

cat << 'EOF' > "$APP_BUNDLE/Contents/Info.plist"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>SpeedX</string>
    <key>CFBundleIdentifier</key>
    <string>com.festomanolo.speedx</string>
    <key>CFBundleName</key>
    <string>SpeedX</string>
    <key>CFBundleDisplayName</key>
    <string>Speed-X</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0.0</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>LSMinimumSystemVersion</key>
    <string>13.0</string>
    <key>LSUIElement</key>
    <true/>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSSupportsAutomaticGraphicsSwitching</key>
    <true/>
    <key>NSMicrophoneUsageDescription</key>
    <string>Speed-X uses the microphone for offline voice commands.</string>
    <key>NSSpeechRecognitionUsageDescription</key>
    <string>Speed-X uses Speech Recognition to convert spoken English and Swahili commands to text.</string>
</dict>
</plist>
EOF

echo "💿 [3/4] Preparing DMG staging area..."
DMG_STAGING="dist/dmg_staging"
rm -rf "$DMG_STAGING" dist/SpeedX.dmg
mkdir -p "$DMG_STAGING"

cp -R "$APP_BUNDLE" "$DMG_STAGING/"
ln -s /Applications "$DMG_STAGING/Applications"

echo "💿 [4/4] Creating DMG using native hdiutil..."
hdiutil create -volname "Speed-X" -srcfolder "$DMG_STAGING" -ov -format UDZO dist/SpeedX.dmg

rm -rf "$DMG_STAGING"

echo "Build Complete!"
echo "   App: dist/SpeedX.app"
echo "   DMG: dist/SpeedX.dmg"
