# api_server.py
import logging
import os
import json
from flask import Flask, jsonify, request
from evaluation.generate_reports import generate_reports
from alarm_config import AlarmConfig

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("api")

app = Flask(__name__)

# CORS Header manuell hinzufügen
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

# In-Memory Alarm-Konfiguration (wird von Frontend aktualisiert)
# Laden der Default-Einstellungen aus alarm_button_config.json beim Start
ALARM_JSON_PATH = os.path.join(os.path.dirname(__file__), "config", "alarm_button_config.json")

try:
    if os.path.exists(ALARM_JSON_PATH):
        with open(ALARM_JSON_PATH, "r", encoding="utf-8") as f:
            alarm_data = json.load(f)
        alarm_config = AlarmConfig.from_dict(alarm_data)
        log.info(f"✅ Alarm-Konfiguration vom Start geladen: {ALARM_JSON_PATH}")
        print(f"✅ Alarm-Konfiguration geladen: {alarm_config}", flush=True)
    else:
        alarm_config = AlarmConfig(enbutton=[])
        log.warning(f"⚠️ alarm_button_config.json nicht gefunden: {ALARM_JSON_PATH}")
        print(f"⚠️ alarm_button_config.json nicht gefunden", flush=True)
except Exception as e:
    log.error(f"❌ Fehler beim Laden von alarm_button_config.json: {e}")
    print(f"❌ Fehler beim Laden von alarm_button_config.json: {e}", flush=True)
    alarm_config = AlarmConfig(enbutton=[])


@app.route("/api/update", methods=["POST"])
def update():
    """Update reports endpoint"""
    try:
        generate_reports()
        return jsonify({"ok": True}), 200
    except Exception as e:
        log.exception("Update fehlgeschlagen")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/alarms", methods=["GET"])
def get_alarms():
    """Gebe alle Alarm-Einstellungen zurück"""
    return jsonify({"ok": True, "alarms": alarm_config.to_dict()}), 200


@app.route("/api/alarms", methods=["POST"])
def update_alarms():
    """Update Alarm-Einstellungen (von Frontend)"""
    global alarm_config
    
    try:
        data = request.get_json()
        print(f"📨 POST /api/alarms: {data}")  # Debug
        
        # Ersetze die komplette Konfiguration mit den Daten vom Frontend
        alarm_config = AlarmConfig.from_dict(data)
        log.info("Alarm-Einstellungen vom Frontend aktualisiert")
        print(f"✅ Konfiguration aktualisiert: {alarm_config}\n")  # Debug
        
        return jsonify({"ok": True, "message": "Alarm-Einstellungen gespeichert", "alarms": alarm_config.to_dict()}), 200

    except Exception as e:
        print(f"❌ FEHLER in POST /api/alarms: {e}\n")  # Debug
        log.exception("Fehler beim Update der Alarm-Einstellungen")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/alarms/<sensor_alias>", methods=["GET"])
def get_alarm_by_sensor(sensor_alias):
    """Gebe Alarm-Einstellung für einen Sensor zurück"""
    try:
        alarm = alarm_config.get_alarm_by_sensor(sensor_alias)
        return jsonify({"ok": True, "alarm": alarm.to_dict()}), 200
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 404


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({"ok": False, "error": "Not found"}), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    log.exception("Interner Fehler")
    return jsonify({"ok": False, "error": "Internal server error"}), 500


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8001, debug=False)
