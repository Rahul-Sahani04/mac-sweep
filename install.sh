#!/usr/bin/env bash
# install.sh — one-liner setup for mac-sweep
set -euo pipefail

TOOL_NAME="mac-sweep"
INSTALL_DIR="/usr/local/bin"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

echo ""
echo "  🧹  Installing mac-sweep..."
echo ""

# Check Python 3
if ! command -v python3 &>/dev/null; then
    echo "  ✗  Python 3 is required. Install via: brew install python"
    exit 1
fi

# Create and populate local virtualenv
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/python" -m pip install --quiet --upgrade pip
if [ -f "$SCRIPT_DIR/requirements.txt" ]; then
    "$VENV_DIR/bin/python" -m pip install --quiet -r "$SCRIPT_DIR/requirements.txt"
else
    "$VENV_DIR/bin/python" -m pip install --quiet rich
fi

# Copy script and make executable
cp "$SCRIPT_DIR/mac_sweep.py" "$INSTALL_DIR/$TOOL_NAME"
chmod +x "$INSTALL_DIR/$TOOL_NAME"

# Fix shebang to use virtualenv python
sed -i '' "1s|.*|#!$VENV_DIR/bin/python|" "$INSTALL_DIR/$TOOL_NAME"

echo "  ✓  Installed to $INSTALL_DIR/$TOOL_NAME"
echo "  ✓  Virtualenv ready at $VENV_DIR"
echo ""
echo "  Usage:"
echo "    ./run.sh scan          # run from this repository"
echo "    mac-sweep scan          # find all junk"
echo "    mac-sweep clean         # interactive cleanup"
echo "    mac-sweep clean -s      # safe-only auto mode"
echo "    mac-sweep large         # find big files"
echo "    mac-sweep doctor        # quick health check"
echo ""
