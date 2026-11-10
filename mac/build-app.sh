#!/bin/zsh
# Build Hookscope.app into ./build, signed with your free Apple Development certificate (ad-hoc if none).
# Run again after moving the hookscope folder: the app remembers where the folder is.
set -euo pipefail

ROOT="${0:A:h:h}"
OUT="$ROOT/build/Hookscope.app"
SRC="$ROOT/mac"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "Building Hookscope.app for $ROOT"
rm -rf "$OUT"
mkdir -p "$OUT/Contents/MacOS" "$OUT/Contents/Resources"

swiftc -O -target arm64-apple-macos13 -framework AppKit "$SRC/main.swift" -o "$OUT/Contents/MacOS/Hookscope"

"$ROOT/.venv/bin/python" "$SRC/make_icon.py" "$TMP/AppIcon.iconset" >/dev/null
iconutil -c icns "$TMP/AppIcon.iconset" -o "$OUT/Contents/Resources/AppIcon.icns"

cat > "$OUT/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Hookscope</string>
  <key>CFBundleDisplayName</key><string>Hookscope</string>
  <key>CFBundleIdentifier</key><string>local.vishal.hookscope</string>
  <key>CFBundleExecutable</key><string>Hookscope</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
  <key>LSApplicationCategoryType</key><string>public.app-category.productivity</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSAppTransportSecurity</key><dict><key>NSAllowsLocalNetworking</key><true/></dict>
  <key>HookscopeRoot</key><string>$ROOT</string>
</dict>
</plist>
PLIST

IDENTITY="$(security find-identity -v -p codesigning 2>/dev/null | awk -F'"' '/Apple Development/ {print $2; exit}')"
if [[ -n "$IDENTITY" ]]; then
  codesign --force --sign "$IDENTITY" --timestamp=none "$OUT"
  echo "Signed with: $IDENTITY"
else
  codesign --force --sign - "$OUT"
  echo "Signed ad-hoc (no Apple Development certificate found)"
fi
codesign --verify --strict "$OUT" && echo "Built: $OUT"
