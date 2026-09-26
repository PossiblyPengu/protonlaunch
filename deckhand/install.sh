#!/bin/bash
# Install Deckhand from a source checkout (most people should use get.sh instead).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"
INSTALL_DIR="$HOME/.local/share/deckhand/app"

mkdir -p "$BIN_DIR" "$DESKTOP_DIR"

if [ -x "$ROOT_DIR/dist/deckhand" ]; then
    echo "Installing onefile build…"
    install -m 755 "$ROOT_DIR/dist/deckhand" "$BIN_DIR/deckhand"
else
    echo "No onefile build found (run build_onefile.sh); installing from source."
    python3 -c "import PyQt6" 2>/dev/null || python3 -m pip install --user -r "$ROOT_DIR/requirements.txt"
    rm -rf "$INSTALL_DIR"
    mkdir -p "$INSTALL_DIR"
    cp -a "$SCRIPT_DIR" "$INSTALL_DIR/"
    cat > "$BIN_DIR/deckhand" << LAUNCH
#!/bin/bash
PYTHONPATH="$INSTALL_DIR" exec python3 -m deckhand "\$@"
LAUNCH
    chmod +x "$BIN_DIR/deckhand"
fi

sed "s|/home/deck|$HOME|g" "$SCRIPT_DIR/deckhand.desktop" > "$DESKTOP_DIR/deckhand.desktop"
chmod +x "$DESKTOP_DIR/deckhand.desktop"
update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true

echo "✓ Installed. Run 'deckhand' or find it in the app menu."
