# ======================================
# FINAL SINGLE DEPLOY AI SIGNAL SYSTEM
# REAL MARKET • NO PLACEHOLDER • 2M LOGIC
# ======================================

import asyncio
import json
import requests
import websockets
import numpy as np
from datetime import datetime, timedelta
import pytz
from river import linear_model, preprocessing

# ---------------- CONFIG ----------------

BOT_TOKEN = "8751531182:AAHRVd3Zeo7Z9wUWb9q7ruiH_lppQE_ymak"
CHAT_ID = "8308393231"

DERIV_WS = "wss://ws.binaryws.com/websockets/v3?app_id=1089"
TIMEZONE = pytz.timezone("Africa/Lagos")

TICK_CONFIRM = 3
CONFIDENCE_THRESHOLD = 78
MAX_VOL = 0.006
MIN_VOL = 0.001

# 2 MINUTE STRUCTURE
ENTRY_DELAY = 120
MG1_DELAY = 120
MG2_DELAY = 120
MG3_DELAY = 120

# ---------------- GLOBALS ----------------

prices = {}
confirm = {}
global_lock = False

# ---------------- MODEL ----------------

model = preprocessing.StandardScaler() | linear_model.LogisticRegression()

# initialize (avoid 50%)
model.learn_one({"r":0,"v":0,"m":0,"t":0}, 1)

# ---------------- FEATURES ----------------

def features(p):
    if len(p) < 30:
        return None
    return {
        "r": (p[-1] - p[-2]) / p[-2],
        "v": np.std(p[-20:]),
        "m": np.sum(np.diff(p[-10:])),
        "t": p[-1] - np.mean(p[-20:])
    }

# ---------------- PREDICTION ----------------

def predict(p):
    f = features(p)
    if not f:
        return None, None

    prob = model.predict_proba_one(f).get(1, 0) * 100
    prob = min(max(prob, 1), 99)

    direction = "BUY" if prob >= 50 else "SELL"
    return prob, direction

# ---------------- FILTER ----------------

def market_ok(p):
    if len(p) < 20:
        return False
    vol = np.std(p[-20:])
    return MIN_VOL < vol < MAX_VOL

# ---------------- TELEGRAM ----------------

def send_signal(pair, direction):
    now = datetime.now(TIMEZONE)

    entry_time = now + timedelta(seconds=ENTRY_DELAY)
    mg1 = entry_time + timedelta(seconds=MG1_DELAY)
    mg2 = mg1 + timedelta(seconds=MG2_DELAY)
    mg3 = mg2 + timedelta(seconds=MG3_DELAY)

    msg = f"""🚨 TRADE SETUP

📊 {pair}
📈 Direction: {direction}

⏰ Expiry: 2 minutes

📍 Entry Time: {entry_time.strftime('%I:%M:%S %p')}

🎯 Martingale:
1️⃣ {mg1.strftime('%I:%M:%S %p')}
2️⃣ {mg2.strftime('%I:%M:%S %p')}
3️⃣ {mg3.strftime('%I:%M:%S %p')}
"""

    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                  data={"chat_id": CHAT_ID, "text": msg})

    return mg3

# ---------------- TRAIN ----------------

def train(pair, entry_price, direction):
    f = features(prices[pair])
    if not f:
        return

    current = prices[pair][-1]

    if direction == "BUY":
        y = 1 if current > entry_price else 0
    else:
        y = 1 if current < entry_price else 0

    model.learn_one(f, y)

# ---------------- MAIN ----------------

async def run():
    global global_lock

    async with websockets.connect(DERIV_WS) as ws:

        await ws.send(json.dumps({"active_symbols": "brief"}))
        res = json.loads(await ws.recv())
        symbols = [s["symbol"] for s in res["active_symbols"] if s["symbol"].startswith("frx")]

        for s in symbols:
            prices[s] = []
            confirm[s] = {"dir": None, "count": 0}

        for s in symbols:
            await ws.send(json.dumps({"ticks": s, "subscribe": 1}))

        async for msg in ws:
            data = json.loads(msg)

            if "tick" not in data:
                continue

            pair = data["tick"]["symbol"]
            price = data["tick"]["quote"]

            prices[pair].append(price)
            if len(prices[pair]) > 200:
                prices[pair].pop(0)

            if global_lock:
                continue

            if not market_ok(prices[pair]):
                continue

            prob, direction = predict(prices[pair])
            if prob is None or prob < CONFIDENCE_THRESHOLD:
                continue

            # confirmation
            if confirm[pair]["dir"] == direction:
                confirm[pair]["count"] += 1
            else:
                confirm[pair] = {"dir": direction, "count": 1}

            if confirm[pair]["count"] < TICK_CONFIRM:
                continue

            entry_price = prices[pair][-1]

            # SEND SIGNAL
            last_time = send_signal(pair, direction)

            global_lock = True

            # WAIT FULL CYCLE (ENTRY + MG1 + MG2 + MG3)
            delay = (last_time - datetime.now(TIMEZONE)).total_seconds()
            await asyncio.sleep(max(0, delay))

            # TRAIN AFTER FULL CYCLE
            train(pair, entry_price, direction)

            global_lock = False


# ---------------- RUN ----------------

asyncio.run(run())
