#!/bin/bash

#Verhalten:
#startet Mosquitto (wenn nicht schon aktiv)
#setzt den Proxy im Gateway
#startet mobilealerts.js im Hintergrund mit Logfile
#startet dein Python-MQTT-Subscriber
#funktioniert für lokal + Cloud oder nur lokal

### ===============================
### Einstellungen
### ===============================

LOCAL_IP="192.168.1.203"        # IP des Raspi
GATEWAY_IP="192.168.1.200"     # Mobile-Alerts Gateway
PROXY_PORT="8089"              # Muss zu config.json passen!
REPO_DIR="$HOME/project/MMMMobileAlerts/maserver"
PY_SCRIPT="$HOME/project/mqtt_sqlite_logger.py"

LOG_NODE="$HOME/project/sensorLogger/log/mobilealerts.log"
LOG_PY="$HOME/project/sensorLogger/log/python_mqtt.log"

### ===============================
### 1) MQTT-Broker (Mosquitto) starten
### ===============================

echo "[MQTT] Prüfe Mosquitto..."
if ! systemctl is-active --quiet mosquitto; then
    echo "[MQTT] Starte Mosquitto..."
    sudo systemctl start mosquitto
else
    echo "[MQTT] Mosquitto läuft bereits."
fi

### ===============================
### 2) In das Projekt wechseln
### ===============================

cd "$REPO_DIR" || {
    echo "[FEHLER] REPO_DIR nicht gefunden!"
    exit 1
}

### ===============================
### 3) Proxy im Gateway setzen
### ===============================

echo "[GW] Setze Proxy $LOCAL_IP:$PROXY_PORT im Gateway $GATEWAY_IP ..."
node gatewayConfig.js --ip "$GATEWAY_IP" --set-proxy "$LOCAL_IP:$PROXY_PORT"

### ===============================
### 4) mobilealerts.js starten (Hintergrund)
### ===============================

echo "[Node] Starte mobilealerts.js im Hintergrund..."
nohup node mobilealerts.js \
    --localIPv4Address="$LOCAL_IP" \
    --proxyServerPort="$PROXY_PORT" \
    > "$LOG_NODE" 2>&1 &

sleep 3

### ===============================
### 5) Python-Subscriber starten
### ===============================

if [ -f "$PY_SCRIPT" ]; then
    echo "[Python] Starte MQTT-Subscriber..."
    nohup python3 "$PY_SCRIPT" > "$LOG_PY" 2>&1 &
else
    echo "[WARNUNG] Python-Skript '$PY_SCRIPT' wurde nicht gefunden."
fi

echo "[OK] Start komplett!"
echo "Logs:"
echo " - NodeJS:   $LOG_NODE"
echo " - Python:   $LOG_PY"
