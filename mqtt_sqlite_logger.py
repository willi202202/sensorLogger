# mqtt_sqlite_logger.py
import json
import sqlite3
import datetime
from paho.mqtt import client as mqtt

# --- KONFIGURATION ---
BROKER = "127.0.0.1"
TOPIC  = "mobilealerts/#"
DB_FILE = "log/mobilealerts.db"

# WICHTIG: Definiere hier deine Sensor-Mappings!
SENSOR_MAP = {
    "11566802925f": "Garten_Sensor",
    "001d8c0e0851": "Gateway_ID",
    # Füge hier weitere Sensor-IDs und deren Namen hinzu!
}

# --- FUNKTIONEN ZUR DATENBANKVERWALTUNG ---

def initialize_database():
    """Erstellt die Datenbankverbindung und die Tabelle, falls sie nicht existiert."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # SQL-Befehl zur Erstellung der Tabelle 'measurements'
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS measurements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp_iso TEXT NOT NULL,
                datum_utc TEXT,
                uhrzeit_utc TEXT,
                sensor_name TEXT,
                sensor_id_raw TEXT,
                temp1 REAL,
                feuchte1 REAL,
                temp2 REAL,
                feuchte2 REAL,
                temp3 REAL,
                feuchte3 REAL,
                temp_in REAL,
                feuchte_in REAL,
                battery_ok BOOLEAN,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()
        print(f"✅ Datenbank {DB_FILE} initialisiert.")
        
    except sqlite3.Error as e:
        print(f"❌ Fehler bei der Datenbankinitialisierung: {e}")

def insert_record(record):
    """Fügt einen einzelnen Messdatensatz in die Datenbank ein."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # SQLite kann Spaltennamen direkt aus einem Dictionary (record) verwenden
        # Wir definieren die Spalten explizit, um die Reihenfolge zu garantieren
        columns = [
            "timestamp_iso", "datum_utc", "uhrzeit_utc", "sensor_name", "sensor_id_raw",
            "temp1", "feuchte1", "temp2", "feuchte2", "temp3", "feuchte3", 
            "temp_in", "feuchte_in", "battery_ok"
        ]
        
        # Erstellt die Platzhalter: (?, ?, ?, ...)
        placeholders = ', '.join(['?'] * len(columns))
        
        # Erstellt die Werte-Liste basierend auf der Spaltenreihenfolge
        values = [record.get(col) for col in columns]

        sql = f"INSERT INTO measurements ({', '.join(columns)}) VALUES ({placeholders})"
        cursor.execute(sql, values)
        
        conn.commit()
        conn.close()
        
    except sqlite3.Error as e:
        print(f"❌ Fehler beim Einfügen des Datensatzes: {e}")

# --- FUNKTION ZUR FEHLERBEHANDLUNG ---

def safe_extract_value(data, key):
    """
    Extrahiert einen Messwert robust:
    1. Holt den Wert zum Key.
    2. Wenn es ein Array ist, nimmt es den ersten Wert [0].
    3. Wenn es ein einzelner Wert ist, gibt es diesen zurück.
    4. Gibt None zurück, wenn der Key fehlt oder der Wert ungültig ist.
    """
    value = data.get(key)
    
    if isinstance(value, list):
        # Fall 1: Wert liegt als Array vor (wie in deinem Beispiel)
        return value[0] if value else None
    elif isinstance(value, (int, float)):
        # Fall 2: Wert liegt als einfacher numerischer Typ vor
        return value
    elif isinstance(value, str) and value.replace('.', '', 1).isdigit():
        # Fall 3: Wert liegt als parsbarer String vor
        try:
            return float(value)
        except ValueError:
            return None
    
    # Fall 4: Wert fehlt oder ist None
    return None

# --- MQTT HANDLER ---

def on_connect(client, userdata, flags, rc):
    print("✅ Verbunden mit MQTT-Broker, Statuscode:", rc)
    client.subscribe(TOPIC)

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
        
        if isinstance(payload, dict):
            
            # --- 1. Zeitstempel-Verarbeitung ---
            utc_timestamp_iso = payload.get("utms", "")
            datum = utc_timestamp_iso[:10] if utc_timestamp_iso else None
            uhrzeit = utc_timestamp_iso[11:19] if utc_timestamp_iso else None

            # --- 2. Batteriestatus-Verarbeitung ---
            batterie_ok = payload.get("battery", "").lower() == "ok" 
            
            # --- 3. Sensor-Mapping ---
            sensor_id_raw = payload.get("id")
            sensor_name = SENSOR_MAP.get(sensor_id_raw, sensor_id_raw)

            # --- 4. Daten-Record erstellen (mit robuster Extraktion) ---
            record = {
                "timestamp_iso": utc_timestamp_iso,
                "datum_utc": datum,
                "uhrzeit_utc": uhrzeit,
                "sensor_name": sensor_name,
                "sensor_id_raw": sensor_id_raw,
                
                # Robuste Extraktion der numerischen Werte
                "temp1": safe_extract_value(payload, "temperature1"),
                "feuchte1": safe_extract_value(payload, "humidity1"),
                "temp2": safe_extract_value(payload, "temperature2"),
                "feuchte2": safe_extract_value(payload, "humidity2"),
                "temp3": safe_extract_value(payload, "temperature3"),
                "feuchte3": safe_extract_value(payload, "humidity3"),
                "temp_in": safe_extract_value(payload, "temperatureIN"),
                "feuchte_in": safe_extract_value(payload, "humidityIN"),
                
                "battery_ok": batterie_ok
            }
            
            # 5. In SQLite-Datenbank einfügen
            insert_record(record)
            
            print(f"✅ DB: {sensor_name} | Temp1: {record['temp1']} | Eingefügt.")
        
        else:
            print(f"ℹ️ {msg.topic}: {msg.payload.decode('utf-8')} (Nicht-JSON-Nachricht ignoriert)")
            
    except json.JSONDecodeError:
        print(f"❌ {msg.topic}: Ungültiges JSON-Format.")
    except Exception as e:
        print(f"❌ Allgemeiner Fehler bei on_message: {e}")


# --- HAUPTPROGRAMM ---
# 1. Datenbank initialisieren
initialize_database()

# 2. MQTT-Client starten
client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message
print(f"Verbinde zu Broker {BROKER}...")

try:
    client.connect(BROKER, 1883, 60)
    client.loop_forever()
except Exception as e:
    print(f"❌ Verbindungsfehler: {e}")