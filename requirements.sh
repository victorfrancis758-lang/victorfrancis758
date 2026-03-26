#!/bin/bash

# Update package list
apt-get update

# Install Tesseract OCR
apt-get install -y tesseract-ocr

# Optional: install English language if needed
apt-get install -y tesseract-ocr-eng

echo "Tesseract OCR installed successfully."
