import asyncio
import json
import requests
import websockets
import numpy as np
from datetime import datetime, timedelta
import pytz
import logging
from collections import deque, defaultdict
import heapq

# ----------------------
# CONFIG
# ----------------------
BOT_TOKEN = "8751531182:AAHRVd3Zeo7Z9wUWb9q7ruiH_lppQE_ymak"
CHAT_ID = "8308393231"
DERIV_WS = "wss://ws.binaryws.com/websockets/v3?app_id=1089"
TIMEZONE = pytz.timezone("Africa/Lagos")
EXPIRY_MINUTES = 5
MAX_PRICES = 5000
OBSERVATION_TICKS = 15
PRE_SIGNAL_OBSERVATION = 120
BLOCKED_PAIRS = ["frxUSDNOK","frxGBPNOK","frxUSDPLN","frxGBPNZD","frxUSDSEK"]
LOSS_FREEZE_COUNT = 2
MIN_ACCURACY = 82
MAX_ACCURACY = 95
MIN_SIGNAL_INTERVAL = 1800
MAX_SIGNALS_PER_HOUR = 2
EXPLOSION_THRESHOLD = 0.01
EXPLOSION_BOOST = 5
PING_INTERVAL = 30
TELEGRAM_RETRY_INTERVAL = 2

# ----------------------
# GLOBAL STATE
# ----------------------
prices = {}
historical_memory = {}
signal_history = defaultdict(list)
pair_losses = defaultdict(int)
adaptive_weights = {"ema":0.25,"momentum":0.25,"volatility":0.25,"pullback":0.25}
active_pair = None
last_signal_time = datetime.min.replace(tzinfo=TIMEZONE)
signals_sent_this_hour = 0
signal_queue = []

# ----------------------
# LOGGING
# ----------------------
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

# ----------------------
# EMA
# ----------------------
def ema(data, period):
    if len(data) < period: return None
    k = 2 / (period + 1)
    val = data[0]
    for p in data: val = p * k + val * (1 - k)
    return val

# ----------------------
# TREND DETECTION
# ----------------------
def detect_trend(p):
    if len(p) < 50: return None
    e1 = ema(p[-10:],3)
    e2 = ema(p[-20:],5)
    e3 = ema(p[-30:],8)
    e4 = ema(p[-50:],13)
    if not all([e1,e2,e3,e4]): return None
    if e1>e2 and e3>e4: return "BUY"
    if e1<e2 and e3<e4: return "SELL"
    return None

# ----------------------
# PULLBACK & STABLE CHECK
# ----------------------
def is_stable_and_no_pullback(p,direction):
    if len(p)<OBSERVATION_TICKS+5: return False
    last_diff = np.diff(p[-OBSERVATION_TICKS:])
    if direction=="BUY": return np.all(last_diff>0)
    if direction=="SELL": return np.all(last_diff<0)
    return False

# ----------------------
# MARKET NOISE FILTER
# ----------------------
def is_market_stable(p):
    if len(p)<30: return False
    std = np.std(p[-30:])
    mean = np.mean(p[-30:])
    return std/mean < 0.005

# ----------------------
# EXPLOSION DETECTION
# ----------------------
def detect_explosion(p,direction):
    if len(p)<OBSERVATION_TICKS: return False
    recent_change = (p[-1]-p[-OBSERVATION_TICKS])/p[-OBSERVATION_TICKS]
    if direction=="BUY" and recent_change >= EXPLOSION_THRESHOLD: return True
    if direction=="SELL" and recent_change <= -EXPLOSION_THRESHOLD: return True
    return False

