import asyncio
import json
import requests
from signalrcore.hub_connection_builder import HubConnectionBuilder
import websockets
from collections import deque
import logging
from datetime import datetime
import pytz

# ----------------------
# CONFIG
# ----------------------
BOT_TOKEN = "8751531182:AAHRVd3Zeo7Z9wUWb9q7ruiH_lppQE_ymak"
CHAT_ID = "8308393231"
DERIV_WS = "wss://ws.binaryws.com/websockets/v3?app_id=1089"
WEEKEND_WS = "https://biquote.io/hubs/tick"  # SignalR weekend WebSocket
TIMEZONE = pytz.timezone("Africa/Lagos")

# Top 30 popular OTC pairs
OTC_PAIRS = [
    "frxAUDCAD", "frxAUDCHF", "frxAUDJPY", "frxAUDNZD", "frxAUDUSD",
    "frxCADCHF", "frxCADJPY", "frxCHFJPY", "frxEURAUD", "frxEURCAD",
    "frxEURCHF", "frxEURGBP", "frxEURJPY", "frxEURNZD", "frxEURUSD",
    "frxGBPAUD", "frxGBPCAD", "frxGBPCHF", "frxGBPJPY", "frxGBPNZD",
    "frxGBPUSD", "frxNZDCAD", "frxNZDCHF", "frxNZDJPY", "frxNZDUSD",
    "frxUSDCAD", "frxUSDCHF", "frxUSDJPY", "frxUSDNOK", "frxUSDSEK"
]

# ----------------------
# LOGGING
# ----------------------
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

# ----------------------
# TELEGRAM
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
# DERIV WebSocket (weekdays)
# ----------------------
async def deriv_stream():
    async with websockets.connect(DERIV_WS) as ws:
        for pair in OTC_PAIRS:
            await ws.send(json.dumps({"ticks": pair, "subscribe": 1}))
        logging.info("Subscribed to all OTC pairs on Deriv WebSocket")

        async for msg in ws:
            try:
                data = json.loads(msg)
                if "tick" in data:
                    pair = data["tick"]["symbol"]
                    price = data["tick"]["quote"]
                    msg_text = f"Deriv Tick: {pair} = {price}"
                    send_telegram(msg_text)
                    logging.info(msg_text)
            except Exception as e:
                logging.warning(f"Error parsing tick: {e}")

# ----------------------
# WEEKEND SignalR WebSocket
# ----------------------
def weekend_stream():
    hub_connection = HubConnectionBuilder()\
        .with_url(WEEKEND_WS)\
        .build()

    def on_message(msg):
        try:
            data = json.loads(msg)
            pair = data.get("pair")
            price = data.get("price")
            if pair and price is not None:
                msg_text = f"Weekend Tick: {pair} = {price}"
                send_telegram(msg_text)
                logging.info(msg_text)
        except Exception as e:
            logging.warning(f"Error parsing weekend tick: {e}")

    hub_connection.on("tick", on_message)
    hub_connection.start()

# ----------------------
# MAIN
# ----------------------
async def main():
    now = datetime.now(TIMEZONE)
    weekday = now.weekday()  # 0=Mon, 6=Sun

    if weekday in [5, 6]:  # Weekend
        logging.info("Starting weekend SignalR stream")
        weekend_stream()
        while True:
            await asyncio.sleep(1)
    else:  # Weekday
        logging.info("Starting weekday Deriv WebSocket stream")
        await deriv_stream()

if __name__ == "__main__":
    asyncio.run(main())
