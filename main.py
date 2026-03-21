import asyncio
import websockets
import json
import requests
import logging
import time

# ----------------------
# CONFIG
# ----------------------
WEEKEND_WS = "wss://biquote.io/hubs/tick"  # Weekend WebSocket
BOT_TOKEN = "8751531182:AAHRVd3Zeo7Z9wUWb9q7ruiH_lppQE_ymak"
CHAT_ID = "8308393231"
TELEGRAM_RETRY_INTERVAL = 2
PING_INTERVAL = 30

# ----------------------
# LOGGING
# ----------------------
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

# ----------------------
# TELEGRAM FUNCTION
# ----------------------
def send_telegram(msg):
    while True:
        try:
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                data={"chat_id": CHAT_ID, "text": msg},
                timeout=5
            )
            break
        except Exception as e:
            logging.warning(f"Telegram send failed, retrying in {TELEGRAM_RETRY_INTERVAL}s: {e}")
            time.sleep(TELEGRAM_RETRY_INTERVAL)

# ----------------------
# STREAM ALL TICKS DYNAMICALLY
# ----------------------
async def stream_all_ticks():
    async with websockets.connect(WEEKEND_WS, ping_interval=PING_INTERVAL) as ws:
        # Subscribe to everything available dynamically (no fixed list)
        await ws.send(json.dumps({"type": "subscribe", "pairs": []}))  # empty list = subscribe all

        logging.info("Connected to weekend WebSocket and subscribing to all available OTC pairs...")

        async for msg in ws:
            try:
                data = json.loads(msg)
                pair = data.get("pair") or data.get("symbol") or "UNKNOWN"
                price = data.get("price") or data.get("quote")
                if price is not None:
                    message = f"Tick received: {pair} = {price}"
                    logging.info(message)
                    send_telegram(message)
            except Exception as e:
                logging.warning(f"Error parsing tick: {e}")

# ----------------------
# RUN
# ----------------------
asyncio.run(stream_all_ticks())
