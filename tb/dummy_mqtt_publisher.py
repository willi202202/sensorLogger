#!/usr/bin/env python3
# dummy_mqtt_publisher.py
#
# Publiziert Dummy-Daten fuer TH + Wind und kann gezielt Exceptions ausloesen.

import time
import json
import random
from datetime import datetime, timedelta
import paho.mqtt.client as mqtt

BROKER = "127.0.0.1"
TOPIC_PREFIX = "mobilealerts"
TOPIC_PREFIX_ERROR = "mobilefault"

SENSOR_TH = "11566802925f"
SENSOR_W  = "0b55aada036f"
SENSOR_ERROR  = "0b55aada9999"  # Unbekannter Sensor fuer UnknownSensorError


def iso_utc(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds") + ".000Z"


def base_timestamps(counter: int):
    ts = datetime.utcnow() - timedelta(seconds=counter * 60)
    return {
        "t": ts.strftime("%d.%m.%Y, %H:%M:%S"),
        "ut": int(ts.timestamp()),
        "utms": iso_utc(ts),
        "lastTransmit": random.randint(200, 600),
    }


def payload_th(counter: int) -> dict:
    base = base_timestamps(counter)
    return {
        "temperature1": [round(3.6 + random.uniform(-0.3, 0.3), 1), 3.8],
        "humidity1":    [random.randint(90, 95), 94],
        "temperature2": [round(19.2 + random.uniform(-0.3, 0.3), 1), 19.2],
        "humidity2":    [random.randint(56, 62), 59],
        "temperature3": [round(15.3 + random.uniform(-0.3, 0.3), 1), 15.3],
        "humidity3":    [random.randint(56, 60), 58],
        "temperatureIN":[round(20.8 + random.uniform(-0.5, 0.5), 1), 20.8],
        "humidityIN":   [random.randint(42, 50), 46],
        "battery":      "ok" if counter % 7 != 0 else "low",
        "offline":      False,
        "id": SENSOR_TH,
        **base,
    }


def payload_wind(counter: int) -> dict:
    base = base_timestamps(counter)
    return {
        "directionDegree": round(random.uniform(0, 360), 1),
        "direction": random.choice(["N", "NE", "E", "SE", "S", "SW", "W", "NW", "WSW"]),
        "windSpeed": round(random.uniform(0.0, 3.5), 1),
        "gustSpeed": round(random.uniform(0.0, 5.0), 1),
        "battery": "ok" if counter % 6 != 0 else "low",
        "offline": False,
        "id": SENSOR_W,
        **base,
    }


# --------------------------
# Fault injection
# --------------------------

def publish_invalid_json(client: mqtt.Client, topic: str):
    # Ungueltiges JSON -> JSONDecodeError
    payload = "{not-json"
    print(f"> [FAULT] invalid_json: {topic} {payload}")
    client.publish(topic, payload)


def publish_non_dict_json(client: mqtt.Client, topic: str):
    # JSON aber nicht dict -> PayloadFormatError (wenn raise aktiviert)
    payload = json.dumps([1, 2, 3])
    print(f"> [FAULT] non_dict_payload: {topic} {payload}")
    client.publish(topic, payload)


def publish_missing_timestamp(client: mqtt.Client, topic: str, base_payload: dict, ts_key: str = "utms"):
    # utms entfernen -> MissingTimestampError (wenn raise aktiviert)
    p = dict(base_payload)
    if ts_key in p:
        del p[ts_key]
    payload = json.dumps(p)
    print(f"> [FAULT] missing_timestamp: {topic} {payload}")
    client.publish(topic, payload)

def publish_unknown_sensor_exception(client: mqtt.Client, base_payload: dict):
    # Unbekannter Sensor -> UnknownSensorError
    topic = f"{TOPIC_PREFIX}/{SENSOR_ERROR}/json"
    payload = json.dumps(base_payload)
    print(f"> [FAULT] unknown_sensor: {topic} {payload}")
    client.publish(topic, payload)

def publish_unknown_topic_prefix_exception(client: mqtt.Client, base_payload: dict):
    # Unbekannter Sensor -> UnknownSensorError
    topic = f"{TOPIC_PREFIX_ERROR}/{SENSOR_W}/json"
    payload = json.dumps(base_payload)
    print(f"> [FAULT] unknown_topic_prefix: {topic} {payload}")
    client.publish(topic, payload)


def publish_bad_values(client: mqtt.Client, base_payload: dict):
    # Fehlerhafte Werte -> Bad-Values Alarm
    # temperature1 auf -9999 setzen (invalid_map wird auf NULL gemappt)
    p = dict(base_payload)
    p["temperature1"] = [-9999, 3.8]  # Bad value
    topic = f"{TOPIC_PREFIX}/{SENSOR_TH}/json"
    payload = json.dumps(p)
    print(f"> [FAULT] bad_values (temperature1=-9999): {topic}")
    client.publish(topic, payload)


def main():
    print(f"🔌 Verbinde zu MQTT Broker {BROKER} ...")
    client = mqtt.Client()
    client.connect(BROKER)
    print("✅ Verbunden")

    counter = 0

    while True:
        # normale Messages
        th = payload_th(counter)
        w  = payload_wind(counter)

        th_topic = f"{TOPIC_PREFIX}/{SENSOR_TH}/json"
        w_topic  = f"{TOPIC_PREFIX}/{SENSOR_W}/json"

        client.publish(th_topic, json.dumps(th))
        client.publish(w_topic, json.dumps(w))
        print(f"> OK: {th_topic} (th), {w_topic} (wind)")

        # Fault injections
        offset = 6
        if True:
            if counter == 1*offset:
                publish_missing_timestamp(client, w_topic, w, ts_key="utms")

            if counter == 2*offset:
                publish_non_dict_json(client, w_topic)

            if counter == 3*offset:
                publish_invalid_json(client, w_topic)

            if counter == 4*offset:
                publish_unknown_sensor_exception(client, w)
                
            if counter == 5*offset:
                publish_unknown_topic_prefix_exception(client, w)

            if counter == 6*offset:
                publish_bad_values(client, th)

        if counter >= 7*offset:
            counter = 0
        else:
            counter += 1
        time.sleep(3)


if __name__ == "__main__":
    main()
