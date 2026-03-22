import asyncio
import json
import requests
import websockets
from datetime import datetime
from collections import deque, defaultdict
import pytz
import numpy as np
import logging

# ----------------------
# CONFIGURATION
# ----------------------
BOT_TOKEN = "8751531182:AAHRVd3Zeo7Z9wUWb9q7ruiH_lppQE_ymak""
CHAT_ID = "8308393231"
DERIV_WS = "wss://ws.binaryws.com/websockets/v3?app_id=1089"
TIMEZONE = pytz.timezone("Africa/Lagos")

EXPIRY_MINUTES = 5
MAX_PRICES = 5000
MIN_SIGNAL_INTERVAL = 60

CRYPTO_PAIRS = [
    "cryBTCUSD","cryETHUSD","cryLTCUSD","cryXRPUSD","cryBCHUSD",
    "cryEOSUSD","cryTRXUSD","cryADAUSD","cryBNBUSD","cryDOTUSD",
    "cryLINKUSD","cryXLMUSD","cryDOGEUSD","cryUNIUSD","crySOLUSD"
]

# ----------------------
# GLOBAL STATE
# ----------------------
prices = defaultdict(lambda: deque(maxlen=MAX_PRICES))
last_signal_time = datetime.min.replace(tzinfo=TIMEZONE)
signal_count_hour = 0
last_hour = None
pending_signal = None
signal_ready = False

# ----------------------
# LOGGING
# ----------------------
logging.basicConfig(level=logging.INFO)

# ----------------------
# EMA FUNCTION
# ----------------------
def ema(data, period):
    if len(data) < period:
        return None
    k = 2 / (period + 1)
    val = data[0]
    for p in data:
        val = p * k + val * (1 - k)
    return val

# ----------------------
# TREND ANALYSIS
# ----------------------
def analyze_pair(p):
    if len(p) < 60:
        return None, 0
    p = list(p)
    e1 = ema(p[-10:], 3)
    e2 = ema(p[-20:], 5)
    e3 = ema(p[-30:], 8)
    e4 = ema(p[-50:], 13)
    if not all([e1, e2, e3, e4]):
        return None, 0
    direction = None
    score = 0
    if e1 > e2 > e3 > e4:
        direction = "BUY"
        score += 30
    elif e1 < e2 < e3 < e4:
        direction = "SELL"
        score += 30
    if not direction:
        return None, 0
    diff = np.diff(p[-6:])
    if direction == "BUY" and np.all(diff > 0):
        score += 25
    if direction == "SELL" and np.all(diff < 0):
        score += 25
    std = np.std(p[-30:])
    mean = np.mean(p[-30:])
    if std / mean < 0.004:
        score += 20
    last = np.diff(p[-3:])
    if direction == "BUY" and np.all(last > 0):
        score += 25
    if direction == "SELL" and np.all(last < 0):
        score += 25
    return direction, score

# ----------------------
# TELEGRAM SIGNAL
# ----------------------
def send_signal(pair, direction, accuracy, trend_type):
    arrow = "⬆️" if direction == "BUY" else "⬇️"
    msg = f"""🔥 ELITE SIGNAL 🔥

Pair: {pair}
Direction: {direction} {arrow}
Type: {trend_type}
Accuracy: {accuracy}%
Expiry: {EXPIRY_MINUTES} min
"""
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": msg}
        )
        logging.info(f"SENT: {pair} {direction} {accuracy}%")
    except Exception as e:
        logging.error(e)

# ----------------------
# GET FOREX SYMBOLS
# ----------------------
async def get_symbols():
    try:
        async with websockets.connect(DERIV_WS, ping_interval=30, ping_timeout=10) as ws:
            await ws.send(json.dumps({"active_symbols": "brief"}))
            res = json.loads(await ws.recv())
            return [s["symbol"] for s in res["active_symbols"] if s["symbol"].startswith("frx")]
    except Exception as e:
        logging.error(f"Error fetching forex symbols: {e}")
        return []

# ----------------------
# ROBUST WEBSOCKET HANDLER
# ----------------------
async def connect_ws(symbols):
    while True:
        try:
            async with websockets.connect(DERIV_WS, ping_interval=30, ping_timeout=10) as ws:
                # Subscribe to all symbols
                for s in symbols:
                    await ws.send(json.dumps({"ticks": s, "subscribe": 1}))

                async for msg in ws:
                    data = json.loads(msg)
                    if "tick" not in data:
                        continue

                    pair = data["tick"]["symbol"]
                    price = data["tick"]["quote"]
                    prices[pair].append(price)

                    if len(prices[pair]) < 60:
                        continue

                    direction, score = analyze_pair(prices[pair])
                    if not direction or score < 75:
                        pending_signal = None
                        signal_ready = False
                        continue

                    # Require consecutive tick alignment
                    if pending_signal and pending_signal[0] == pair and pending_signal[1] == direction:
                        signal_ready = True
                    else:
                        pending_signal = (pair, direction, score)
                        signal_ready = False

                    # Send signal only when ready
                    if signal_ready:
                        global last_signal_time, signal_count_hour
                        if signal_count_hour >= 2:
                            continue
                        if (datetime.now(TIMEZONE) - last_signal_time).total_seconds() < MIN_SIGNAL_INTERVAL:
                            continue
                        accuracy = min(95, int(score))
                        trend_type = "Stable Trend" if score < 90 else "Strong Breakout"
                        send_signal(pair, direction, accuracy, trend_type)
                        last_signal_time = datetime.now(TIMEZONE)
                        signal_count_hour += 1
                        pending_signal = None
                        signal_ready = False
                        await asyncio.sleep(EXPIRY_MINUTES * 60)

        except (websockets.ConnectionClosedError, websockets.ConnectionClosedOK, asyncio.TimeoutError) as e:
            logging.warning(f"WebSocket disconnected, reconnecting: {e}")
            await asyncio.sleep(5)
        except Exception as e:
            logging.error(f"Unexpected error: {e}")
            await asyncio.sleep(5)

# ----------------------
# SYSTEM LOOP
# ----------------------
async def system_loop():
    global signal_count_hour, last_hour
    while True:
        now = datetime.now(TIMEZONE)
        if last_hour != now.hour:
            signal_count_hour = 0
            last_hour = now.hour

        weekday = now.weekday()
        hour = now.hour
        if (weekday == 4 and hour >= 21) or weekday in [5,6]:
            symbols = CRYPTO_PAIRS
        else:
            symbols = await get_symbols()

        await connect_ws(symbols)

# ----------------------
# RUN SYSTEM
# ----------------------
asyncio.run(system_loop())
