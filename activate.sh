#!/bin/bash
# Quick venv activation helper
# Usage: source activate.sh

if [ ! -d "venv" ]; then
    echo "Error: Virtual environment not found"
    echo "Run setup first: ./setup.sh"
    return 1 2>/dev/null || exit 1
fi

source venv/bin/activate
echo "✓ TPMS virtual environment activated"
echo "  Deactivate with: deactivate"
