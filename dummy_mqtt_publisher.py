#!/usr/bin/env python3
import time
import json
import random
from datetime import datetime, timedelta
import paho.mqtt.client as mqtt


BROKER = "127.0.0.1"   # Ziel: dein Windows-Broker
TOPIC_PREFIX = "mobilealerts"
GATEWAY_ID = "11566802925f"


def generate_payload(counter: int):
    """
    Erzeugt ein Payload ähnlich den echten Daten.
    """
    ts = datetime.utcnow() - timedelta(seconds=counter * 60)
    ts_iso = ts.isoformat(timespec="seconds") + "Z"

    payload = {
        "temperature1": [round(3.6 + random.uniform(-0.3, 0.3), 1), 3.8],
        "humidity1": [random.randint(90, 95), 94],
        "temperature2": [round(19.2 + random.uniform(-0.3, 0.3), 1), 19.2],
        "humidity2": [random.randint(56, 62), 59],
        "temperature3": [round(15.3 + random.uniform(-0.3, 0.3), 1), 15.3],
        "humidity3": [random.randint(56, 60), 58],
        "temperatureIN": [round(20.8 + random.uniform(-0.5, 0.5), 1), 20.8],
        "humidityIN": [random.randint(42, 50), 46],
        "id": GATEWAY_ID,
        "t": ts.strftime("%d.%m.%Y, %H:%M:%S"),
        "ut": int(ts.timestamp()),
        "utms": ts_iso,
        "battery": "ok" if counter % 5 != 0 else "low",
        "offline": False
    }

    return payload


def main():
    print(f"Verbinde zu MQTT Broker {BROKER} ...")
    client = mqtt.Client()

    client.connect(BROKER)
    print("Verbunden ✔")

    count = 0

    while True:
        payload = generate_payload(count)
        topic = f"{TOPIC_PREFIX}/{GATEWAY_ID}/json"
        data_json = json.dumps(payload)

        print(f"> Sending: {topic} → {data_json}")

        client.publish(topic, data_json)

        time.sleep(3)   # alle 3 Sekunden neuer Dummy-Datensatz
        count += 1


if __name__ == "__main__":
    main()
