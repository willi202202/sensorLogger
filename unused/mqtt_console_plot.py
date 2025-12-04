# mqtt_console_plot.py
import json
from paho.mqtt import client as mqtt

BROKER = "127.0.0.1"
TOPIC  = "mobilealerts/#"

def on_connect(client, userdata, flags, rc):
    print("✅ Verbunden mit MQTT-Broker, Statuscode:", rc)
    client.subscribe(TOPIC)

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
    except Exception:
        payload = msg.payload.decode("utf-8")
    print(f"{msg.topic}: {payload}")

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message
client.connect(BROKER, 1883, 60)
client.loop_forever()
