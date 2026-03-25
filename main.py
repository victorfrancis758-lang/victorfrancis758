# ======================================
# TELEGRAM AI CHART ANALYZER (STABLE)
# ======================================

import os
import csv
import logging
from datetime import datetime
from io import BytesIO

import pytz
import numpy as np
from PIL import Image
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters

# -------------------
# CONFIG
# -------------------
BOT_TOKEN = "8751531182:AAHRVd3Zeo7Z9wUWb9q7ruiH_lppQE_ymak"
TIMEZONE = pytz.timezone("Africa/Lagos")

DATA_DIR = "data"
CSV_FILE = os.path.join(DATA_DIR, "logs.csv")

os.makedirs(DATA_DIR, exist_ok=True)

# -------------------
# INIT CSV
# -------------------
if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "time", "image", "direction", "tp", "sl", "timeframe"
        ])

# -------------------
# CORE ANALYSIS ENGINE
# -------------------
def analyze_chart(image: Image.Image):

    img = np.array(image)

    # Convert to grayscale
    gray = np.mean(img, axis=2)

    # Basic volatility estimation
    volatility = np.std(gray)

    # Trend estimation (simple pixel gradient logic)
    height, width = gray.shape
    left = np.mean(gray[:, :width//2])
    right = np.mean(gray[:, width//2:])

    trend_strength = right - left

    # -------------------
    # DECISION LOGIC
    # -------------------
    if trend_strength > 2:
        direction = "BUY"
    elif trend_strength < -2:
        direction = "SELL"
    else:
        direction = "RANGE"

    # -------------------
    # TP / SL LOGIC
    # -------------------
    base_price = 100  # symbolic since no price feed

    if direction == "BUY":
        sl = base_price - (volatility * 0.5)
        tp = base_price + (volatility * 1.5)

    elif direction == "SELL":
        sl = base_price + (volatility * 0.5)
        tp = base_price - (volatility * 1.5)

    else:
        sl = base_price
        tp = base_price

    # -------------------
    # TIMEFRAME ESTIMATION
    # -------------------
    if volatility < 20:
        timeframe = "M5"
    elif volatility < 40:
        timeframe = "M15"
    else:
        timeframe = "M30"

    return direction, round(tp, 2), round(sl, 2), timeframe

# -------------------
# SAVE LOG
# -------------------
def save_log(image_name, direction, tp, sl, timeframe):
    with open(CSV_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            datetime.now(TIMEZONE), image_name, direction, tp, sl, timeframe
        ])

# -------------------
# TELEGRAM HANDLERS
# -------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📊 Send chart screenshot for analysis")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):

    photo = update.message.photo[-1]
    file = await photo.get_file()

    bio = BytesIO()
    await file.download_to_memory(bio)
    bio.seek(0)

    image = Image.open(bio)

    # Analyze
    direction, tp, sl, timeframe = analyze_chart(image)

    # Save image
    timestamp = datetime.now(TIMEZONE).strftime("%Y%m%d_%H%M%S")
    filename = f"{DATA_DIR}/chart_{timestamp}.png"
    image.save(filename)

    # Log
    save_log(filename, direction, tp, sl, timeframe)

    # Reply
    msg = f"""
📊 ANALYSIS RESULT

Direction: {direction}
TP: {tp}
SL: {sl}
Timeframe: {timeframe}
"""

    await update.message.reply_text(msg)

# -------------------
# RUN BOT
# -------------------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    print("Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()
