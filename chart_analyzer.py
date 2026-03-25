# chart_analyzer.py
import cv2
import numpy as np
from PIL import Image

# -------------------------------
# REAL CHART DETECTION SYSTEM
# -------------------------------
class ChartAnalyzer:
    """
    Analyze screenshots for:
    - Candlestick patterns
    - Fair Value Gaps (FVG)
    - Demand & Supply Zones
    - Break of Structure (BoS)
    - Imbalances
    """

    def __init__(self):
        # You can add pre-trained ML models or CV configs here later
        pass

    def preprocess(self, image: Image):
        """Convert PIL image to OpenCV grayscale numpy array"""
        img = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        return gray

    def detect_candles(self, gray_img):
        """Detect basic candlestick structure from the image"""
        # Example heuristic: detect vertical lines for candles
        edges = cv2.Canny(gray_img, 50, 150)
        vertical_lines = cv2.reduce(edges, 1, cv2.REDUCE_SUM, dtype=cv2.CV_32S)
        candle_count = np.count_nonzero(vertical_lines > 10)
        return candle_count

    def detect_fvg(self, gray_img):
        """Detect potential FVG (Fair Value Gap) areas"""
        # Simple CV heuristic: large gaps between high/low regions
        hist = cv2.reduce(gray_img, 1, cv2.REDUCE_AVG).flatten()
        diff = np.diff(hist)
        fvg_detected = np.any(np.abs(diff) > 25)  # threshold can be tuned
        return fvg_detected

    def detect_zones(self, gray_img):
        """Detect simple demand and supply zones"""
        min_val, max_val, _, _ = cv2.minMaxLoc(gray_img)
        demand_zone = round(min_val / 255 * 100, 2)
        supply_zone = round(max_val / 255 * 100, 2)
        return demand_zone, supply_zone

    def detect_bos_imbalance(self, gray_img):
        """Detect Break of Structure and Imbalances"""
        # Example heuristic: compare moving averages of high/low regions
        hist = cv2.reduce(gray_img, 1, cv2.REDUCE_AVG).flatten()
        if len(hist) < 5:
            return False, False
        bos = hist[-1] - hist[0] > 10   # structure break
        imbalance = np.std(hist) > 20   # imbalance
        return bos, imbalance

    def analyze(self, image: Image):
        gray = self.preprocess(image)
        candle_count = self.detect_candles(gray)
        fvg = self.detect_fvg(gray)
        demand, supply = self.detect_zones(gray)
        bos, imbalance = self.detect_bos_imbalance(gray)

        return {
            "candles": candle_count,
            "fvg": fvg,
            "demand_zone": demand,
            "supply_zone": supply,
            "bos": bos,
            "imbalance": imbalance
        }
