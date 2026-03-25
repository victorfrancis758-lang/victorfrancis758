# ======================================
# AI TRADER WITH SELF-LEARNING SYSTEM
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
STATS_FILE = os.path.join(DATA_DIR, "stats.json")
os.makedirs(DATA_DIR, exist_ok=True)

# -------------------
# INIT FILES
# -------------------
if not os.path.exists(LOG_FILE):
    with open(LOG_FILE, "w", newline="") as f:
        csv.writer(f).writerow([
            "time","direction","tp","sl","timeframe","result"
        ])

if not os.path.exists(STATS_FILE):
    with open(STATS_FILE, "w") as f:
        json.dump({
            "buy_win":0,
            "buy_loss":0,
            "sell_win":0,
            "sell_loss":0
        }, f)

# -------------------
# GLOBAL
# -------------------
market_volatility = 0.0

# -------------------
# LOAD STATS
# -------------------
def load_stats():
    with open(STATS_FILE) as f:
        return json.load(f)

def save_stats(stats):
    with open(STATS_FILE, "w") as f:
        json.dump(stats, f)

# -------------------
# REAL MARKET
# -------------------
async def market_listener():
    global market_volatility
    async with websockets.connect(DERIV_WS) as ws:
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
# SIMPLE IMAGE ANALYSIS
# -------------------
def detect_direction(image: Image):
    img = np.array(image)
    gray = np.mean(img, axis=2)
    trend = np.mean(gray[:, -50:]) - np.mean(gray[:, :50])

    if trend > 0:
        return "BUY"
    else:
        return "SELL"

# -------------------
# TP/SL WITH LEARNING
# -------------------
def calculate_tp_sl(direction, vol):
    stats = load_stats()

    base = 100
    risk = max(1, vol * 50)

    # Learning adjustment
    if direction == "BUY":
        win = stats["buy_win"]
        loss = stats["buy_loss"]
    else:
        win = stats["sell_win"]
        loss = stats["sell_loss"]

    total = win + loss if (win+loss) > 0 else 1
    accuracy = win / total

    # Adjust risk based on performance
    if accuracy > 0.6:
        risk *= 1.2
    elif accuracy < 0.4:
        risk *= 0.8

    if direction == "BUY":
        sl = base - risk
        tp = base + risk * 2
    else:
        sl = base + risk
        tp = base - risk * 2

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
def save_trade(direction, tp, sl, timeframe):
    with open(LOG_FILE, "a", newline="") as f:
        csv.writer(f).writerow([
            datetime.now(TIMEZONE), direction, tp, sl, timeframe, "PENDING"
        ])

# -------------------
# UPDATE RESULT + LEARNING
# -------------------
def update_last_result(direction, result):
    stats = load_stats()

    rows = []
    with open(LOG_FILE, "r") as f:
        rows = list(csv.reader(f))

    rows[-1][-1] = result

    with open(LOG_FILE, "w", newline="") as f:
        csv.writer(f).writerows(rows)

    # Update learning stats
    if direction == "BUY":
        if result == "WIN":
            stats["buy_win"] += 1
        else:
            stats["buy_loss"] += 1
    else:
        if result == "WIN":
            stats["sell_win"] += 1
        else:
            stats["sell_loss"] += 1

    save_stats(stats)

# -------------------
# TELEGRAM
# -------------------
last_signal_direction = None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send chart screenshot")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global last_signal_direction

    photo = update.message.photo[-1]
    file = await photo.get_file()
    bio = BytesIO()
    await file.download_to_memory(bio)
    bio.seek(0)
    image = Image.open(bio)

    direction = detect_direction(image)
    last_signal_direction = direction

    tp, sl, timeframe = calculate_tp_sl(direction, market_volatility)
    save_trade(direction, tp, sl, timeframe)

    keyboard = [
        [InlineKeyboardButton("✅ WIN", callback_data="win"),
         InlineKeyboardButton("❌ LOSS", callback_data="loss")]
    ]

    msg = f"""
📊 SIGNAL
Direction: {direction}
TP: {tp}
SL: {sl}
Timeframe: {timeframe}
"""

    await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global last_signal_direction

    query = update.callback_query
    await query.answer()

    if query.data == "win":
        update_last_result(last_signal_direction, "WIN")
        await query.edit_message_text("Recorded: WIN ✅")
    else:
        update_last_result(last_signal_direction, "LOSS")
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
# ENTRY
# -------------------
if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    loop = asyncio.get_event_loop()
    loop.create_task(main())
    loop.run_forever()
