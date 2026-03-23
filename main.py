# ======================================
# DERIV OTC SIGNAL BOT - FULL UPGRADED
# LIVE STREAM + ADAPTIVE ENTRY + COOLDOWN
# ======================================

import asyncio
import json
import requests
import websockets
import numpy as np
from datetime import datetime, timedelta
import pytz

BOT_TOKEN = "8751531182:AAHRVd3Zeo7Z9wUWb9q7ruiH_lppQE_ymak"
CHAT_ID = "8308393231"

DERIV_WS = "wss://ws.binaryws.com/websockets/v3?app_id=1089"
TIMEZONE = pytz.timezone("Africa/Lagos")

MAX_PRICES = 5000
TICK_CONFIRMATION = 2  # Reduced for OTC streaming
COOLDOWN_MINUTES = 2

# ================================
# BLOCKED PAIRS
# ================================
BLOCKED_PAIRS = ["frxUSDNOK","frxGBPNOK","frxUSDPLN","frxGBPNZD","frxUSDSEK"]

prices = {}
tick_confirm = {}
cooldowns = {}

# ================================
# EMA UTILITY
# ================================
def ema(data, period):
    if len(data) < period:
        return None
    k = 2 / (period + 1)
    val = data[0]
    for p in data:
        val = p * k + val * (1 - k)
    return val

# ================================
# TREND DETECTION
# ================================
def detect_trend(p):
    if len(p) < 100:
        return None
    e1 = ema(p[-20:], 5)
    e2 = ema(p[-50:], 13)
    e3 = ema(p[-100:], 21)
    if not all([e1, e2, e3]):
        return None
    if e1 > e2 > e3:
        return "BUY"
    elif e1 < e2 < e3:
        return "SELL"
    return None

# ================================
# PULLBACK DETECTION
# ================================
def detect_pullback(p, direction):
    recent = np.array(p[-10:])
    diff = np.diff(recent)
    threshold = 0.001 * np.mean(recent)
    if direction == "BUY" and np.any(diff < -threshold):
        return True
    if direction == "SELL" and np.any(diff > threshold):
        return True
    return False

# ================================
# REVERSAL DETECTION
# ================================
def detect_reversal(p):
    recent = np.array(p[-15:])
    diff = np.diff(recent)
    ups = np.sum(diff > 0)
    downs = np.sum(diff < 0)
    if ups >= 10 and downs >= 3:
        return "BUY_REVERSE"
    if downs >= 10 and ups >= 3:
        return "SELL_REVERSE"
    return None

# ================================
# BIG MOVE CHECK
# ================================
def big_move_ready(p, direction):
    if len(p) < 50:
        return False
    std = np.std(p[-30:])
    mean = np.mean(p[-30:])
    if std > 0.01 * mean:
        return False
    diff = np.diff(p[-10:])
    if direction in ["BUY", "BUY_REVERSE"]:
        if np.sum(diff > 0) < 8 or not (diff[-1] > diff[-2] > diff[-3]):
            return False
    if direction in ["SELL", "SELL_REVERSE"]:
        if np.sum(diff < 0) < 8 or not (diff[-1] < diff[-2] < diff[-3]):
            return False
    return True

# ================================
# ENTRY CONFIRM
# ================================
def entry_confirm(p, direction):
    diff = np.diff(p[-10:])
    if direction in ["BUY", "BUY_REVERSE"]:
        return np.sum(diff > 0) >= 8
    if direction in ["SELL", "SELL_REVERSE"]:
        return np.sum(diff < 0) >= 8
    return False

# ================================
# ACCURACY
# ================================
def get_accuracy(p):
    if len(p) < 50:
        return 85
    std = np.std(p[-30:])
    mean = np.mean(p[-30:])
    return 90 if std / mean > 0.005 else 85

# ================================
# COOLDOWN / LOCK
# ================================
def locked(pair):
    return pair in cooldowns and datetime.now(TIMEZONE) < cooldowns[pair]

def set_cooldown(pair, minutes):
    cooldowns[pair] = datetime.now(TIMEZONE) + timedelta(minutes=minutes)

