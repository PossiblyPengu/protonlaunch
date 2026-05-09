#!/bin/bash
# Build a self-contained single-file ProtonLaunch executable (Steam Deck/Linux).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== Building ProtonLaunch onefile binary ==="
echo "Project root: $ROOT_DIR"

/usr/bin/python3 -m pip install --user --upgrade pyinstaller PyQt6 requests

cd "$ROOT_DIR"
/usr/bin/python3 -m PyInstaller \
  --noconfirm \
  --clean \
  --onefile \
  --name protonlaunch \
  --paths "$ROOT_DIR" \
  --hidden-import PyQt6.sip \
  protonlaunch/protonlaunch.py

mkdir -p "$SCRIPT_DIR/dist"
cp -f "$ROOT_DIR/dist/protonlaunch" "$SCRIPT_DIR/dist/protonlaunch"
chmod +x "$SCRIPT_DIR/dist/protonlaunch"

echo ""
echo "Built: $SCRIPT_DIR/dist/protonlaunch"
echo "Install it with: ./install.sh"
