# ======================================
# AI TRADER WITH AUTOMATIC PAIRS FETCHING + CANDLESTICKS + BoS + FVG + DEMAND/SUPPLY + LEARNING
# ======================================

import os
import csv
import json
import asyncio
import websockets
import numpy as np
from datetime import datetime, timedelta
from io import BytesIO
import pytz
from PIL import Image
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
            "time","symbol","direction","tp","sl","timeframe","demand_zone","supply_zone","result"
        ])

# -------------------
# GLOBAL VARIABLES
# -------------------
market_volatility = {}
confidence_bias = {}
cooldown_tracker = {}

# -------------------
# HELPER FUNCTIONS
# -------------------
async def fetch_all_pairs(ws):
    """
    Fetch all available market symbols including OTC and top 7 crypto.
    """
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
        # Subscribe to all symbols
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
# CANDLESTICKS, BoS & FVG DETECTION
# -------------------
def detect_candles_bos_fvg(image: Image):
    img = np.array(image.convert("L"))
    series = np.mean(img, axis=0)
    series = (series - np.min(series)) / (np.max(series) - np.min(series) + 1e-9)
    trend = series[-1] - series[0]
    diff = np.diff(series)
    bos = np.any(np.abs(diff) > 0.08)
    fvg = np.any(np.abs(diff) > 0.05) and bos
    if trend > 0.05 and bos:
        direction = "BUY"
    elif trend < -0.05 and bos:
        direction = "SELL"
    else:
        direction = "NO TRADE"
    return direction, bos, fvg

# -------------------
# DEMAND/SUPPLY DETECTION
# -------------------
def detect_demand_supply(image: Image):
    img = np.array(image.convert("L"))
    series = np.mean(img, axis=0)
    series = (series - np.min(series)) / (np.max(series) - np.min(series) + 1e-9)
    demand_zone = round(np.min(series)*100,2)
    supply_zone = round(np.max(series)*100,2)
    return demand_zone, supply_zone

# -------------------
# TP/SL CALCULATION
# -------------------
def calculate_tp_sl(direction, bos, fvg, vol):
    base = 100
    risk = max(1, np.std(vol)*50 + (5 if fvg else 0))
    if direction == "BUY":
        sl = base - risk
        tp = base + risk*2
    else:
        sl = base + risk
        tp = base - risk*2
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
    return round(tp,2), round(sl,2), timeframe

# -------------------
# SAVE TRADE
# -------------------
def save_trade(symbol, direction, tp, sl, timeframe, demand_zone, supply_zone):
    with open(LOG_FILE, "a", newline="") as f:
        csv.writer(f).writerow([
            datetime.now(TIMEZONE), symbol, direction, tp, sl, timeframe, demand_zone, supply_zone, "PENDING"
        ])

# -------------------
# UPDATE RESULT
# -------------------
def update_last_result(result):
    rows = []
    with open(LOG_FILE, "r") as f:
        rows = list(csv.reader(f))
    rows[-1][-1] = result
    with open(LOG_FILE, "w", newline="") as f:
        csv.writer(f).writerows(rows)

# -------------------
# TELEGRAM HANDLERS
# -------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send your chart screenshot to analyze.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global cooldown_tracker
    photo = update.message.photo[-1]
    file = await photo.get_file()
    bio = BytesIO()
    await file.download_to_memory(bio)
    bio.seek(0)
    image = Image.open(bio)

    # Detect candlesticks
    direction, bos, fvg = detect_candles_bos_fvg(image)
    demand_zone, supply_zone = detect_demand_supply(image)

    if direction == "NO TRADE":
        await update.message.reply_text("No valid setup detected.")
        return

    # Use volatility from the market listener
    symbol = "SCREENSHOT"  # placeholder symbol for screenshot trades
    vol = market_volatility.get(symbol, [1]*10)
    tp, sl, timeframe = calculate_tp_sl(direction, bos, fvg, vol)

    # Cooldown check
    last_time = cooldown_tracker.get(symbol)
    now = datetime.now(TIMEZONE)
    if last_time and (now - last_time).total_seconds() < 600:  # 10 min cooldown
        await update.message.reply_text("Cooldown active. Wait before sending another signal.")
        return
    cooldown_tracker[symbol] = now

    save_trade(symbol, direction, tp, sl, timeframe, demand_zone, supply_zone)

    keyboard = [
        [InlineKeyboardButton("✅ WIN", callback_data="win"),
         InlineKeyboardButton("❌ LOSS", callback_data="loss")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = f"""
📊 SIGNAL
Direction: {direction}
TP: {tp}
SL: {sl}
Timeframe: {timeframe}
Demand Zone: {demand_zone}
Supply Zone: {supply_zone}
"""
    await update.message.reply_text(msg, reply_markup=reply_markup)

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "win":
        update_last_result("WIN")
        await query.edit_message_text("Recorded: WIN ✅")
    else:
        update_last_result("LOSS")
        await query.edit_message_text("Recorded: LOSS ❌")

# -------------------
# MAIN
# -------------------
async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(handle_button))
    asyncio.create_task(market_listener())
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
