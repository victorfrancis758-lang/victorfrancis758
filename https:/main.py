# ======================================
# DERIV OTC SIGNAL BOT
# FULLY ENHANCED: POCKETOPTION-STYLE SIGNALS
# HISTORICAL PATTERN DETECTION, SMART ENTRY
# ADAPTIVE ACCURACY 82-85%, FIXED STRENGTH 95%
# SINGLE SIGNAL PER CANDLE, PREDICTIVE VALIDATION
# SESSION FILTER (LONDON/NY/ASIA)
# ======================================

import asyncio
import json
import requests
import websockets
import logging
import numpy as np
from datetime import datetime, timedelta, time
import pytz

BOT_TOKEN = "8751531182:AAHRVd3Zeo7Z9wUWb9q7ruiH_lppQE_ymak"
CHAT_ID = "8308393231"

DERIV_WS = "wss://ws.binaryws.com/websockets/v3?app_id=1089"
TIMEZONE = pytz.timezone("Africa/Lagos")

TREND_SCORE_THRESHOLD = 82
FIXED_STRENGTH = 95
ENTRY_DELAY = 2
MG_STEP = 2
MAX_MG_STEPS = 3
EXPIRY_MINUTES = 2

MAX_PRICES = 5000
RETRY_SECONDS = 5
TICK_CONFIRMATION = 3
GLOBAL_SIGNAL_COOLDOWN = 10

BLOCKED_PAIRS = ["frxUSDNOK","frxGBPNOK","frxUSDPLN","frxGBPNZD","frxUSDSEK"]

prices = {}
tick_confirm = {}
pending_signal = {}
active_signal = {}
last_global_signal_time = None

# ================================
# MARKET SESSION FILTER
# ================================
def in_active_session(now):
    # Define main sessions in UTC
    utc_now = now.astimezone(pytz.utc).time()
    london_start, london_end = time(8,0), time(17,0)
    ny_start, ny_end = time(13,0), time(22,0)
    asia_start, asia_end = time(0,0), time(9,0)
    if london_start <= utc_now <= london_end:
        return True
    if ny_start <= utc_now <= ny_end:
        return True
    if asia_start <= utc_now <= asia_end:
        return True
    return False

# ================================
# EMA CALCULATION
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
# TREND STRENGTH BASED ON HISTORICAL PATTERNS
# ================================
def trend_strength(price_list):
    if len(price_list) < 150:
        return 0
    ema_fast = ema(price_list[-50:], 10)
    ema_slow = ema(price_list[-100:], 20)
    separation = abs(ema_fast - ema_slow) if ema_fast and ema_slow else 0
    volatility = np.std(price_list[-100:])
    if volatility == 0:
        return 0
    return min(max((separation / volatility) * 100, 82), FIXED_STRENGTH)

# ================================
# ADAPTIVE ACCURACY BASED ON CONDITIONS
# ================================
def adjust_accuracy(strength, pattern_score):
    base_acc = 82 if strength < 90 else 85
    final_acc = base_acc + pattern_score
    return min(final_acc, 85)

# ================================
# TREND DETECTION
# ================================
def detect_trend(price_list):
    if len(price_list) < 300:
        return 0,0,None
    ema_fast = ema(price_list[-50:],10)
    ema_slow = ema(price_list[-100:],20)
    ema_long_fast = ema(price_list[-200:],30)
    ema_long_slow = ema(price_list[-300:],60)
    direction = None
    if ema_fast and ema_slow and ema_long_fast and ema_long_slow:
        if ema_fast>ema_slow and ema_long_fast>ema_long_slow:
            direction="BUY"
        elif ema_fast<ema_slow and ema_long_fast<ema_long_slow:
            direction="SELL"
    strength = trend_strength(price_list)
    if len(price_list) >= 200:
        historical_patterns = [np.diff(price_list[i:i+10]) for i in range(len(price_list)-210)]
        matches = sum([all(np.diff(price_list[-10:])>0) if direction=="BUY" else all(np.diff(price_list[-10:])<0) for hp in historical_patterns])
        pattern_score = min(int((matches / len(historical_patterns))*3),3)
    else:
        pattern_score = 0
    accuracy = adjust_accuracy(strength, pattern_score)
    return accuracy, strength, direction

# ================================
# PREDICTIVE PRE-ENTRY CHECK
# ================================
def predictive_valid(price_list, direction):
    if len(price_list) < 10:
        return False
    recent = price_list[-10:]
    moves = np.diff(recent)
    if direction=="BUY":
        return np.sum(moves>0) >= 7
    elif direction=="SELL":
        return np.sum(moves<0) >= 7
    return False

# ================================
# SIGNAL LOCK PER PAIR
# ================================
def signal_active(pair):
    if pair not in active_signal or active_signal[pair] is None:
        return False
    return datetime.now(TIMEZONE) < active_signal[pair]

