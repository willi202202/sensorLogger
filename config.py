#!/usr/bin/env python3
# config.py

# ---------------- MQTT CONFIG ----------------
BROKER = "127.0.0.1"
BROKER_PORT = 1883
TOPIC = "mobilealerts/#"
CLIENT_ID = "mqtt_sqlite_logger"

# ---------------- DATABASE CONFIG ----------------
DB_FILE = "log/mobilealerts.db"
TABLE_NAME = "measurements"

# Feldname -> SQL-Typ
# Namen entsprechen 1:1 den MQTT/JSON Keys
REQUIRED_FIELDS = {
    "utms": "TEXT NOT NULL",
    "temperature1": "REAL",
    "humidity1": "REAL",
    "temperature2": "REAL",
    "humidity2": "REAL",
    "temperature3": "REAL",
    "humidity3": "REAL",
    "temperatureIN": "REAL",
    "humidityIN": "REAL",
    "battery": "BOOLEAN"   # wird als 0/1 gespeichert
}

# Welche Felder sollen als Zahl geparst werden?
NUMERIC_FIELDS = {
    "temperature1",
    "humidity1",
    "temperature2",
    "humidity2",
    "temperature3",
    "humidity3",
    "temperatureIN",
    "humidityIN",
}

# Welches Feld ist der Battery-Status?
BATTERY_FIELD = "battery"

# Pflichtfeld für Zeitstempel (NOT NULL in der DB)
TIMESTAMP_FIELD = "utms"

# ---------------- TIMEOUT / MONITORING ----------------
TIMEOUT_SECONDS = 3600  # 1 Stunde ohne Daten -> Alarm

# ---------------- MAIL CONFIG ----------------
MAIL_SENDER = "roman.willi@gmx.ch"
MAIL_RECIPIENT = "roman.willi@gmx.ch"
MAIL_SUBJECT_PREFIX = "[MQTT-LOGGER]"

# ---------------- REPORTING CONFIG ----------------
REPORTS_PATH = "log/reports"
REPORTS_CONFIG_FILE = "reports.json"

# Aliase für die Sensoren im Plot-Skript:
#   Key   = Name, den du auf der Kommandozeile verwendest (Alias)
#   Value = Spaltenname in der DB (= JSON-Field vom Broker)
SENSOR_ALIASES = {
    "temp1": "temperature1",
    "hum1": "humidity1",
    "temp2": "temperature2",
    "hum2": "humidity2",
    "temp3": "temperature3",
    "hum3": "humidity3",
    "temp_in": "temperatureIN",
    "hum_in": "humidityIN",
    "battery": "battery",
}

UNIT_MAP = {
    "temperature1": "°C",
    "humidity1": "%RH",
    "temperature2": "°C",
    "humidity2": "%RH",
    "temperature3": "°C",
    "humidity3": "%RH",
    "temperatureIN": "°C",
    "humidityIN": "%RH",
    "battery": "1"
}

SENSOR_LIMITS = {
    "temperature1": (-30, 50),
    "humidity1": (0, 100),
    "temperature2": (-30, 50),
    "humidity2": (0, 100),
    "temperature3": (-30, 50),
    "humidity3": (0, 100),
    "temperatureIN": (-30, 50),
    "humidityIN": (0, 100),
    "battery": (0, 1),
}
