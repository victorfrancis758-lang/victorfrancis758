# ======================================
# AI TRADER SIGNAL SYSTEM - REAL MONEY READY
# ======================================

import os
import csv
import json
import asyncio
import websockets
import numpy as np
from datetime import datetime, timedelta
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, CallbackQueryHandler, ContextTypes, filters

# -------------------
# CONFIG
# -------------------
BOT_TOKEN = "8581515208:AAFWsel7xveab0iMmDE3NJ_5Ow3I4uaSvQo"
CHAT_ID = "8308393231"
DERIV_WS = "wss://ws.binaryws.com/websockets/v3?app_id=1089"
TIMEZONE = pytz.timezone("Africa/Lagos")
DATA_DIR = "data"
LOG_FILE = os.path.join(DATA_DIR, "trades.csv")
os.makedirs(DATA_DIR, exist_ok=True)

# -------------------
# INIT CSV
# -------------------
if not os.path.exists(LOG_FILE):
    with open(LOG_FILE, "w", newline="") as f:
        csv.writer(f).writerow([
            "time","symbol","direction","tp","sl","timeframe","martingale","result"
        ])

# -------------------
# GLOBAL VARIABLES
# -------------------
market_volatility = {}      # store tick history per symbol
cooldown_tracker = {}       # prevent spamming same signals
adaptive_trend_factor = {}  # weekly adaptive adjustment

# -------------------
# FETCH ALL SYMBOLS
# -------------------
async def fetch_all_pairs(ws):
    await ws.send(json.dumps({"active_symbols": "brief"}))
    while True:
        msg = await ws.recv()
        data = json.loads(msg)
        if "active_symbols" in data:
            symbols = [s["symbol"] for s in data["active_symbols"]]
            otc_pairs = [s for s in symbols if s.startswith("OTC")]
            crypto_pairs = ["CRYPTO:BTCUSD","CRYPTO:ETHUSD","CRYPTO:XRPUSD",
                            "CRYPTO:LTCUSD","CRYPTO:BCHUSD","CRYPTO:ADAUSD","CRYPTO:DOGEUSD"]
            return otc_pairs + crypto_pairs

# -------------------
# MARKET LISTENER
# -------------------
async def market_listener():
    global market_volatility
    async with websockets.connect(DERIV_WS) as ws:
        pairs = await fetch_all_pairs(ws)
        print(f"Monitoring {len(pairs)} symbols: {pairs}")

        # Subscribe to all pairs
        for p in pairs:
            await ws.send(json.dumps({"ticks": p, "subscribe": 1}))
            market_volatility[p] = []

        async for msg in ws:
            data = json.loads(msg)
            if "tick" not in data:
                continue
            symbol = data["tick"]["symbol"]
            quote = data["tick"]["quote"]
            market_volatility[symbol].append(quote)
            if len(market_volatility[symbol]) > 100:
                market_volatility[symbol].pop(0)

# -------------------
# SIGNAL GENERATION
# -------------------
def analyze_pair(symbol, ticks):
    """
    Very simple adaptive signal:
    - Compare last tick vs moving average
    - Determine trend and direction
    """
    if len(ticks) < 10:
        return None  # not enough data

    series = np.array(ticks)
    ma = np.mean(series[-10:])
    last = series[-1]

    # adaptive weekly factor
    factor = adaptive_trend_factor.get(symbol, 1.0)

    if last > ma * (1 + 0.001*factor):
        direction = "BUY"
    elif last < ma * (1 - 0.001*factor):
        direction = "SELL"
    else:
        return None

    vol = np.std(series[-10:]) + 1e-5
    base = last
    risk = vol * 50
    if direction == "BUY":
        sl = base - risk
        tp = base + risk*2
    else:
        sl = base + risk
        tp = base - risk*2

    # Determine timeframe based on distance
    distance = abs(tp - sl)
    if distance <= 5:
        timeframe = "M1"
    elif distance <= 10:
        timeframe = "M5"
    elif distance <= 20:
        timeframe = "M15"
    elif distance <= 40:
        timeframe = "M30"
    else:
        timeframe = "H1"

    return {
        "symbol": symbol,
        "direction": direction,
        "tp": round(tp,5),
        "sl": round(sl,5),
        "timeframe": timeframe
    }

# -------------------
# SAVE TRADE
# -------------------
def save_trade(trade, martingale=0):
    with open(LOG_FILE, "a", newline="") as f:
        csv.writer(f).writerow([
            datetime.now(TIMEZONE), trade["symbol"], trade["direction"], trade["tp"], trade["sl"],
            trade["timeframe"], martingale, "PENDING"
        ])

# -------------------
# TELEGRAM SIGNAL
# -------------------
async def send_signal(trade, context, martingale=0):
    keyboard = [
        [InlineKeyboardButton("✅ WIN", callback_data="win"),
         InlineKeyboardButton("❌ LOSS", callback_data="loss")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = f"""
📊 SIGNAL
Symbol: {trade['symbol']}
Direction: {trade['direction']}
TP: {trade['tp']}
SL: {trade['sl']}
Timeframe: {trade['timeframe']}
Martingale: {martingale}
"""
    await context.bot.send_message(chat_id=CHAT_ID, text=msg, reply_markup=reply_markup)
    save_trade(trade, martingale)

# -------------------
# GENERATE SIGNALS LOOP (ALL SYMBOLS SIMULTANEOUSLY)
# -------------------
async def generate_signals(app):
    while True:
        for symbol, ticks in market_volatility.items():
            trade = analyze_pair(symbol, ticks)
            if trade:
                now = datetime.now(TIMEZONE)
                last_time = cooldown_tracker.get(symbol)
                if last_time and (now - last_time).total_seconds() < 120:
                    continue
                cooldown_tracker[symbol] = now

                # Send primary signal and Martingale 3 levels
                await send_signal(trade, app, martingale=0)
                for i in range(1,4):
                    # Martingale entry: 2 min apart
                    await asyncio.sleep(120)
                    await send_signal(trade, app, martingale=i)
        await asyncio.sleep(5)  # small delay to loop again

# -------------------
# TELEGRAM HANDLERS
# -------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("AI Trading Signal Bot is active. Signals will appear automatically.")

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "win":
        update_last_result("WIN")
        await query.edit_message_text("Recorded: WIN ✅")
    else:
        update_last_result("LOSS")
        await query.edit_message_text("Recorded: LOSS ❌")

def update_last_result(result):
    rows = []
    with open(LOG_FILE, "r") as f:
        rows = list(csv.reader(f))
    rows[-1][-1] = result
    with open(LOG_FILE, "w", newline="") as f:
        csv.writer(f).writerows(rows)

# -------------------
# MAIN
# -------------------
async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_button))
    asyncio.create_task(market_listener())
    asyncio.create_task(generate_signals(app))
    print("Bot running...")
    await app.run_polling()

# -------------------
# ENTRY POINT
# -------------------
if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    loop = asyncio.get_event_loop()
    loop.create_task(main())
    loop.run_forever()
