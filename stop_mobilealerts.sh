#!/bin/bash
echo "[Stop] Beende Node..."
pkill -f "node mobilealerts.js"

echo "[Stop] Beende Python-MQTT..."
pkill -f "mqtt_console_plot.py"

# Optional Mosquitto stoppen:
# sudo systemctl stop mosquitto

echo "[Stop] Done."
