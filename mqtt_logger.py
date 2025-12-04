# mqtt_logger.py
import time
import datetime
import sys

from paho.mqtt import client as mqtt

# Importiere Konfiguration und Funktionen
import config 
import utils

# Globale Status-Variable
LAST_MESSAGE_TIME = time.time() 

# --- MQTT HANDLER ---

def on_connect(client, userdata, flags, rc):
    print("✅ Verbunden mit MQTT-Broker, Statuscode:", rc)
    client.subscribe(config.TOPIC)

def on_message(client, userdata, msg):
    global LAST_MESSAGE_TIME
    
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
        
        if isinstance(payload, dict):
            # --- Datenverarbeitung ---
            utc_timestamp_iso = payload.get("utms", "")
            datum = utc_timestamp_iso[:10] if utc_timestamp_iso else None
            uhrzeit = utc_timestamp_iso[11:19] if utc_timestamp_iso else None
            batterie_ok = payload.get("battery", "").lower() == "ok"
            gateway_id = payload.get("id")

            record = {
                "timestamp_iso": utc_timestamp_iso,
                "datum_utc": datum,
                "uhrzeit_utc": uhrzeit,
                "gateway_id": gateway_id,
                
                # Verwende utils-Funktion zur Extraktion
                "temp1": utils.safe_extract_value(payload, "temperature1"),
                "feuchte1": utils.safe_extract_value(payload, "humidity1"),
                "temp2": utils.safe_extract_value(payload, "temperature2"),
                "feuchte2": utils.safe_extract_value(payload, "humidity2"),
                "temp3": utils.safe_extract_value(payload, "temperature3"),
                "feuchte3": utils.safe_extract_value(payload, "humidity3"),
                "temp_in": utils.safe_extract_value(payload, "temperatureIN"),
                "feuchte_in": utils.safe_extract_value(payload, "humidityIN"),
                
                "battery_ok": batterie_ok
            }
            
            # 5. In SQLite-Datenbank einfügen
            utils.insert_record(record)
            
            print(f"✅ id: {gateway_id} | temp_in: {record['temp_in']} | Eingefügt.")
            
            # Zeitstempel zurücksetzen und Fehler-Flag aufheben
            LAST_MESSAGE_TIME = time.time()
            utils.LAST_ERROR_MAIL_DATE = None 
        
        else:
            print(f"ℹ️ {msg.topic}: {msg.payload.decode('utf-8')} (Nicht-JSON-Nachricht ignoriert)")
            
    except json.JSONDecodeError:
        print(f"❌ {msg.topic}: Ungültiges JSON-Format.")
    except Exception as e:
        print(f"❌ Allgemeiner Fehler bei on_message: {e}")


# --- HAUPTPROGRAMM ---

def main():
    """Startet den Logger und überwacht den Timeout."""
    global LAST_MESSAGE_TIME
    
    # 1. Datenbank initialisieren
    utils.initialize_database()

    # 2. MQTT-Client starten
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    print(f"Verbinde zu Broker {config.BROKER}...")

    try:
        client.connect(config.BROKER, 1883, 60)
        
        # ⭐ Status-E-Mail beim Start
        start_time_iso = datetime.datetime.now().isoformat()
        utils.send_mail(
            subject="[INFO] MQTT Logger gestartet",
            body=f"Der MQTT-SQLite-Logger wurde erfolgreich gestartet und verbindet sich.\nStartzeit: {start_time_iso}\nBroker: {config.BROKER}"
        )
        
        client.loop_start() # Startet den Client-Thread
        
        # 3. Haupt-Timeout-Schleife
        while True:
            time.sleep(60) # Alle 60 Sekunden prüfen
            
            current_time = time.time()
            
            if (current_time - LAST_MESSAGE_TIME) > config.TIMEOUT_SECONDS:
                timeout_duration = round((current_time - LAST_MESSAGE_TIME) / 3600, 2)
                
                body = (
                    f"SEIT {timeout_duration} STUNDEN KEINE NEUEN DATEN EMPFANGEN!\n"
                    f"Letzter Empfangszeitpunkt: {datetime.datetime.fromtimestamp(LAST_MESSAGE_TIME).isoformat()}\n"
                    f"Broker: {config.BROKER}"
                )
                
                utils.check_and_send_error_mail("[ALARM] MQTT Daten-Timeout", body)
                
    except Exception as e:
        print(f"❌ KRITISCHER FEHLER: {e}")
        # Sende Mail bei kritischem Fehler und beende das Programm
        utils.check_and_send_error_mail(
            subject="[KRITISCH] MQTT Logger beendet",
            body=f"Der MQTT-Logger ist aufgrund eines kritischen Fehlers gestoppt worden:\n{e}"
        )
        sys.exit(1)

if __name__ == "__main__":
    main()