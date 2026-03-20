#!/usr/bin/env bash
# run.sh — run mac_sweep.py using the local virtual environment
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
PYTHON_BIN="$VENV_DIR/bin/python"

if [ ! -x "$PYTHON_BIN" ]; then
    echo "Virtual environment not found at $VENV_DIR"
    echo "Run ./install.sh first."
    exit 1
fi

exec "$PYTHON_BIN" "$SCRIPT_DIR/mac_sweep.py" "$@"
