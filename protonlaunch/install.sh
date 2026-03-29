#!/bin/bash
# ProtonLaunch installer for Steam Deck
set -e

INSTALL_DIR="$HOME/.local/share/protonlaunch"
DESKTOP_DIR="$HOME/.local/share/applications"
BIN_DIR="$HOME/.local/bin"

echo "=== ProtonLaunch Installer ==="
echo ""

# Check PyQt6
echo "Checking dependencies..."
if ! python3 -c "import PyQt6" 2>/dev/null; then
    echo "Installing PyQt6..."
    pip install --user PyQt6
fi

# Install app
echo "Installing ProtonLaunch..."
mkdir -p "$INSTALL_DIR"
cp protonlaunch.py "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/protonlaunch.py"

# Create launcher script
mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/protonlaunch" << 'EOF'
#!/bin/bash
python3 "$HOME/.local/share/protonlaunch/protonlaunch.py" "$@"
EOF
chmod +x "$BIN_DIR/protonlaunch"

# Desktop entry
mkdir -p "$DESKTOP_DIR"
sed "s|/home/deck|$HOME|g" protonlaunch.desktop > "$DESKTOP_DIR/protonlaunch.desktop"
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
