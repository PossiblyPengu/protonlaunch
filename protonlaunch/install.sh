#!/bin/bash
# ProtonLaunch installer for Steam Deck
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$HOME/.local/share/protonlaunch"
DESKTOP_DIR="$HOME/.local/share/applications"
BIN_DIR="$HOME/.local/bin"
BINARY_SOURCE="$SCRIPT_DIR/dist/protonlaunch"

echo "=== ProtonLaunch Installer ==="
echo ""

# Install app
echo "Installing ProtonLaunch..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$BIN_DIR"

if [ -x "$BINARY_SOURCE" ]; then
    echo "Using self-contained onefile build."
    cp "$BINARY_SOURCE" "$BIN_DIR/protonlaunch"
    chmod +x "$BIN_DIR/protonlaunch"
else
    echo "No onefile binary found; installing Python source mode."
    echo "Checking Python dependencies..."
    if ! /usr/bin/python3 -c "import PyQt6, requests" 2>/dev/null; then
        echo "Installing user Python dependencies (PyQt6 + requests)..."
        /usr/bin/python3 -m pip install --user PyQt6 requests
    fi

    rm -rf "$INSTALL_DIR/protonlaunch"
    cp -a "$SCRIPT_DIR" "$INSTALL_DIR/"
    chmod +x "$INSTALL_DIR/protonlaunch/protonlaunch.py"

    # Create launcher script
    cat > "$BIN_DIR/protonlaunch" << 'EOF'
#!/bin/bash
PYTHONPATH="$HOME/.local/share/protonlaunch" /usr/bin/python3 -m protonlaunch.protonlaunch "$@"
EOF
    chmod +x "$BIN_DIR/protonlaunch"
fi

# Desktop entry
mkdir -p "$DESKTOP_DIR"
sed "s|/home/deck|$HOME|g" "$SCRIPT_DIR/protonlaunch.desktop" > "$DESKTOP_DIR/protonlaunch.desktop"
chmod +x "$DESKTOP_DIR/protonlaunch.desktop"
update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true

echo ""
echo "✓ ProtonLaunch installed!"
echo ""
echo "Run with:  protonlaunch"
echo "Or find it in your application menu under Games."
echo ""
echo "To add to Steam Game Mode:"
echo "  1. Open Steam → Add a Game → Add a Non-Steam Game"
echo "  2. Browse to: $BIN_DIR/protonlaunch"
