#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_ROOT="$ROOT/macos/AcademicHarnessApp"
DIST="$ROOT/dist"
APP="$DIST/AcademicHarness.app"
EXECUTABLE="$APP/Contents/MacOS/AcademicHarnessApp"

mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
swift build -c release --package-path "$APP_ROOT"
cp "$APP_ROOT/.build/release/AcademicHarnessApp" "$EXECUTABLE"
chmod +x "$EXECUTABLE"
cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key>
  <string>AcademicHarnessApp</string>
  <key>CFBundleIdentifier</key>
  <string>com.mappedinfo.academic-harness</string>
  <key>CFBundleName</key>
  <string>Academic Harness</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>0.1.0</string>
  <key>LSMinimumSystemVersion</key>
  <string>13.0</string>
</dict>
</plist>
PLIST

echo "$APP"
