# config.py

# --- MQTT & DB KONFIGURATION ---
BROKER = "127.0.0.1"
TOPIC = "mobilealerts/#"
DB_FILE = "log/mobilealerts.db"

# --- MAIL & TIMEOUT KONFIGURATION ---
MAIL_RECIPIENT = "ihre@emailadresse.de" 
MAIL_SENDER = "pi@mein-raspi.local"   
TIMEOUT_SECONDS = 3600  # 1 Stunde

# ⭐ SPALTENNAMEN-KONFIGURATION ⭐
# Logischer Name (Key) : Datenbank-Spaltenname (Value)
COLUMN_NAMES = {
    "id": "id",
    "timestamp_iso": "timestamp_iso",
    "datum_utc": "datum_utc",
    "uhrzeit_utc": "uhrzeit_utc",
    "gateway_id": "gateway_id",
    "temp1": "temp_aussen1", 
    "feuchte1": "feuchte_aussen1", 
    "temp2": "temp_aussen2",
    "feuchte2": "feuchte_aussen2",
    "temp3": "temp_aussen3",
    "feuchte3": "feuchte_aussen3",
    "temp_in": "temp_innen", 
    "feuchte_in": "feuchte_innen", 
    "battery_ok": "batteriestatus", 
    "created_at": "created_at"
}

# Reihenfolge der Spalten für INSERT-Statements
INSERT_COLUMNS = [
    COLUMN_NAMES["timestamp_iso"], COLUMN_NAMES["datum_utc"], COLUMN_NAMES["uhrzeit_utc"], 
    COLUMN_NAMES["gateway_id"],
    COLUMN_NAMES["temp1"], COLUMN_NAMES["feuchte1"], 
    COLUMN_NAMES["temp2"], COLUMN_NAMES["feuchte2"], 
    COLUMN_NAMES["temp3"], COLUMN_NAMES["feuchte3"], 
    COLUMN_NAMES["temp_in"], COLUMN_NAMES["feuchte_in"], 
    COLUMN_NAMES["battery_ok"]
]