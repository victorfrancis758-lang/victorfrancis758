import asyncio
import json
import requests
from signalrcore.hub_connection_builder import HubConnectionBuilder

# --- Telegram ---
TELEGRAM_BOT_TOKEN = "8751531182:AAHRVd3Zeo7Z9wUWb9q7ruiH_lppQE_ymak"
TELEGRAM_CHAT_ID = "8308393231"

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        requests.post(url, data=data)
    except Exception as e:
        print("Telegram error:", e)

# --- WebSocket URL ---
WEEKEND_WS_URL = "YOUR_WEEKEND_SIGNALR_HUB_URL"  # replace with actual

# --- OTC Pairs for weekend ---
OTC_PAIRS = [
    "OTC-USDJPY", "OTC-EURUSD", "OTC-GBPUSD", "OTC-AUDUSD", "OTC-USDCAD",
    "OTC-EURJPY", "OTC-GBPJPY", "OTC-AUDJPY", "OTC-USDCHF", "OTC-EURAUD",
    "OTC-EURGBP", "OTC-GBPCHF", "OTC-AUDNZD", "OTC-USDNOK", "OTC-USDSEK",
    "OTC-USDSGD", "OTC-EURNZD", "OTC-GBPNZD", "OTC-NZDUSD", "OTC-CADJPY",
    "OTC-EURCAD", "OTC-GBPCA", "OTC-AUDCAD", "OTC-AUDCHF", "OTC-NZDJPY",
    "OTC-NZDCHF", "OTC-CADCHF", "OTC-EURCHF", "OTC-GBPZAR", "OTC-USDZAR"
]

# --- Connect to SignalR ---
hub_connection = HubConnectionBuilder()\
    .with_url(WEEKEND_WS_URL)\
    .build()

def on_tick_received(tick_data):
    try:
        tick = json.loads(tick_data)
        send_telegram_message(f"Tick: {tick}")
    except Exception as e:
        print("Tick parse error:", e)

for pair in OTC_PAIRS:
    hub_connection.on(f"{pair}_tick", on_tick_received)

hub_connection.start()
print("Connected to weekend WebSocket... streaming all ticks")

try:
    while True:
        asyncio.sleep(1)
except KeyboardInterrupt:
    hub_connection.stop()
