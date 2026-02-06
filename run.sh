#!/bin/bash
# TPMS BLE Monitor - Run Interactive Version
# Activates venv and runs the interactive monitor

set -e  # Exit on error

# Check if venv exists
if [ ! -d "venv" ]; then
    echo "Error: Virtual environment not found"
    echo "Run setup first: ./setup.sh"
    exit 1
fi

# Activate virtual environment
source venv/bin/activate

# Run the interactive TPMS monitor
python tpms-interactive.py
