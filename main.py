# ======================================
# STRUCTURE-BASED TRADING BOT (REAL LOGIC)
# ======================================

import os, csv, json, asyncio, websockets, numpy as np, pytz
from datetime import datetime
from io import BytesIO
from PIL import Image
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, CallbackQueryHandler, ContextTypes, filters

# -------------------
BOT_TOKEN = "8751531182:AAHRVd3Zeo7Z9wUWb9q7ruiH_lppQE_ymak"
DERIV_WS = "wss://ws.binaryws.com/websockets/v3?app_id=1089"
TIMEZONE = pytz.timezone("Africa/Lagos")

DATA_DIR = "data"
LOG_FILE = os.path.join(DATA_DIR, "trades.csv")
os.makedirs(DATA_DIR, exist_ok=True)

if not os.path.exists(LOG_FILE):
    with open(LOG_FILE,"w",newline="") as f:
        csv.writer(f).writerow(["time","direction","entry","tp","sl","timeframe","result"])

market_prices = []

# -------------------
# MARKET FEED
# -------------------
async def market_listener():
    global market_prices
    async with websockets.connect(DERIV_WS) as ws:
        await ws.send(json.dumps({"ticks":"frxEURUSD","subscribe":1}))

        async for msg in ws:
            data = json.loads(msg)
            if "tick" not in data: continue

            price = data["tick"]["quote"]
            market_prices.append(price)

            if len(market_prices) > 200:
                market_prices.pop(0)

# -------------------
# STRUCTURE LOGIC
# -------------------
def analyze_market_structure():
    if len(market_prices) < 50:
        return None

    prices = np.array(market_prices[-50:])

    highs = []
    lows = []

    for i in range(2, len(prices)-2):
        if prices[i] > prices[i-1] and prices[i] > prices[i+1]:
            highs.append(prices[i])
        if prices[i] < prices[i-1] and prices[i] < prices[i+1]:
            lows.append(prices[i])

    if len(highs) < 2 or len(lows) < 2:
        return None

    # Trend detection
    if highs[-1] > highs[-2] and lows[-1] > lows[-2]:
        trend = "UP"
    elif highs[-1] < highs[-2] and lows[-1] < lows[-2]:
        trend = "DOWN"
    else:
        trend = "RANGE"

    # Break of Structure
    bos = False
    if trend == "UP" and prices[-1] > highs[-2]:
        bos = True
    elif trend == "DOWN" and prices[-1] < lows[-2]:
        bos = True

    return trend, bos, highs, lows

# -------------------
# TRADE SETUP
# -------------------
def generate_trade():
    data = analyze_market_structure()
    if not data:
        return None

    trend, bos, highs, lows = data
    current_price = market_prices[-1]

    if trend == "UP" and bos:
        entry = current_price
        sl = lows[-1]
        tp = entry + (entry - sl) * 2
        direction = "BUY"

    elif trend == "DOWN" and bos:
        entry = current_price
        sl = highs[-1]
        tp = entry - (sl - entry) * 2
        direction = "SELL"

    else:
        return None

    distance = abs(tp - sl)

    if distance < 0.0005:
        timeframe = "M1"
    elif distance < 0.001:
        timeframe = "M5"
    elif distance < 0.002:
        timeframe = "M15"
    else:
        timeframe = "M30"

    return direction, entry, tp, sl, timeframe

# -------------------
# SAVE
# -------------------
def save_trade(direction, entry, tp, sl, timeframe):
    with open(LOG_FILE,"a",newline="") as f:
        csv.writer(f).writerow([
            datetime.now(TIMEZONE), direction, entry, tp, sl, timeframe, "PENDING"
        ])

def update_last(result):
    rows = list(csv.reader(open(LOG_FILE)))
    rows[-1][-1] = result
    with open(LOG_FILE,"w",newline="") as f:
        csv.writer(f).writerows(rows)

# -------------------
# TELEGRAM
# -------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send screenshot to trigger analysis")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    trade = generate_trade()

    if not trade:
        await update.message.reply_text("❌ No valid structure setup")
        return

    direction, entry, tp, sl, timeframe = trade
    save_trade(direction, entry, tp, sl, timeframe)

    msg = f"""
📊 STRUCTURE SIGNAL

Direction: {direction}
Entry: {entry}
TP: {round(tp,5)}
SL: {round(sl,5)}
Timeframe: {timeframe}
"""

    keyboard = [[
        InlineKeyboardButton("✅ WIN", callback_data="win"),
        InlineKeyboardButton("❌ LOSS", callback_data="loss")
    ]]

    await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "win":
        update_last("WIN")
        await query.edit_message_text("Recorded WIN ✅")
    else:
        update_last("LOSS")
        await query.edit_message_text("Recorded LOSS ❌")

# -------------------
# MAIN
# -------------------
async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(handle_button))

    asyncio.create_task(market_listener())

    print("Running REAL trading bot...")
    await app.run_polling()

if __name__ == "__main__":
    import nest_asyncio, asyncio
    nest_asyncio.apply()
    asyncio.get_event_loop().run_until_complete(main())
