import asyncio
import json
import websockets
import requests
import logging

# ----------------------
# CONFIG
# ----------------------
BOT_TOKEN = "8751531182:AAHRVd3Zeo7Z9wUWb9q7ruiH_lppQE_ymak"
CHAT_ID = "8308393231"
WEEKEND_WS = "wss://biquote.io/hubs/tick"
PING_INTERVAL = 30

# Popular OTC currency pairs (weekend trading)
OTC_PAIRS = [
    "EURUSD","GBPUSD","USDJPY","AUDUSD","USDCHF",
    "USDCAD","NZDUSD","EURGBP","EURJPY","GBPJPY",
    "AUDJPY","EURAUD","EURAUD","GBPCHF","AUDCHF",
    "CHFJPY","EURCAD","GBPCAD","AUDNZD","NZDJPY",
    "CADJPY","EURCHF","GBPJPY","EURNZD","GBPUSD",
    "USDJPY","AUDUSD","USDCHF","EURUSD","GBPUSD"
]

# ----------------------
# LOGGING
# ----------------------
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

# ----------------------
# TELEGRAM FUNCTION
# ----------------------
def send_telegram(msg):
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": msg},
            timeout=5
        )
    except Exception as e:
        logging.warning(f"Telegram send failed: {e}")

# ----------------------
# HANDLE TICKS
# ----------------------
async def handle_pair(pair, ws):
    async for msg in ws:
        try:
            # Sometimes multiple JSON objects can come in one message
            for part in msg.split("\n"):
                if not part.strip():
                    continue
                data = json.loads(part)
                # Extract price from weekend WebSocket structure
                price = float(data.get("price", 0))
                if price == 0:
                    continue
                # Send every tick to Telegram
                send_telegram(f"Pair: {pair} | Price: {price}")
                logging.info(f"{pair} | {price}")
        except Exception as e:
            logging.warning(f"Error parsing tick for {pair}: {e}")

# ----------------------
# MAIN CONNECTION
# ----------------------
async def main():
    try:
        async with websockets.connect(WEEKEND_WS, ping_interval=PING_INTERVAL, ping_timeout=10) as ws:
            # Subscribe to all OTC pairs
            subscribe_msg = {"type":"subscribe", "pairs": OTC_PAIRS}
            await ws.send(json.dumps(subscribe_msg))
            logging.info(f"Subscribed to all OTC pairs on weekend WebSocket...")
            
            # Handle all pairs concurrently
            tasks = [handle_pair(pair, ws) for pair in OTC_PAIRS]
            await asyncio.gather(*tasks)
    except Exception as e:
        logging.error(f"WebSocket connection failed: {e}")
        await asyncio.sleep(5)
        await main()  # Retry on fail

# ----------------------
# RUN
# ----------------------
asyncio.run(main())
