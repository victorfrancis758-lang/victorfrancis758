import time
import requests
import logging
from signalrcore.hub_connection_builder import HubConnectionBuilder

# ----------------------
# CONFIG
# ----------------------
BOT_TOKEN = "8751531182:AAHRVd3Zeo7Z9wUWb9q7ruiH_lppQE_ymak"
CHAT_ID = "8308393231"
BIQUOTE_HUB = "https://biquote.io/hubs/tick"

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
        logging.warning(f"Telegram error: {e}")

# ----------------------
# SIGNALR HANDLER
# ----------------------
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

hub_connection = HubConnectionBuilder() \
    .with_url(BIQUOTE_HUB) \
    .with_automatic_reconnect({
        "type": "raw",
        "keep_alive_interval": 10,
        "reconnect_interval": 5
    }) \
    .build()

# This event fires whenever a tick arrives
def on_receive_tick(tick):
    try:
        symbol = tick.get("symbol")
        bid = tick.get("bid")
        ask = tick.get("ask")
        last = tick.get("last")
        if symbol:
            message = f"Tick | {symbol} | bid={bid} ask={ask} last={last}"
            logging.info(message)
            send_telegram(message)
    except Exception as e:
        logging.warning(f"Tick parse error: {e}")

# Register the event
hub_connection.on("ReceiveTick", on_receive_tick)

# Connect
hub_connection.start()
time.sleep(1)

# Subscribe to everything (empty list means you can adjust later)
hub_connection.send("Subscribe", [[]])

logging.info("Connected and subscribed to tick stream...")

# Keep the script running
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    hub_connection.stop()
