#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_ROOT="$ROOT/macos/AcademicHarnessApp"
DIST="$ROOT/dist"
APP="$DIST/AcademicHarness.app"
TMP_APP="$DIST/.tmp/AcademicHarness.app"
CLANG_MODULE_CACHE_PATH="${CLANG_MODULE_CACHE_PATH:-/tmp/academicharness-clang-cache}"

rm -rf "$DIST/.tmp" "$APP"
mkdir -p "$TMP_APP/Contents/MacOS" "$TMP_APP/Contents/Resources/bin" "$TMP_APP/Contents/Resources/python"

export CLANG_MODULE_CACHE_PATH

swift build -c release --package-path "$APP_ROOT"
cp "$APP_ROOT/.build/release/AcademicHarnessApp" "$TMP_APP/Contents/MacOS/AcademicHarnessApp"
chmod +x "$TMP_APP/Contents/MacOS/AcademicHarnessApp"
python3 "$ROOT/scripts/generate-app-icon.py" "$TMP_APP/Contents/Resources/AcademicHarness.icns"
while IFS= read -r source_file; do
  relative_path="${source_file#"$ROOT/src/"}"
  target_file="$TMP_APP/Contents/Resources/python/$relative_path"
  mkdir -p "$(dirname "$target_file")"
  cp "$source_file" "$target_file"
done < <(find "$ROOT/src/academic_harness" -type f -name '*.py' | sort)
cat > "$TMP_APP/Contents/Resources/bin/academic-harness" <<'SH'
#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$APP_ROOT/python${PYTHONPATH:+:$PYTHONPATH}"
exec /usr/bin/python3 -m academic_harness "$@"
SH
chmod +x "$TMP_APP/Contents/Resources/bin/academic-harness"
cat > "$TMP_APP/Contents/Info.plist" <<'PLIST'
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
  <key>CFBundleIconFile</key>
  <string>AcademicHarness.icns</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleVersion</key>
  <string>1</string>
  <key>CFBundleShortVersionString</key>
  <string>0.2.0</string>
  <key>NSPrincipalClass</key>
  <string>NSApplication</string>
  <key>NSHighResolutionCapable</key>
  <true/>
  <key>LSMinimumSystemVersion</key>
  <string>13.0</string>
</dict>
</plist>
PLIST
printf "APPL????" > "$TMP_APP/Contents/PkgInfo"

if command -v codesign >/dev/null; then
  codesign --remove-signature "$TMP_APP" 2>/dev/null || true
  if ! codesign --force --sign - "$TMP_APP"; then
    echo "warning: unable to sign app bundle; continuing with unsigned bundle" >&2
  fi
fi

mv "$TMP_APP" "$APP"
echo "$APP"
