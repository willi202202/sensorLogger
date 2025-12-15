# config.py

# ---------------- MQTT CONFIG ----------------
BROKER = "127.0.0.1"
BROKER_PORT = 1883
TOPIC = "mobilealerts/+/json"

# ---------------- DATABASE CONFIG ----------------
DB_FILE = "log/mobilealerts.db"

# ---------------- MAIL CONFIG ----------------
MAIL_SENDER = "roman.willi@gmx.ch"
MAIL_RECIPIENT = "roman.willi@gmx.ch"
MAIL_SUBJECT_PREFIX = "[MQTT-LOGGER]"
TIMEOUT_SECONDS = 60 * 60 * 24      # 24h
DB_SIZE_WARN_MB = 500               # Warnschwelle
DB_SIZE_CRIT_MB = 900               # kritisch
DB_SIZE_CHECK_EVERY_MIN = 60 * 60   # z.B. stündlich pruefen

# ---------------- SENSOR CONFIG ----------------
TIMESTAMP_FIELD = "utms"
BATTERY_FIELD = "battery"

# Wie sollen Listen [x,y] behandelt werden
LIST_POLICY = "first"   # "first" | "last" | "avg"

SENSORS = {
    "11566802925f": {
        "table": "measurements_th",
        "fields": [
            "utms",
            "temperature1",
            "humidity1",
            "temperature2",
            "humidity2",
            "temperature3",
            "humidity3",
            "temperatureIN",
            "humidityIN",
            "battery",
        ],
        "numeric_fields": {
            "temperature1", "humidity1",
            "temperature2", "humidity2",
            "temperature3", "humidity3",
            "temperatureIN", "humidityIN",
        },
    },

    "0b55aada036f": {
        "table": "measurements_w",
        "fields": [
            "utms",
            "directionDegree",
            "direction",
            "windSpeed",
            "gustSpeed",
            "battery",
        ],
        "numeric_fields": {
            "directionDegree",
            "windSpeed",
            "gustSpeed",
        },
    },
}
