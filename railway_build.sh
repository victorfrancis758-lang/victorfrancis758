#!/bin/bash
# ======================================
# RAILWAY BUILD SCRIPT
# ======================================
# This script installs dependencies and ensures the environment is ready
# for deploying the AI Trading Signal Bot on Railway.

echo "Starting Railway Build Script..."

# Upgrade pip
python -m pip install --upgrade pip

# Install required Python packages from requirements.txt
if [ -f "requirements.txt" ]; then
    echo "Installing Python dependencies..."
    pip install --no-cache-dir -r requirements.txt
else
    echo "Error: requirements.txt not found!"
    exit 1
fi

# Verify that the Telegram bot and websockets packages are installed
echo "Verifying installations..."
python -c "import telegram; print('python-telegram-bot installed')"
python -c "import websockets; print('websockets installed')"
python -c "import numpy; print('numpy installed')"
python -c "import PIL; print('Pillow installed')"
python -c "import pytz; print('pytz installed')"
python -c "import pytesseract; print('pytesseract installed')"

echo "Railway Build Script finished successfully!"
