import asyncio
import websockets
import json
import requests
import logging

# ----------------------
# CONFIG
# ----------------------
BOT_TOKEN = "8751531182:AAHRVd3Zeo7Z9wUWb9q7ruiH_lppQE_ymak"
CHAT_ID = "8308393231"
WEEKEND_WS = "wss://biquote.io/hubs/tick"  # Weekend WebSocket
PING_INTERVAL = 30

# 30 popular OTC currency pairs for testing
OTC_PAIRS = [
    "EURUSD","GBPUSD","USDJPY","AUDUSD","USDCHF","USDCAD",
    "NZDUSD","EURGBP","EURJPY","GBPJPY","AUDJPY","AUDNZD",
    "CHFJPY","EURCHF","EURAUD","EURNZD","GBPCHF","GBPUSD",
    "AUDCAD","AUDCHF","CADJPY","EURCAD","GBPAUD","GBPNZD",
    "NZDJPY","NZDCAD","NZDCHF","USDNOK","USDSEK","USDHKD"
]

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
        logging.warning(f"Failed to send Telegram message: {e}")

# ----------------------
# WEBSOCKET HANDLER
# ----------------------
async def weekend_ticks():
    while True:
        try:
            async with websockets.connect(WEEKEND_WS, ping_interval=PING_INTERVAL, ping_timeout=10) as ws:
                # Subscribe to all OTC pairs
                subscribe_data = {"type":"subscribe", "pairs": OTC_PAIRS}
                await ws.send(json.dumps(subscribe_data))
                logging.info("Subscribed to all OTC pairs on weekend WebSocket...")

                async for message in ws:
                    try:
                        data = json.loads(message)
                        # Assume the tick price is under 'price'
                        for pair in OTC_PAIRS:
                            price = data.get("price")
                            if price:
                                msg = f"Tick | Pair: {pair} | Price: {price}"
                                send_telegram(msg)
                                logging.info(msg)
                    except Exception as e:
                        logging.warning(f"Error parsing tick: {e}")
        except Exception as e:
            logging.error(f"WebSocket connection failed, retrying in 5s: {e}")
            await asyncio.sleep(5)

# ----------------------
# RUN
# ----------------------
async def main():
    await weekend_ticks()

asyncio.run(main())
