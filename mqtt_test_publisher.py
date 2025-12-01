import json
import time
from datetime import datetime
from paho.mqtt import publish

# --- KONFIGURATION ---
BROKER_ADDRESS = "127.0.0.1"
MQTT_TOPIC = "mobilealerts/status"

# Simulierte Sensoren (passend zu der Konfiguration in mqtt_sqlite_logger.py)
SENSOR_GARTEN_ID = "11566802925f"
SENSOR_GATEWAY_ID = "001d8c0e0851"

def generate_payload(sensor_id, temp1, hum1, temp2, battery_ok=True, temp_in=None):
    """
    Erzeugt einen simulierten Mobile Alerts JSON Payload.
    Die Werte werden teilweise absichtlich als Array formatiert,
    um die Fehlerbehandlung im Logger zu testen.
    """
    now = datetime.utcnow().isoformat(timespec='seconds') + 'Z'
    
    payload = {
        # Grundlegende Identifikationsdaten
        "id": sensor_id,
        "utms": now,
        
        # Testet die Array-Handhabung (Temp1 als Array)
        "temperature1": [temp1, temp1], 
        "humidity1": hum1,
        
        # Testet die einfache Wert-Handhabung (Temp2 als Zahl)
        "temperature2": temp2,
        
        # Testet fehlende Werte (humidity2 fehlt)
        "humidity3": 75.0,
        
        # Testet den Batteriestatus
        "battery": "OK" if battery_ok else "LOW",
    }
    
    # Fügt optionale interne Temperaturdaten hinzu
    if temp_in is not None:
        payload["temperatureIN"] = temp_in
        payload["humidityIN"] = 45.5 # Fester Wert
    
    return payload

def publish_test_data(broker):
    """Generiert und sendet mehrere Testdatensätze."""
    print(f"Starte Senden der Testdaten an Broker: {broker}")
    
    # 1. Messung für den Garten-Sensor (Normalfall)
    temp_garden = 15.3
    payload1 = generate_payload(SENSOR_GARTEN_ID, temp_garden, 60.5, 12.0)
    
    print(f"\n[1] Sende Garten-Sensor Daten ({temp_garden}°C)...")
    try:
        publish.single(MQTT_TOPIC, json.dumps(payload1), hostname=broker)
        print("   -> Gesendet.")
    except Exception as e:
        print(f"   ❌ Fehler beim Senden: {e}")

    time.sleep(1)

    # 2. Messung für das Gateway (mit interner Temperatur)
    temp_gateway = 21.5
    payload2 = generate_payload(SENSOR_GATEWAY_ID, temp_gateway, 42.1, 21.0, temp_in=temp_gateway)
    
    print(f"[2] Sende Gateway Daten ({temp_gateway}°C, mit TempIN)...")
    try:
        publish.single(MQTT_TOPIC, json.dumps(payload2), hostname=broker)
        print("   -> Gesendet.")
    except Exception as e:
        print(f"   ❌ Fehler beim Senden: {e}")

    time.sleep(1)
    
    # 3. Messung mit niedrigem Batteriestatus und Extremwert (zum Testen der Visualisierung)
    temp_extreme = -5.1
    payload3 = generate_payload(SENSOR_GARTEN_ID, temp_extreme, 95.0, -6.0, battery_ok=False)
    
    print(f"[3] Sende Garten-Sensor Extremwert ({temp_extreme}°C, LOW Battery)...")
    try:
        publish.single(MQTT_TOPIC, json.dumps(payload3), hostname=broker)
        print("   -> Gesendet.")
    except Exception as e:
        print(f"   ❌ Fehler beim Senden: {e}")

    print("\nAlle Testdaten gesendet.")

if __name__ == "__main__":
    publish_test_data(BROKER_ADDRESS)