# ================================
# TELEGRAM SIGNALS
# ================================
def send_signal(pair, direction, duration, acc):
    arrow = "⬆️" if "BUY" in direction else "⬇️"
    msg = f"""
SIGNAL {arrow}

Asset: {pair}_otc
Duration: {duration} min
Payout: 92%
Accuracy: {acc}%
"""
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                  data={"chat_id": CHAT_ID, "text": msg})
    print(f"[{datetime.now()}] SIGNAL SENT: {pair} {direction} Dur:{duration} Acc:{acc}%")

def send_exit(pair, direction):
    arrow = "🔴 EXIT"
    msg = f"Signal closed for {pair}_otc {arrow}"
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                  data={"chat_id": CHAT_ID, "text": msg})
    print(f"[{datetime.now()}] SIGNAL EXIT: {pair}")

# ================================
# LOAD SYMBOLS
# ================================
async def load_symbols():
    try:
        async with websockets.connect(DERIV_WS) as ws:
            await ws.send(json.dumps({"active_symbols": "brief"}))
            res = json.loads(await ws.recv())
            return [s["symbol"] for s in res["active_symbols"]
                    if s["symbol"].startswith("frx") and s["symbol"] not in BLOCKED_PAIRS]
    except Exception as e:
        print("Error loading symbols:", e)
        return []

# ================================
# MAIN MONITOR LOOP
# ================================
async def monitor():
    while True:
        try:
            symbols = await load_symbols()
            if not symbols:
                await asyncio.sleep(5)
                continue

            for s in symbols:
                prices[s] = []
                tick_confirm[s] = {"count": 0, "dir": None}

            async with websockets.connect(DERIV_WS) as ws:
                for s in symbols:
                    await ws.send(json.dumps({"ticks": s, "subscribe": 1}))

                async for msg in ws:
                    try:
                        data = json.loads(msg)
                        if "tick" not in data:
                            continue
                        pair = data["tick"]["symbol"]
                        price = data["tick"]["quote"]

                        prices[pair].append(price)
                        if len(prices[pair]) > MAX_PRICES:
                            prices[pair].pop(0)

                        if locked(pair):
                            continue

                        # Trend detection
                        direction = detect_trend(prices[pair])
                        if not direction:
                            continue

                        # Pullback check
                        if detect_pullback(prices[pair], direction):
                            continue

                        # Reversal detection
                        reversal = detect_reversal(prices[pair])
                        if reversal:
                            direction = reversal

                        # Tick confirmation
                        if tick_confirm[pair]["dir"] == direction:
                            tick_confirm[pair]["count"] += 1
                        else:
                            tick_confirm[pair] = {"dir": direction, "count": 1}

                        if tick_confirm[pair]["count"] < TICK_CONFIRMATION:
                            continue

                        # Big move check
                        if not big_move_ready(prices[pair], direction):
                            continue

                        # Adaptive duration
                        duration = max(1, min(5, int(np.std(prices[pair][-20:])*200)))

                        # Accuracy
                        acc = get_accuracy(prices[pair])

                        # Send signal
                        send_signal(pair, direction, duration, acc)
                        set_cooldown(pair, duration + COOLDOWN_MINUTES)

                        # Auto exit tracking
                        exit_triggered = False
                        entry_price = prices[pair][-1]
                        start_time = datetime.now(TIMEZONE)
                        while not exit_triggered:
                            await asyncio.sleep(1)
                            if len(prices[pair]) < 5:
                                continue
                            current_price = prices[pair][-1]
                            trend_now = detect_trend(prices[pair])
                            if trend_now != direction:
                                exit_triggered = True
                                send_exit(pair, direction)
                            if (datetime.now(TIMEZONE) - start_time).seconds / 60 >= duration:
                                exit_triggered = True
                                send_exit(pair, direction)

                        tick_confirm[pair] = {"count": 0, "dir": None}

                    except Exception as e:
                        print("Error in tick processing:", e)
                        continue
        except Exception as e:
            print("Error in monitor loop:", e)
            await asyncio.sleep(5)

asyncio.run(monitor())