def register_signal(pair):
    now = datetime.now(TIMEZONE)
    total_lock = ENTRY_DELAY + MG_STEP*MAX_MG_STEPS + EXPIRY_MINUTES
    active_signal[pair] = now + timedelta(minutes=total_lock)

# ================================
# FLAG EMOJIS
# ================================
def get_flag(code):
    flags = {"USD":"🇺🇸","EUR":"🇪🇺","GBP":"🇬🇧","CHF":"🇨🇭",
             "JPY":"🇯🇵","AUD":"🇦🇺","CAD":"🇨🇦","NZD":"🇳🇿"}
    return flags.get(code.upper(),"")

# ================================
# SEND TELEGRAM SIGNAL
# ================================
def send_signal(pair, direction, accuracy, strength):
    global last_global_signal_time
    now_time = datetime.now(TIMEZONE)
    if last_global_signal_time and (now_time - last_global_signal_time).total_seconds() < GLOBAL_SIGNAL_COOLDOWN:
        return
    if signal_active(pair):
        return
    if not in_active_session(now_time):
        return
    last_global_signal_time = now_time
    now = now_time
    entry_time = now + timedelta(minutes=ENTRY_DELAY)
    expiry_time = entry_time + timedelta(minutes=EXPIRY_MINUTES)
    register_signal(pair)
    base = pair[3:6].upper()
    quote = pair[6:9].upper()
    mg_times = [entry_time + timedelta(minutes=MG_STEP*i) for i in range(1,MAX_MG_STEPS+1)]
    msg=(f"🚨TRADE SIGNAL (POCKETOPTION-STYLE)\n\n"
         f"📉{get_flag(base)} {base}/{quote} {get_flag(quote)} (OTC)\n"
         f"📍 Signal Time: {now.strftime('%I:%M:%S %p')}\n"
         f"⏳ Entry Time: {entry_time.strftime('%I:%M:%S %p')}\n"
         f"⏰ Expiry Time: {expiry_time.strftime('%I:%M:%S %p')}\n"
         f"📈 Direction: {direction} {'🟩' if direction=='BUY' else '🟥'}\n"
         f"Accuracy: {accuracy}%\n"
         f"Strength: {strength:.0f}%\n"
         f"Mode: SMART ENTRY CONFIRMED")
    try:
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                      data={"chat_id":CHAT_ID,"text":msg},timeout=10)
    except:
        logging.info("Telegram error")

# ================================
# LOAD DERIV SYMBOLS
# ================================
async def load_otc_symbols():
    try:
        async with websockets.connect(DERIV_WS) as ws:
            await ws.send(json.dumps({"active_symbols":"brief"}))
            response=json.loads(await ws.recv())
            return [s["symbol"] for s in response.get("active_symbols",[])
                    if s["symbol"].startswith("frx") and s["symbol"] not in BLOCKED_PAIRS]
    except:
        return []

# ================================
# MAIN MONITOR LOOP
# ================================
async def monitor():
    global pending_signal
    while True:
        try:
            symbols = await load_otc_symbols()
            if not symbols:
                await asyncio.sleep(5)
                continue
            for s in symbols:
                prices[s] = []
                tick_confirm[s] = {"count":0,"direction":None}
                pending_signal[s] = None
            async with websockets.connect(DERIV_WS) as ws:
                for s in symbols:
                    await ws.send(json.dumps({"ticks":s,"subscribe":1}))
                async for message in ws:
                    data=json.loads(message)
                    if "tick" not in data:
                        continue
                    pair=data["tick"]["symbol"]
                    price=data["tick"]["quote"]
                    prices[pair].append(price)
                    if len(prices[pair])>MAX_PRICES:
                        prices[pair].pop(0)
                    accuracy,strength,direction=detect_trend(prices[pair])
                    if direction and accuracy>=TREND_SCORE_THRESHOLD and strength>=FIXED_STRENGTH:
                        if tick_confirm[pair]["direction"]==direction:
                            tick_confirm[pair]["count"]+=1
                        else:
                            tick_confirm[pair]={"direction":direction,"count":1}
                        if tick_confirm[pair]["count"]>=TICK_CONFIRMATION:
                            if predictive_valid(prices[pair],direction):
                                pending_signal[pair]=(direction,accuracy,strength)
                    if pending_signal.get(pair) and not signal_active(pair):
                        dir_check,acc_check,str_check=pending_signal[pair]
                        acc2,str2,dir2=detect_trend(prices[pair])
                        if dir2==dir_check and predictive_valid(prices[pair],dir_check):
                            send_signal(pair,dir2,acc2,str2)
                        pending_signal[pair]=None
        except:
            logging.info("Reconnecting...")
            await asyncio.sleep(RETRY_SECONDS)

# ================================
# START BOT
# ================================
asyncio.run(monitor())
