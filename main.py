import asyncio
import json
import websockets
import numpy as np
from datetime import datetime, timedelta
import pytz
from telegram import Bot

# =====================
# CONFIG
# =====================
BOT_TOKEN = "8581515208:AAFWsel7xveab0iMmDE3NJ_5Ow3I4uaSvQo"
CHAT_ID = "8308393231"

DERIV_WS = "wss://ws.binaryws.com/websockets/v3?app_id=1089"
TIMEZONE = pytz.timezone("Africa/Lagos")

# Popular OTC currency pairs (50) + 7 major crypto pairs
SYMBOLS = [
    "OTC_EURUSD","OTC_GBPUSD","OTC_USDJPY","OTC_USDCAD","OTC_AUDUSD",
    "OTC_NZDUSD","OTC_USDCHF","OTC_EURGBP","OTC_EURAUD","OTC_EURNZD",
    "OTC_EURJPY","OTC_GBPJPY","OTC_GBPCHF","OTC_GBPCAD","OTC_GBPAUD",
    "OTC_GBPNZD","OTC_AUDJPY","OTC_AUDNZD","OTC_AUDCAD","OTC_AUDCHF",
    "OTC_NZDJPY","OTC_NZDCHF","OTC_NZDCAD","OTC_CADJPY",
    "OTC_USDMXN","OTC_EURCHF","OTC_EURCAD",
    "OTC_EURAED","OTC_GBPAED",
    "CRYPTO:BTCUSD","CRYPTO:ETHUSD","CRYPTO:XRPUSD","CRYPTO:LTCUSD",
    "CRYPTO:BCHUSD","CRYPTO:ADAUSD","CRYPTO:DOGEUSD"
]

bot = Bot(token=BOT_TOKEN)
price_data = {}
trade_active = False
last_signal_time = None

# =====================
# FORMAT SIGNAL
# =====================
def format_signal(symbol, direction):
    now = datetime.now(TIMEZONE)
    entry = now + timedelta(minutes=2)
    mg1 = entry + timedelta(minutes=2)
    mg2 = entry + timedelta(minutes=4)
    mg3 = entry + timedelta(minutes=6)

    symbol_clean = symbol.replace("OTC_", "").replace("_", "/").replace("CRYPTO:", "")
    emoji = "🟩" if direction == "BUY" else "🟥"

    return f"""
🚨TRADE NOW!!

📉 {symbol_clean} 
⏰ Expiry: 2 minutes
📍 Entry Time: {entry.strftime('%I:%M %p')}
📈 Direction: {direction} {emoji}

🎯 Martingale Levels:
🔁 Level 1 → {mg1.strftime('%I:%M %p')}
🔁 Level 2 → {mg2.strftime('%I:%M %p')}
🔁 Level 3 → {mg3.strftime('%I:%M %p')}
"""

# =====================
# ADVANCED LOGIC
# =====================
def analyze_ticks(ticks):
    if len(ticks) < 30:
        return None

    data = np.array(ticks[-30:])
    returns = np.diff(data)
    momentum = np.sum(returns)
    last_move = returns[-1]
    volatility = np.std(data)

    # Skip if market is too flat
    if volatility < 0.00005:
        return None

    short_ma = np.mean(data[-5:])
    long_ma = np.mean(data[-20:])

    if short_ma > long_ma and momentum > 0 and last_move > 0:
        return "BUY"
    if short_ma < long_ma and momentum < 0 and last_move < 0:
        return "SELL"

    return None

# =====================
# SPIKE FILTER
# =====================
SPIKE_THRESHOLD = 0.005  # 0.5% price spike threshold

def check_spike(ticks):
    if len(ticks) < 10:
        return True
    recent_avg = np.mean(ticks[-10:])
    last_tick = ticks[-1]
    if abs(last_tick - recent_avg) / recent_avg > SPIKE_THRESHOLD:
        return False
    return True

# =====================
# MAIN LOOP
# =====================
async def run_bot():
    global trade_active, last_signal_time

    async with websockets.connect(DERIV_WS) as ws:
        # Subscribe to all symbols
        for sym in SYMBOLS:
            await ws.send(json.dumps({"ticks": sym, "subscribe": 1}))
            price_data[sym] = []

        while True:
            msg = await ws.recv()
            data = json.loads(msg)
            if "tick" not in data:
                continue

            sym = data["tick"]["symbol"]
            price = data["tick"]["quote"]

            price_data[sym].append(price)
            if len(price_data[sym]) > 60:
                price_data[sym].pop(0)

            # Wait for previous signal expiry
            if trade_active:
                continue

            direction = analyze_ticks(price_data[sym])

            if direction:
                if not check_spike(price_data[sym]):
                    continue

                now = datetime.now(TIMEZONE)
                if last_signal_time and (now - last_signal_time).seconds < 180:
                    continue

                signal = format_signal(sym, direction)
                await bot.send_message(chat_id=CHAT_ID, text=signal)
                print(f"SIGNAL: {sym} {direction}")

                trade_active = True
                last_signal_time = now
                # Wait full expiry + martingale time
                await asyncio.sleep(480)
                trade_active = False

# =====================
# START BOT
# =====================
if __name__ == "__main__":
    print("Bot running...")
    asyncio.run(run_bot())