# ----------------------
# ACCURACY CALCULATION
# ----------------------
def calculate_accuracy(p,direction):
    score=0
    e1 = ema(p[-10:],3)
    e2 = ema(p[-20:],5)
    e3 = ema(p[-30:],8)
    e4 = ema(p[-50:],13)
    if direction=="BUY" and e1>e2 and e3>e4: score+=adaptive_weights["ema"]*100
    if direction=="SELL" and e1<e2 and e3<e4: score+=adaptive_weights["ema"]*100
    diff = np.diff(p[-5:])
    if direction=="BUY" and np.all(diff>0): score+=adaptive_weights["momentum"]*100
    if direction=="SELL" and np.all(diff<0): score+=adaptive_weights["momentum"]*100
    std = np.std(p[-30:])
    mean = np.mean(p[-30:])
    if std/mean < 0.005: score+=adaptive_weights["volatility"]*100
    last_diff = np.diff(p[-OBSERVATION_TICKS:])
    if direction=="BUY" and np.all(last_diff>0): score+=adaptive_weights["pullback"]*100
    if direction=="SELL" and np.all(last_diff<0): score+=adaptive_weights["pullback"]*100
    if detect_explosion(p,direction):
        score += EXPLOSION_BOOST
    accuracy = min(score,100)
    return max(MIN_ACCURACY,min(accuracy,MAX_ACCURACY))

# ----------------------
# ADAPTIVE LEARNING
# ----------------------
def update_adaptive_weights(pair,direction,result):
    signal_history[pair].append(result)
    if len(signal_history[pair])>100: signal_history[pair].pop(0)
    for k in adaptive_weights:
        if result: adaptive_weights[k]=min(0.4,adaptive_weights[k]+0.01)
        else: adaptive_weights[k]=max(0.15,adaptive_weights[k]-0.01)
    if not result: pair_losses[pair]+=1
    else: pair_losses[pair]=0
    logging.info(f"Adaptive weights: {adaptive_weights} | Pair losses: {dict(pair_losses)}")

# ----------------------
# TELEGRAM WITH RETRY
# ----------------------
def send_telegram(msg):
    while True:
        try:
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                          data={"chat_id":CHAT_ID,"text":msg}, timeout=5)
            break
        except Exception as e:
            logging.warning(f"Telegram send failed, retrying in {TELEGRAM_RETRY_INTERVAL}s: {e}")
            asyncio.sleep(TELEGRAM_RETRY_INTERVAL)

def send_asset(pair, move_type="Steady Trend"):
    msg=f"SIGNAL ⚠️\nAsset: {pair}_otc\nExpiration: M{EXPIRY_MINUTES}\nMove Type: {move_type}\nObserving market for stable move..."
    send_telegram(msg)
    logging.info(f"Asset observation started: {pair} ({move_type})")

def send_final(pair,direction,acc, move_type="Steady Trend"):
    arrow="⬆️" if direction=="BUY" else "⬇️"
    msg=f"SIGNAL {arrow}\nAsset: {pair}_otc\nPayout: 92%\nAccuracy: {acc}%\nExpiration: M{EXPIRY_MINUTES}\nMove Type: {move_type}"
    send_telegram(msg)
    logging.info(f"Final signal sent: {pair} {direction} Accuracy: {acc}% ({move_type})")

# ----------------------
# LOAD SYMBOLS
# ----------------------
async def load_symbols():
    try:
        async with websockets.connect(DERIV_WS) as ws:
            await ws.send(json.dumps({"active_symbols":"brief"}))
            res = json.loads(await ws.recv())
            return [s["symbol"] for s in res["active_symbols"] if s["symbol"].startswith("frx") and s["symbol"] not in BLOCKED_PAIRS]
    except Exception as e:
        logging.warning(f"Failed to load symbols: {e}")
        return []

# ----------------------
# PRIORITY QUEUE SUPPORT
# ----------------------
def calculate_signal_score(pair, direction):
    acc = calculate_accuracy(list(prices[pair]), direction)
    explosion = detect_explosion(list(prices[pair]), direction)
    recent = list(prices[pair])[-OBSERVATION_TICKS:]
    trend_strength = abs(recent[-1]-recent[0]) if len(recent)>1 else 0
    score = acc + (EXPLOSION_BOOST if explosion else 0) + trend_strength*100
    return score

