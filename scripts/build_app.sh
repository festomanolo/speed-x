#!/bin/bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

echo "🔨 [1/4] Compiling Speed-X Swift UI Sources..."
mkdir -p bin dist
swiftc -O -target "$(uname -m)-apple-macos26.0" swift_ui/Sources/*.swift -o bin/SpeedX

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
    <string>26.0</string>
    <key>CFBundleURLTypes</key>
    <array>
        <dict>
            <key>CFBundleURLName</key>
            <string>com.festomanolo.speedx</string>
            <key>CFBundleURLSchemes</key>
            <array>
                <string>speedx</string>
            </array>
        </dict>
    </array>
    <key>SpeedXProjectRoot</key>
    <string>__PROJECT_ROOT__</string>
    <key>LSUIElement</key>
    <true/>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSSupportsAutomaticGraphicsSwitching</key>
    <true/>
    <key>NSMicrophoneUsageDescription</key>
    <string>Speed-X uses the microphone for offline voice commands.</string>
    <key>NSAppleEventsUsageDescription</key>
    <string>Speed-X controls apps like Music, Notes, Mail and Reminders when you ask it to.</string>
    <key>NSSpeechRecognitionUsageDescription</key>
    <string>Speed-X uses Speech Recognition to convert spoken English and Swahili commands to text.</string>
</dict>
</plist>
EOF
sed -i '' "s#__PROJECT_ROOT__#$DIR#" "$APP_BUNDLE/Contents/Info.plist"

# Ad-hoc signature with an identifier-based designated requirement. macOS only shows the
# microphone / speech / automation prompts for a signed bundle, and pinning the requirement
# to the bundle id (instead of the default per-build code hash) means granted permissions
# survive rebuilds.
codesign --force --deep --sign - \
    --requirements '=designated => identifier "com.festomanolo.speedx"' \
    "$APP_BUNDLE"

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
