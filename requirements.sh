#!/bin/bash

# Update system packages
apt-get update

# Install Tesseract OCR
apt-get install -y tesseract-ocr

# Optional: English language support
apt-get install -y tesseract-ocr-eng
