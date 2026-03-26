#!/bin/bash
# Install Tesseract OCR before running the bot

# Update package list
apt-get update

# Install Tesseract OCR
apt-get install -y tesseract-ocr

# Optional: install English language pack (usually default)
# apt-get install -y tesseract-ocr-eng

# Start the bot
python main.py
