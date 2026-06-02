#!/usr/bin/env bash
# setup.sh — Cross-platform setup script for Linux/macOS
# Usage: bash setup.sh

set -e

echo "=== Schedule Viewer App Setup ==="

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv venv
fi

# Activate and install dependencies
echo "Installing dependencies..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "=== Setup complete ==="
echo "To run the application:"
echo "  source venv/bin/activate"
echo "  python main.py"
echo ""
echo "On Linux, the VBA/CSV-pull features will be disabled."
echo "The calendar viewer, timeline, and edit-form will work."