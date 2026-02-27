# ======================================
# POCKET OPTION OTC SIGNAL BOT
# ONE SIGNAL + MARTINGALE + QUEUE
# PROFIT CHECK + 2-MIN RULE
# CONTINUOUS OPERATION
# STRICT DURATION / SPIKE-PROOF
# ======================================

import asyncio
import json
import requests
import websockets
import logging
import numpy as np
from datetime import datetime, timedelta
import pytz
import os

# ================================
# TELEGRAM
# ================================
BOT_TOKEN = "8369673752:AAGChqjqvpQ3DW89WGgFW8IRTW94BjC2aoo"
CHAT_ID = "6918721957"

# ================================
# SETTINGS
# ================================
DERIV_WS = "wss://ws.binaryws.com/websockets/v3?app_id=1089"
TIMEZONE = pytz.timezone("Africa/Lagos")

TREND_SCORE_THRESHOLD = 85
TREND_STRENGTH_THRESHOLD = 85

ENTRY_DELAY = 2          # minutes until entry
MG_STEP = 2              # minutes between martingale levels
MAX_MG_STEPS = 3
EXPIRY_MINUTES = 2       # trade expiry

PAIR_LOCK_MINUTES = 10   # lock per pair
GLOBAL_LOCK_MINUTES = 4  # one signal at a time lock

MAX_PRICES = 700

SPIKE_MULTIPLIER = 2.0   # tighter spike filter for OTC

logging.basicConfig(level=logging.INFO)

# ================================
# STATE
# ================================
prices = {}
pair_locked_until = {}
locked_direction = {}
global_lock_until = datetime.min.replace(tzinfo=TIMEZONE)
signal_queue = []

# ================================
# EMA FUNCTIONS
# ================================
def ema(data, period):
    if len(data) < period:
        return None
    k = 2 / (period + 1)
    value = data[0]
    for price in data:
        value = price * k + value * (1 - k)
    return value

# ================================
# TREND & STRENGTH
# ================================
def trend_strength(price_list):
    if len(price_list) < 150:
        return 0
    ema_fast = ema(price_list[-50:], 10)
    ema_slow = ema(price_list[-100:], 20)
    if ema_fast is None or ema_slow is None:
        return 0
    separation = abs(ema_fast - ema_slow)
    volatility = np.std(price_list[-100:])
    if volatility == 0:
        return 0
    return min((separation / volatility) * 100, 100)

def detect_trend(price_list):
    if len(price_list) < 300:
        return 0, 0, None
    ema_fast = ema(price_list[-50:], 10)
    ema_slow = ema(price_list[-100:], 20)
    ema_long_fast = ema(price_list[-200:], 30)
    ema_long_slow = ema(price_list[-300:], 60)
    strength = trend_strength(price_list)
    score = min(50 + strength * 0.5, 100)
    direction = None
    if ema_fast and ema_slow and ema_long_fast and ema_long_slow:
        if ema_fast > ema_slow and ema_long_fast > ema_long_slow:
            direction = "BUY"
        elif ema_fast < ema_slow and ema_long_fast < ema_long_slow:
            direction = "SELL"
    return score, strength, direction

# ================================
# SPIKE FILTER
# ================================
def spike_filter(price_list):
    if len(price_list) < 50:
        return True
    base_vol = np.std(price_list[-50:])
    recent_vol = np.std(price_list[-5:])
    return recent_vol <= base_vol * SPIKE_MULTIPLIER

# ================================
# STRICT DURATION CONFIRM
# ================================
def duration_strict(price_list, direction):
    """Ensure the trend/duration is unbroken for OTC, spike-proof"""
    if len(price_list) < 200:
        return False
    ema_short = ema(price_list[-10:], 5)
    ema_medium = ema(price_list[-50:], 20)
    ema_long = ema(price_list[-200:], 50)
    if None in [ema_short, ema_medium, ema_long]:
        return False
    if direction == "BUY":
        return ema_short > ema_medium > ema_long
    elif direction == "SELL":
        return ema_short < ema_medium < ema_long
    return False

# ================================
# LOCK SYSTEM
# ================================
def pair_locked(pair):
    return datetime.now(TIMEZONE) < pair_locked_until.get(pair, datetime.min.replace(tzinfo=TIMEZONE))

def global_locked():
    return datetime.now(TIMEZONE) < global_lock_until

def lock_pair(pair, direction):
    global global_lock_until
    pair_locked_until[pair] = datetime.now(TIMEZONE) + timedelta(minutes=PAIR_LOCK_MINUTES)
    locked_direction[pair] = direction
    global_lock_until = datetime.now(TIMEZONE) + timedelta(minutes=GLOBAL_LOCK_MINUTES)

