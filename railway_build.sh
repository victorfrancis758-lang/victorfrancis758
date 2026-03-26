#!/bin/bash
# ----------------------------------------
# Railway Build Script - Executes on deploy
# ----------------------------------------

# Upgrade pip and install dependencies
python -m pip install --upgrade pip
pip install -r requirements.txt

echo "Build script executed successfully."
