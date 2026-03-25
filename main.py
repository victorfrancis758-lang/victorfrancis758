# ======================================
# AI TRADER WITH CANDLESTICK + BoS + FVG + FEEDBACK
# ======================================

import os
import csv
import json
import asyncio
import websockets
import numpy as np
from datetime import datetime
from io import BytesIO
import pytz
from PIL import Image
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, CallbackQueryHandler, ContextTypes, filters

# -------------------
# CONFIG
# -------------------
BOT_TOKEN = "8751531182:AAHRVd3Zeo7Z9wUWb9q7ruiH_lppQE_ymak"
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
            "time","direction","tp","sl","timeframe","result"
        ])

# -------------------
# GLOBAL MARKET MEMORY
# -------------------
market_volatility = 0.0
confidence_bias = 0  # learning factor

# -------------------
# REAL MARKET (TICKS)
# -------------------
async def market_listener():
    global market_volatility
    async with websockets.connect(DERIV_WS) as ws:
        # Subscribe to EURUSD, extendable
        await ws.send(json.dumps({"ticks":"frxEURUSD","subscribe":1}))

        prices = []

        async for msg in ws:
            data = json.loads(msg)
            if "tick" not in data:
                continue

            price = data["tick"]["quote"]
            prices.append(price)

            if len(prices) > 100:
                prices.pop(0)

            if len(prices) >= 10:
                market_volatility = np.std(prices)

# -------------------
# CANDLESTICK + BoS + FVG DETECTION (SIMPLIFIED)
# -------------------
def detect_candles_bos_fvg(image: Image):
    img = np.array(image)
    gray = np.mean(img, axis=2)
    series = np.mean(gray, axis=0)
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
# TP/SL & TIMEFRAME CALCULATION
# -------------------
def calculate_tp_sl(direction, bos, fvg, vol):
    base = 100
    risk = max(1, vol * 50 + (5 if fvg else 0))

    if direction == "BUY":
        sl = base - risk
        tp = base + risk * 2
    else:
        sl = base + risk
        tp = base - risk * 2

    if vol < 0.03:
        timeframe = "M5"
    elif vol < 0.06:
        timeframe = "M15"
    else:
        timeframe = "M30"

    return round(tp,2), round(sl,2), timeframe

# -------------------
# SAVE TRADE
# -------------------
def save_trade(direction, tp, sl, timeframe):
    with open(LOG_FILE, "a", newline="") as f:
        csv.writer(f).writerow([
            datetime.now(TIMEZONE), direction, tp, sl, timeframe, "PENDING"
        ])

# -------------------
# UPDATE RESULT
# -------------------
def update_last_result(result):
    global confidence_bias
    rows = []
    with open(LOG_FILE, "r") as f:
        rows = list(csv.reader(f))

    rows[-1][-1] = result

    with open(LOG_FILE, "w", newline="") as f:
        csv.writer(f).writerows(rows)

    if result == "WIN":
        confidence_bias += 1
    else:
        confidence_bias -= 1

# -------------------
# TELEGRAM HANDLERS
# -------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send chart screenshot")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    file = await photo.get_file()
    bio = BytesIO()
    await file.download_to_memory(bio)
    bio.seek(0)
    image = Image.open(bio)

    direction, bos, fvg = detect_candles_bos_fvg(image)

    if direction == "NO TRADE":
        await update.message.reply_text("No valid setup")
        return

    tp, sl, timeframe = calculate_tp_sl(direction, bos, fvg, market_volatility)
    save_trade(direction, tp, sl, timeframe)

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

    # start market listener in background
    asyncio.create_task(market_listener())

    print("Bot running...")
    await app.run_polling()

# -------------------
# RAILWAY-FRIENDLY ENTRY POINT
# -------------------
if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    loop = asyncio.get_event_loop()
    loop.create_task(main())
    loop.run_forever()
