#!/bin/bash
# One-command ProtonLaunch installer for Steam Deck.
# Downloads the latest prebuilt binary — no pip, pacman, or developer mode needed.
#
#   curl -fsSL https://raw.githubusercontent.com/PossiblyPengu/protonlaunch/main/get.sh | bash
set -euo pipefail

REPO="PossiblyPengu/protonlaunch"
ASSET="protonlaunch-linux-x86_64"
BASE_URL="https://github.com/$REPO/releases/latest/download"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "=== ProtonLaunch Installer ==="

echo "Downloading latest release…"
curl -fL --progress-bar -o "$TMP/$ASSET" "$BASE_URL/$ASSET"
curl -fsSL -o "$TMP/$ASSET.sha256" "$BASE_URL/$ASSET.sha256"

echo "Verifying checksum…"
(cd "$TMP" && sha256sum -c "$ASSET.sha256")

mkdir -p "$BIN_DIR" "$DESKTOP_DIR"
install -m 755 "$TMP/$ASSET" "$BIN_DIR/protonlaunch"

cat > "$DESKTOP_DIR/protonlaunch.desktop" << EOF
[Desktop Entry]
Name=ProtonLaunch
Comment=Install and launch Windows games and programs on Steam Deck
Exec=$BIN_DIR/protonlaunch
Icon=applications-games
Terminal=false
Type=Application
Categories=Game;
StartupNotify=true
EOF
chmod +x "$DESKTOP_DIR/protonlaunch.desktop"
update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true

echo ""
echo "✓ ProtonLaunch installed to $BIN_DIR/protonlaunch"
echo "  Find it in the app menu under Games, or run: $BIN_DIR/protonlaunch"
echo ""
echo "To use it from Game Mode, open ProtonLaunch and click \"⚙ Add Tool to Steam\","
echo "then restart Steam."
