# ======================================
# DERIV AI SIGNAL BOT - FULL ADAPTIVE SYSTEM
# REAL MARKET + SELF-LEARNING + STABLE
# ======================================

import asyncio
import json
import requests
import websockets
import numpy as np
from datetime import datetime, timedelta
import pytz
import csv
import os
from sklearn.linear_model import SGDClassifier
from sklearn.preprocessing import StandardScaler

# ---------------- CONFIG ----------------
BOT_TOKEN = "8751531182:AAHRVd3Zeo7Z9wUWb9q7ruiH_lppQE_ymak"
CHAT_ID = "8308393231"
DERIV_WS = "wss://ws.binaryws.com/websockets/v3?app_id=1089"
TIMEZONE = pytz.timezone("Africa/Lagos")

MAX_PRICES = 5000
TICK_CONFIRMATION = 3
COOLDOWN_MINUTES = 2
PROB_THRESHOLD = 70  # Minimum probability to send signal

BLOCKED_PAIRS = ["frxUSDNOK","frxGBPNOK","frxUSDPLN","frxGBPNZD","frxUSDSEK"]
TRADE_LOG = "ai_trades.csv"

# ---------------- INIT ----------------
prices = {}
tick_confirm = {}
cooldowns = {}
pending_signal = {}
features_history = []
labels_history = []

# Initialize trade log
if not os.path.exists(TRADE_LOG):
    with open(TRADE_LOG, "w", newline="") as f:
        csv.writer(f).writerow(["time","pair","dir","entry","exit","result"])

# ---------------- EMA ----------------
def ema(data, period):
    if len(data) < period:
        return None
    k = 2 / (period + 1)
    val = data[0]
    for p in data:
        val = p * k + val * (1 - k)
    return val

# ---------------- FEATURE EXTRACTION ----------------
def extract_features(p):
    if len(p) < 30:
        return None
    returns = (p[-1] - p[-2]) / p[-2]
    volatility = np.std(p[-20:])
    momentum = np.sum(np.diff(p[-10:]))
    trend_strength = abs(ema(p[-20:],5) - ema(p[-50:],13))
    return [returns, volatility, momentum, trend_strength]

# ---------------- MARKET STATE ----------------
def market_state(p):
    if len(p) < 20:
        return "UNKNOWN"
    vol = np.std(p[-20:])
    if vol < 0.001:
        return "RANGE"
    elif vol > 0.005:
        return "VOLATILE"
    return "NORMAL"

# ---------------- TELEGRAM ----------------
def notify_entry(pair, direction, prob):
    msg = f"✅ READY SIGNAL\nAsset: {pair}_otc\nDirection: {direction}\nConfidence: {prob}%"
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                  data={"chat_id": CHAT_ID, "text": msg})

def send_signal(pair, direction, prob):
    msg = f"🚀 AI SIGNAL\nAsset: {pair}_otc\nDirection: {direction}\nConfidence: {prob}%"
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                  data={"chat_id": CHAT_ID, "text": msg})

def log_trade(pair, direction, entry, exit_price):
    result = "WIN" if (
        (direction == "BUY" and exit_price > entry) or
        (direction == "SELL" and exit_price < entry)
    ) else "LOSS"
    with open(TRADE_LOG, "a", newline="") as f:
        csv.writer(f).writerow([datetime.now(TIMEZONE), pair, direction, entry, exit_price, result])
    # Add to history for self-learning
    features = extract_features(prices[pair])
    if features:
        features_history.append(features)
        labels_history.append(1 if result=="WIN" else 0)

# ---------------- MACHINE LEARNING MODEL ----------------
scaler = StandardScaler()
model = SGDClassifier(loss="log", max_iter=1000, tol=1e-3)
model_initialized = False

def predict_ai(p):
    global model_initialized
    features = extract_features(p)
    if not features:
        return 0, None
    x_scaled = scaler.transform([features]) if model_initialized else [features]
    prob = model.predict_proba(x_scaled)[0][1] if model_initialized else 50
    direction = "BUY" if prob > 0.5 else "SELL"
    return prob*100, direction

def update_model():
    global model_initialized
    if len(features_history) < 10:
        return
    X = np.array(features_history)
    y = np.array(labels_history)
    X_scaled = scaler.fit_transform(X)
    model.partial_fit(X_scaled, y, classes=[0,1])
    model_initialized = True

# ---------------- LOAD SYMBOLS ----------------
async def load_symbols():
    try:
        async with websockets.connect(DERIV_WS) as ws:
            await ws.send(json.dumps({"active_symbols": "brief"}))
            res = json.loads(await ws.recv())
            return [s["symbol"] for s in res["active_symbols"] if s["symbol"].startswith("frx") and s["symbol"] not in BLOCKED_PAIRS]
    except:
        return []

# ---------------- MAIN LOOP ----------------
async def monitor():
    while True:
        try:
            symbols = await load_symbols()
            if not symbols:
                await asyncio.sleep(5)
                continue
            for s in symbols:
                prices[s] = []
                tick_confirm[s] = {"count":0, "dir":None}
                pending_signal[s] = None
            async with websockets.connect(DERIV_WS) as ws:
                for s in symbols:
                    await ws.send(json.dumps({"ticks": s, "subscribe":1}))
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
                        print(f"[LIVE] {pair} {price}")

                        # Skip if in cooldown
                        if pair in cooldowns and datetime.now(TIMEZONE) < cooldowns[pair]:
                            continue

                        # Check market state
                        if market_state(prices[pair]) != "NORMAL":
                            continue

                        # Predict AI probability
                        prob, direction = predict_ai(prices[pair])
                        if prob < PROB_THRESHOLD:
                            continue

                        # Tick confirmation
                        if tick_confirm[pair]["dir"] == direction:
                            tick_confirm[pair]["count"] +=1
                        else:
                            tick_confirm[pair] = {"dir": direction, "count":1}
                        if tick_confirm[pair]["count"] < TICK_CONFIRMATION:
                            continue

                        # Pre-signal notification
                        notify_entry(pair, direction, prob)

                        # Send signal
                        entry_price = prices[pair][-1]
                        send_signal(pair, direction, prob)
                        cooldowns[pair] = datetime.now(TIMEZONE) + timedelta(minutes=COOLDOWN_MINUTES)

                        # Wait for signal duration and log exit
                        await asyncio.sleep(60)
                        exit_price = prices[pair][-1]
                        log_trade(pair, direction, entry_price, exit_price)

                        # Update ML model
                        update_model()

                        # Reset tick confirmation
                        tick_confirm[pair] = {"count":0, "dir":None}

                    except Exception as e:
                        print("[ERROR]", e)
        except Exception as e:
            print("[MAIN LOOP ERROR]", e)
            await asyncio.sleep(5)

asyncio.run(monitor())
