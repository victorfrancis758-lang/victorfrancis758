#!/bin/bash
# Railway build script for AI Trading Bot with Tesseract OCR

# Update system packages
sudo apt-get update
sudo apt-get install -y tesseract-ocr

# Activate virtual environment
python -m venv /app/.venv
source /app/.venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install Python dependencies
pip install -r requirements.txt

# Run the bot
python main.py
