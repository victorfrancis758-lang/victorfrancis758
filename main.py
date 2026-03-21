import json
import requests
from signalrcore.hub_connection_builder import HubConnectionBuilder
import time

# === REQUIRED CONFIG ===
SIGNALR_HUB_URL = "https://YOUR_REAL_SIGNALR_URL/otcHub"  # Replace with your real SignalR hub
TELEGRAM_BOT_TOKEN = "8751531182:AAHRVd3Zeo7Z9wUWb9q7ruiH_lppQE_ymak"  # Your Telegram bot token
TELEGRAM_CHAT_ID = "8308393231"  # Your Telegram chat ID

# Send message to Telegram
def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message})
    except Exception as e:
        print(f"[Error] Failed to send Telegram message: {e}")

# Tick handler
def on_tick_received(tick):
    message = f"New Tick: {json.dumps(tick)}"
    print(message)
    send_telegram_message(message)

# Build SignalR connection
hub_connection = HubConnectionBuilder()\
    .with_url(SIGNALR_HUB_URL)\
    .configure_logging(lambda level, message: print(f"[SignalR] {message}"))\
    .build()

# Subscribe to "tick" event
hub_connection.on("tick", on_tick_received)

# Start connection
hub_connection.start()
print("✅ SignalR Hub connected. Streaming ticks now...")

# Keep the script running
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("Stopping...")
    hub_connection.stop()
