# ======================================
# CHART ANALYZER MODULE
# ======================================

import numpy as np
from PIL import Image
import cv2  # OpenCV for advanced image analysis

class ChartAnalyzer:
    """
    Analyze screenshots for:
    - Candlestick patterns
    - Fair Value Gaps (FVG)
    - Demand & Supply Zones
    - Break of Structure (BoS)
    - Imbalances
    """
    def preprocess(self, image: Image):
        img = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        return gray

    def detect_candles(self, gray_img):
        edges = cv2.Canny(gray_img, 50, 150)
        vertical_lines = cv2.reduce(edges, 1, cv2.REDUCE_SUM, dtype=cv2.CV_32S)
        candle_count = np.count_nonzero(vertical_lines > 10)
        return candle_count

    def detect_fvg(self, gray_img):
        hist = cv2.reduce(gray_img, 1, cv2.REDUCE_AVG).flatten()
        diff = np.diff(hist)
        fvg_detected = np.any(np.abs(diff) > 25)
        return fvg_detected

    def detect_zones(self, gray_img):
        min_val, max_val, _, _ = cv2.minMaxLoc(gray_img)
        demand_zone = round(min_val / 255 * 100, 2)
        supply_zone = round(max_val / 255 * 100, 2)
        return demand_zone, supply_zone

    def detect_bos_imbalance(self, gray_img):
        hist = cv2.reduce(gray_img, 1, cv2.REDUCE_AVG).flatten()
        if len(hist) < 5:
            return False, False
        bos = hist[-1] - hist[0] > 10
        imbalance = np.std(hist) > 20
        return bos, imbalance

    def analyze(self, image: Image):
        gray = self.preprocess(image)
        candles = self.detect_candles(gray)
        fvg = self.detect_fvg(gray)
        demand, supply = self.detect_zones(gray)
        bos, imbalance = self.detect_bos_imbalance(gray)
        return {
            "candles": candles,
            "fvg": fvg,
            "demand_zone": demand,
            "supply_zone": supply,
            "bos": bos,
            "imbalance": imbalance
        }

# Create a single instance to use in main.py
analyzer = ChartAnalyzer()
