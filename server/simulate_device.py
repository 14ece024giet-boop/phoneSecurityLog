import time
import requests
from datetime import datetime, timezone, timedelta

SERVER_URL = "http://127.0.0.1:8000/api/v1/telemetry/batch"
API_KEY = "my_personal_phone_secret_key_123"
DEVICE_ID = "pixel_7_personal"
DEVICE_NAME = "My Pixel 7 (Secured)"

now = datetime.now(timezone.utc)

simulated_events = [
    {
        "timestamp": (now - timedelta(minutes=25)).isoformat(),
        "event_type": "SCREEN_UNLOCK",
        "battery_level": 92,
        "latitude": 28.6139,
        "longitude": 77.2090,
        "details": {"method": "FINGERPRINT", "screen_state": "UNLOCKED"}
    },
    {
        "timestamp": (now - timedelta(minutes=20)).isoformat(),
        "event_type": "APP_FOREGROUND",
        "battery_level": 90,
        "latitude": 28.6139,
        "longitude": 77.2090,
        "details": {"package_name": "com.whatsapp", "app_name": "WhatsApp"}
    },
    {
        "timestamp": (now - timedelta(minutes=15)).isoformat(),
        "event_type": "LOCATION_PING",
        "battery_level": 89,
        "latitude": 28.6160,
        "longitude": 77.2110,
        "details": {"provider": "fused_gps", "accuracy_meters": 4.5}
    },
    {
        "timestamp": (now - timedelta(minutes=10)).isoformat(),
        "event_type": "SCREEN_OFF",
        "battery_level": 88,
        "latitude": 28.6160,
        "longitude": 77.2110,
        "details": {"trigger": "TIMEOUT"}
    },
    {
        "timestamp": (now - timedelta(minutes=5)).isoformat(),
        "event_type": "CHARGING_CONNECTED",
        "battery_level": 88,
        "latitude": 28.6160,
        "longitude": 77.2110,
        "details": {"charger_type": "AC_FAST_CHARGER", "voltage_mv": 4200}
    }
]

payload = {
    "device_id": DEVICE_ID,
    "device_name": DEVICE_NAME,
    "events": simulated_events
}

headers = {
    "X-API-KEY": API_KEY,
    "Content-Type": "application/json"
}

def main():
    print(f"[+] Sending {len(simulated_events)} simulated events to {SERVER_URL}...")
    try:
        response = requests.post(SERVER_URL, json=payload, headers=headers)
        if response.status_code == 200:
            print("[SUCCESS] Ingested events successfully!")
            print("Server Response:", response.json())
            print("\n[+] Open your browser at http://127.0.0.1:8000/dashboard to view the live dashboard.")
        else:
            print(f"[ERROR] Server returned status {response.status_code}:", response.text)
    except Exception as err:
        print("[ERROR] Could not connect to the server:", err)

if __name__ == "__main__":
    main()

