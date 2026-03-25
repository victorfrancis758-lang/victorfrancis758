======================================

AI TRADER - OTC + 7 CRYPTO PAIRS + LEARNING + COOL-DOWN + TELEGRAM SIGNALS

======================================

import os import csv import json import asyncio import websockets import numpy as np from datetime import datetime, timedelta from io import BytesIO import pytz from PIL import Image from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, CallbackQueryHandler, ContextTypes, filters import cv2

-------------------

CONFIG

-------------------

BOT_TOKEN = "8751531182:AAHRVd3Zeo7Z9wUWb9q7ruiH_lppQE_ymak" CHAT_ID = "8308393231" DERIV_WS = "wss://ws.binaryws.com/websockets/v3?app_id=1089" TIMEZONE = pytz.timezone("Africa/Lagos") DATA_DIR = "data" LOG_FILE = os.path.join(DATA_DIR, "trades.csv") os.makedirs(DATA_DIR, exist_ok=True)

Currency & crypto pairs

OTC_PAIRS = [ "frxUSDJPY", "frxUSDCHF", "frxUSDSGD", "frxUSDMXN", "frxUSDTRY", "frxUSDZAR", "frxUSDHKD", "frxUSDSEK", "frxUSDCNH", "frxUSDPHP" ] CRYPTO_PAIRS = [ "frxBTCUSD", "frxETHUSD", "frxXRPUSD", "frxLTCUSD", "frxBCHUSD", "frxADAUSD", "frxDOGEUSD" ] ALL_PAIRS = OTC_PAIRS + CRYPTO_PAIRS

COOLDOWN_DEFAULT = 10  # minutes

-------------------

INIT CSV

-------------------

if not os.path.exists(LOG_FILE): with open(LOG_FILE, "w", newline="") as f: csv.writer(f).writerow([ "time","pair","direction","tp","sl","timeframe","result" ])

-------------------

GLOBAL MARKET MEMORY

-------------------

market_volatility = {pair:0.0 for pair in ALL_PAIRS} confidence_bias = {pair:0 for pair in ALL_PAIRS} cooldowns = {pair:datetime.min for pair in ALL_PAIRS}

-------------------

MARKET LISTENER

-------------------

async def market_listener(): async with websockets.connect(DERIV_WS) as ws: for pair in ALL_PAIRS: await ws.send(json.dumps({"ticks": pair, "subscribe":1})) prices = {pair:[] for pair in ALL_PAIRS} async for msg in ws: data = json.loads(msg) if "tick" not in data: continue pair = data["tick"]["symbol"] price = data["tick"]["quote"] prices[pair].append(price) if len(prices[pair]) > 100: prices[pair].pop(0) if len(prices[pair]) >= 10: market_volatility[pair] = np.std(prices[pair])

-------------------

IMAGE ANALYSIS FUNCTIONS

-------------------

def detect_candles_bos_fvg(image: Image): img = np.array(image) gray = np.mean(img, axis=2) series = np.mean(gray, axis=0) series = (series - np.min(series)) / (np.max(series) - np.min(series) + 1e-9) trend = series[-1] - series[0] diff = np.diff(series) bos = np.any(np.abs(diff) > 0.08) fvg = np.any(np.abs(diff) > 0.05) and bos if trend > 0.05 and bos: direction = "BUY" elif trend < -0.05 and bos: direction = "SELL" else: direction = "NO TRADE" return direction, bos, fvg

def detect_demand_supply(image: Image): img = np.array(image) gray = np.mean(img, axis=2) series = np.mean(gray, axis=0) series = (series - np.min(series)) / (np.max(series) - np.min(series) + 1e-9) demand_zone = np.min(series) supply_zone = np.max(series) demand_zone_price = round(demand_zone * 100, 2) supply_zone_price = round(supply_zone * 100, 2) return demand_zone_price, supply_zone_price

-------------------

TP/SL & TIMEFRAME CALCULATION

-------------------

def calculate_tp_sl(direction, bos, fvg, vol): base = 100 risk = max(1, vol * 50 + (5 if fvg else 0)) if direction == "BUY": sl = base - risk tp = base + risk * 2 else: sl = base + risk tp = base - risk * 2 distance = abs(tp - sl) if distance <= 5: timeframe = "M1" elif distance <= 10: timeframe = "M5" elif distance <= 20: timeframe = "M15" elif distance <= 40: timeframe = "M30" else: timeframe = "H1" return round(tp,2), round(sl,2), timeframe

-------------------

SAVE & UPDATE TRADE

-------------------

def save_trade(pair, direction, tp, sl, timeframe): with open(LOG_FILE, "a", newline="") as f: csv.writer(f).writerow([ datetime.now(TIMEZONE), pair, direction, tp, sl, timeframe, "PENDING" ])

def update_last_result(pair, result): global confidence_bias rows = [] with open(LOG_FILE, "r") as f: rows = list(csv.reader(f)) for i in range(len(rows)-1, 0, -1): if rows[i][1] == pair and rows[i][-1] == "PENDING": rows[i][-1] = result break with open(LOG_FILE, "w", newline="") as f: csv.writer(f).writerows(rows) if result == "WIN": confidence_bias[pair] += 1 else: confidence_bias[pair] -= 1

-------------------

TELEGRAM HANDLERS

-------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE): await update.message.reply_text("Send chart screenshot")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE): photo = update.message.photo[-1] file = await photo.get_file() bio = BytesIO() await file.download_to_memory(bio) bio.seek(0) image = Image.open(bio)

direction, bos, fvg = detect_candles_bos_fvg(image)
demand_zone, supply_zone = detect_demand_supply(image)

pair = "UNKNOWN"  # TODO: Could be detected from filename or message

now = datetime.now(TIMEZONE)
if now < cooldowns.get(pair, datetime.min):
    await update.message.reply_text(f"Cooldown active. Wait until {cooldowns[pair]}")
    return

if direction == "NO TRADE":
    await update.message.reply_text("No valid setup")
    return

tp, sl, timeframe = calculate_tp_sl(direction, bos, fvg, market_volatility.get(pair,1))
save_trade(pair, direction, tp, sl, timeframe)

cooldowns[pair] = now + timedelta(minutes=COOLDOWN_DEFAULT)

keyboard = [[InlineKeyboardButton("✅ WIN", callback_data=f"win|{pair}"),
             InlineKeyboardButton("❌ LOSS", callback_data=f"loss|{pair}")]]
reply_markup = InlineKeyboardMarkup(keyboard)

msg = f"Direction: {direction}\nTP: {tp}\nSL: {sl}\nTimeframe: {timeframe}\nDemand Zone: {demand_zone}\nSupply Zone: {supply_zone}"
await update.message.reply_text(msg, reply_markup=reply_markup)

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE): query = update.callback_query await query.answer() data = query.data.split('|') result, pair = data[0].upper(), data[1] update_last_result(pair, result) await query.edit_message_text(f"Recorded: {result} ✅" if result=="WIN" else f"Recorded: {result} ❌")

-------------------

MAIN

-------------------

async def main(): app = ApplicationBuilder().token(BOT_TOKEN).build() app.add_handler(CommandHandler("start", start)) app.add_handler(MessageHandler(filters.PHOTO, handle_photo)) app.add_handler(CallbackQueryHandler(handle_button)) asyncio.create_task(market_listener()) print("Bot running...") await app.run_polling()

-------------------

ENTRY POINT

-------------------

if name == "main": import nest_asyncio nest_asyncio.apply() loop = asyncio.get_event_loop() loop.create_task(main()) loop.run_forever()
