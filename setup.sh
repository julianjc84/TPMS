#!/bin/bash
# TPMS BLE Monitor - Setup Script
# Creates virtual environment and installs dependencies

set -e  # Exit on error

echo "======================================"
echo "TPMS BLE Monitor - Setup"
echo "======================================"
echo

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 is not installed"
    echo "Install with: sudo apt install python3 python3-venv"
    exit 1
fi

# Check if venv module is available
if ! python3 -m venv --help &> /dev/null; then
    echo "Error: python3-venv is not installed"
    echo "Install with: sudo apt install python3-venv"
    exit 1
fi

# Create virtual environment
if [ -d "venv" ]; then
    echo "Virtual environment already exists (venv/)"
    read -p "Remove and recreate? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Removing old virtual environment..."
        rm -rf venv
    else
        echo "Keeping existing virtual environment"
        exit 0
    fi
fi

echo "Creating virtual environment..."
python3 -m venv venv

echo "Activating virtual environment..."
source venv/bin/activate

echo "Upgrading pip..."
pip install --upgrade pip

echo "Installing dependencies..."
pip install -r requirements.txt

echo
echo "======================================"
echo "Setup Complete!"
echo "======================================"
echo
echo "To activate the virtual environment:"
echo "  source venv/bin/activate"
echo
echo "To run the TPMS monitor:"
echo "  ./run.sh"
echo
echo "Or if venv is already activated:"
echo "  python tpms-interactive.py"
echo
echo "Tip: To keep venv active, run this script with 'source':"
echo "  source ./setup.sh"
echo

# Offer to activate venv in current shell
if [ "$0" = "${BASH_SOURCE[0]}" ]; then
    # Script was executed, not sourced
    echo "Would you like to activate the venv now? (Creates a new shell)"
    read -p "Activate venv? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Starting new shell with venv activated..."
        echo "Type 'exit' to leave the venv shell"
        echo
        bash --rcfile <(echo '. venv/bin/activate; PS1="(tpms-venv) \u@\h:\w\$ "')
    fi
else
    # Script was sourced
    echo "Activating venv in current shell..."
    source venv/bin/activate
fi
