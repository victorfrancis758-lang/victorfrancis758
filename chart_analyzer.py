# chart_analyzer.py
import cv2
import numpy as np
from PIL import Image

def read_candlesticks(image: Image):
    """
    Detects candlestick patterns from screenshot.
    Returns:
        - direction: "BUY"/"SELL"/"NO_TRADE"
        - fvg_detected: True/False
        - bos_detected: True/False
    """
    img = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
    
    # Convert to grayscale for analysis
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Simple placeholder logic for demo purposes
    avg_brightness = np.mean(gray)
    direction = "BUY" if avg_brightness > 127 else "SELL"
    
    # Detect rough FVG and BoS placeholders
    fvg_detected = np.std(gray) > 30  # high variance in pixels = potential FVG
    bos_detected = np.max(gray) - np.min(gray) > 100  # big structure break

    return direction, fvg_detected, bos_detected


def detect_demand_supply(image: Image):
    """
    Detects approximate demand (support) and supply (resistance) zones.
    Returns two prices scaled 0-100 (can be linked to real chart later).
    """
    img = np.array(image)
    gray = np.mean(img, axis=2)
    series = np.mean(gray, axis=0)
    series = (series - np.min(series)) / (np.max(series) - np.min(series) + 1e-9)

    demand_zone = round(np.min(series) * 100, 2)
    supply_zone = round(np.max(series) * 100, 2)
    return demand_zone, supply_zone
