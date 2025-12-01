# mqtt_csv_logger.py
import json
import csv
import os
from paho.mqtt import client as mqtt

# --- KONFIGURATION ---
BROKER = "127.0.0.1"
TOPIC  = "mobilealerts/#"
CSV_FILE = "mobilealerts_log.csv"
FIELDNAMES = ["Zeitstempel_UTC", "Sensor_ID", "Temp1", "Feuchte1", "Temp2", "Feuchte2", "Temp3", "Feuchte3", "TempIN", "FeuchteIN", "Batterie"]

# --- CSV FUNKTION ---
def save_to_csv(data):
    """Speichert die extrahierten Daten in der CSV-Datei."""
    
    # Prüfen, ob die Datei existiert, um Header nur einmal zu schreiben
    file_exists = os.path.isfile(CSV_FILE)
    
    try:
        with open(CSV_FILE, 'a', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=FIELDNAMES)
            
            # Schreibe Header, falls Datei neu ist
            if not file_exists:
                writer.writeheader()
            
            # Schreibe die Datenzeile
            writer.writerow(data)
            
    except Exception as e:
        print(f"❌ Fehler beim Schreiben der CSV-Datei: {e}")

# --- MQTT HANDLER ---
def on_connect(client, userdata, flags, rc):
    print("✅ Verbunden mit MQTT-Broker, Statuscode:", rc)
    client.subscribe(TOPIC)

def on_message(client, userdata, msg):
    try:
        # Versuch, die Nachricht als JSON zu dekodieren
        payload = json.loads(msg.payload.decode("utf-8"))
        
        # Nur fortfahren, wenn die Nachricht ein JSON-Objekt und keine einfache Zeichenkette ist
        if isinstance(payload, dict):
            
            # 1. Daten extrahieren und flach machen (flattern)
            record = {
                "Zeitstempel_UTC": payload.get("utms"),
                "Sensor_ID": payload.get("id"),
                # Wir nehmen den ersten Wert des Arrays (aktuellster Wert)
                "Temp1": payload.get("temperature1", [None])[0],
                "Feuchte1": payload.get("humidity1", [None])[0],
                "Temp2": payload.get("temperature2", [None])[0],
                "Feuchte2": payload.get("humidity2", [None])[0],
                "Temp3": payload.get("temperature3", [None])[0],
                "Feuchte3": payload.get("humidity3", [None])[0],
                "TempIN": payload.get("temperatureIN", [None])[0],
                "FeuchteIN": payload.get("humidityIN", [None])[0],
                "Batterie": payload.get("battery"),
            }
            
            # 2. In CSV speichern
            save_to_csv(record)
            
            print(f"✅ {msg.topic}: Daten gespeichert. Temperatur1: {record['Temp1']}")
        
        else:
            # Für nicht-JSON-Nachrichten
            print(f"ℹ️ {msg.topic}: {payload} (Nicht-JSON-Nachricht ignoriert)")
            
    except json.JSONDecodeError:
        print(f"❌ {msg.topic}: Ungültiges JSON-Format.")
    except Exception as e:
        print(f"❌ Allgemeiner Fehler bei on_message: {e}")


# --- HAUPTPROGRAMM ---
client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message
print(f"Verbinde zu Broker {BROKER}...")
try:
    client.connect(BROKER, 1883, 60)
    client.loop_forever()
except Exception as e:
    print(f"❌ Verbindungsfehler: {e}")