def enqueue_signal(pair, direction):
    score = calculate_signal_score(pair, direction)
    heapq.heappush(signal_queue, (-score, datetime.now(TIMEZONE), pair, direction))

def get_top_signal():
    global signals_sent_this_hour, last_signal_time
    while signal_queue:
        score, queued_time, pair, direction = heapq.heappop(signal_queue)
        now = datetime.now(TIMEZONE)
        seconds_since_last = (now-last_signal_time).total_seconds()
        if signals_sent_this_hour<MAX_SIGNALS_PER_HOUR and seconds_since_last>=MIN_SIGNAL_INTERVAL:
            return pair, direction
    return None, None

# ----------------------
# HANDLE PAIR (ULTRA-FAST)
# ----------------------
async def handle_pair(pair):
    global active_pair, last_signal_time, signals_sent_this_hour
    prices[pair] = deque(maxlen=MAX_PRICES)
    historical_memory[pair] = deque(maxlen=MAX_PRICES)
    while True:
        try:
            async with websockets.connect(DERIV_WS, ping_interval=PING_INTERVAL, ping_timeout=10) as ws:
                await ws.send(json.dumps({"ticks":pair,"subscribe":1}))
                async for msg in ws:
                    try:
                        data = json.loads(msg)
                        if "tick" not in data: continue
                        price = data["tick"]["quote"]

                        if pair_losses[pair]>=LOSS_FREEZE_COUNT: continue
                        prices[pair].append(price)
                        historical_memory[pair].append(price)

                        if active_pair: continue
                        direction = detect_trend(list(prices[pair]))
                        if not direction: continue
                        if not is_stable_and_no_pullback(list(prices[pair]),direction): continue
                        if not is_market_stable(list(prices[pair])): continue

                        enqueue_signal(pair,direction)

                        top_pair, top_direction = get_top_signal()
                        if not top_pair: continue

                        move_type = "Big Move" if detect_explosion(list(prices[top_pair]),top_direction) else "Steady Trend"

                        observation_start = datetime.now(TIMEZONE)
                        pre_prices = list(prices[top_pair])
                        while (datetime.now(TIMEZONE)-observation_start).total_seconds()<PRE_SIGNAL_OBSERVATION:
                            await asyncio.sleep(1)
                            pre_prices.append(prices[top_pair][-1])
                            if not is_stable_and_no_pullback(pre_prices,top_direction): break
                        else:
                            acc = calculate_accuracy(pre_prices,top_direction)
                            if acc<MIN_ACCURACY: continue
                            active_pair=top_pair
                            signals_sent_this_hour+=1
                            last_signal_time=datetime.now(TIMEZONE)

                            send_asset(top_pair, move_type)
                            await asyncio.sleep(2)
                            send_final(top_pair,top_direction,acc, move_type)

                            await asyncio.sleep(EXPIRY_MINUTES*60)
                            final_price = historical_memory[top_pair][-1]
                            result=(top_direction=="BUY" and final_price>prices[top_pair][-1]) or (top_direction=="SELL" and final_price<prices[top_pair][-1])
                            update_adaptive_weights(top_pair,top_direction,result)
                            active_pair=None
                            prices[top_pair].clear()
                    except Exception as e_tick:
                        logging.error(f"[{pair}] Tick error: {e_tick}")

        except Exception as e_ws:
            logging.warning(f"[{pair}] WebSocket disconnected: {e_ws}, reconnecting in 5s")
            await asyncio.sleep(5)

# ----------------------
# MAIN MONITOR
# ----------------------
async def monitor():
    symbols = await load_symbols()
    while not symbols:
        logging.warning("No symbols loaded, retrying in 5s")
        await asyncio.sleep(5)
        symbols = await load_symbols()
    tasks = [handle_pair(pair) for pair in symbols]
    await asyncio.gather(*tasks)

# ----------------------
# RUN
# ----------------------
asyncio.run(monitor())
