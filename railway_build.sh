#!/bin/bash
# Make sure script is executable and installs dependencies

echo "Starting Railway build script..."
pip install --upgrade pip
pip install -r requirements.txt