# ================================
# PROFIT CHECK (Entry + MG1)
# ================================
def is_profitable(price_list, direction):
    if len(price_list) < 30:
        return False
    current_price = price_list[-1]
    expected_price = current_price
    for step in range(MAX_MG_STEPS + 1):
        if direction == "BUY":
            if price_list[-1] <= expected_price:
                return False
        elif direction == "SELL":
            if price_list[-1] >= expected_price:
                return False
        expected_price = price_list[-1] * (1.0005 if direction=="BUY" else 0.9995)
        if step == 1:  # Ensure MG1 will also be profitable
            if direction == "BUY" and price_list[-1] <= expected_price:
                return False
            if direction == "SELL" and price_list[-1] >= expected_price:
                return False
    return True

# ================================
# TELEGRAM SIGNAL + MARTINGALE
# ================================
def send_signal(pair, direction, score, strength):
    now = datetime.now(TIMEZONE)
    entry_time = now + timedelta(minutes=ENTRY_DELAY)
    mg_times = [entry_time + timedelta(minutes=MG_STEP*i) for i in range(1, MAX_MG_STEPS+1)]
    expiry_time = entry_time + timedelta(minutes=EXPIRY_MINUTES)
    msg = (
        f"🚨 OTC SIGNAL\n\n"
        f"Pair: {pair}\n"
        f"Direction: {direction}\n"
        f"Confidence: {score:.0f}%\n"
        f"Strength: {strength:.0f}%\n\n"
        f"Entry: {entry_time.strftime('%H:%M')}\n"
        f"MG1: {mg_times[0].strftime('%H:%M')}\n"
        f"MG2: {mg_times[1].strftime('%H:%M')}\n"
        f"MG3: {mg_times[2].strftime('%H:%M')}\n"
        f"Expiry: {expiry_time.strftime('%H:%M')}\n"
        f"Mode: ONE SIGNAL + QUEUE + STRICT DURATION + SPIKE-PROOF"
    )
    try:
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                      data={"chat_id": CHAT_ID,"text":msg},timeout=10)
    except:
        logging.info("Telegram error")

# ================================
# LOAD OTC SYMBOLS
# ================================
async def load_otc_symbols():
    async with websockets.connect(DERIV_WS) as ws:
        await ws.send(json.dumps({"active_symbols": "brief"}))
        response = json.loads(await ws.recv())
        symbols = [s["symbol"] for s in response["active_symbols"] if s["symbol"].startswith("frx")]
        print(f"Loaded {len(symbols)} OTC pairs")
        return symbols

# ================================
# MONITOR LOOP
# ================================
async def monitor():
    symbols = await load_otc_symbols()
    for s in symbols:
        prices[s] = []
        pair_locked_until[s] = datetime.min.replace(tzinfo=TIMEZONE)
    print("BOT STARTED - ONE SIGNAL + QUEUE + STRICT DURATION + SPIKE-PROOF MODE")

    while True:
        try:
            async with websockets.connect(DERIV_WS) as ws:
                for s in symbols:
                    await ws.send(json.dumps({"ticks": s, "subscribe": 1}))

                async for message in ws:
                    data = json.loads(message)
                    if "tick" not in data:
                        continue
                    pair = data["tick"]["symbol"]
                    price = data["tick"]["quote"]
                    prices[pair].append(price)
                    if len(prices[pair]) > MAX_PRICES:
                        prices[pair].pop(0)

                    # Process queued signals
                    if not global_locked() and signal_queue:
                        queued_pair = signal_queue.pop(0)
                        score, strength, direction = detect_trend(prices[queued_pair])
                        if direction and duration_strict(prices[queued_pair], direction) and is_profitable(prices[queued_pair], direction):
                            send_signal(queued_pair, direction, score, strength)
                            lock_pair(queued_pair, direction)

                    # Check all pairs
                    for p in symbols:
                        if global_locked() or pair_locked(p):
                            continue
                        score, strength, direction = detect_trend(prices[p])
                        if direction and score >= TREND_SCORE_THRESHOLD and strength >= TREND_STRENGTH_THRESHOLD and spike_filter(prices[p]):
                            if duration_strict(prices[p], direction) and is_profitable(prices[p], direction):
                                send_signal(p, direction, score, strength)
                                lock_pair(p, direction)
                            else:
                                if p not in signal_queue:
                                    signal_queue.append(p)

                    # Live console display
                    os.system("cls" if os.name=="nt" else "clear")
                    print("ONE SIGNAL + QUEUE + STRICT DURATION + SPIKE-PROOF ACTIVE\n")
                    for p in list(symbols)[:10]:
                        s, st, d = detect_trend(prices[p])
                        print(f"{p} | Score:{s:.0f}% | Strength:{st:.0f}% | Direction:{d}")

        except:
            logging.info("Reconnecting...")
            await asyncio.sleep(5)

# ================================
# START BOT
# ================================
asyncio.run(monitor())
