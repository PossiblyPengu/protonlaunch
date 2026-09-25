#!/bin/bash
# One-command ProtonLaunch installer for Steam Deck.
# Downloads the latest prebuilt binary — no pip, pacman, or developer mode needed.
#
#   curl -fsSL https://raw.githubusercontent.com/PossiblyPengu/protonlaunch/main/get.sh | bash
set -euo pipefail

REPO="PossiblyPengu/protonlaunch"
# main once merged; the development branch until then. PROTONLAUNCH_BRANCH picks one explicitly.
BRANCHES="${PROTONLAUNCH_BRANCH:-main claude/steam-deck-windows-install-mkeivr}"
ASSET="protonlaunch-linux-x86_64"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "=== ProtonLaunch Installer ==="

echo "Downloading ProtonLaunch…"
for BRANCH in $BRANCHES; do
  # Read files at the branch's current commit: raw.githubusercontent caches branch names for minutes.
  REF=$(curl -fsSL -H "Accept: application/vnd.github.sha" "https://api.github.com/repos/$REPO/commits/$BRANCH" 2>/dev/null || true)
  [[ "$REF" =~ ^[0-9a-f]{40}$ ]] || REF="$BRANCH"
  BASE_URL="https://raw.githubusercontent.com/$REPO/$REF/bin"
  if curl -fsSL -o "$TMP/$ASSET.sha256" "$BASE_URL/$ASSET.sha256" 2>/dev/null; then
    curl -fL --progress-bar -o "$TMP/$ASSET" "$BASE_URL/$ASSET"
    break
  fi
done
[ -s "$TMP/$ASSET" ] || { echo "Couldn't download ProtonLaunch — check your internet connection."; exit 1; }

echo "Verifying checksum…"
(cd "$TMP" && sha256sum -c "$ASSET.sha256")

mkdir -p "$BIN_DIR" "$DESKTOP_DIR"
install -m 755 "$TMP/$ASSET" "$BIN_DIR/protonlaunch"

cat > "$DESKTOP_DIR/protonlaunch.desktop" << DESKTOP
[Desktop Entry]
Name=ProtonLaunch
Comment=Install Windows programs and games on Steam Deck
Exec=$BIN_DIR/protonlaunch %f
Icon=applications-games
Terminal=false
Type=Application
Categories=Game;Utility;
MimeType=application/x-ms-dos-executable;application/x-msdownload;application/vnd.microsoft.portable-executable;application/x-msi;application/x-ms-installer;
StartupNotify=true
DESKTOP
chmod +x "$DESKTOP_DIR/protonlaunch.desktop"
update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true

echo ""
echo "✓ $("$BIN_DIR/protonlaunch" --version) installed to $BIN_DIR/protonlaunch"
echo "  Find it in the app menu under Games, or run: $BIN_DIR/protonlaunch"
echo ""
echo "Tip: in Desktop Mode you can right-click any setup .exe → Open With → ProtonLaunch."
echo "To use it from Game Mode, open ProtonLaunch and tap \"Add ProtonLaunch to Steam\"."
