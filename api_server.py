# api_server.py
import logging
import os
from flask import Flask, jsonify, request
from evaluation.generate_reports import generate_reports
from alarm_config import AlarmConfig

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("api")

app = Flask(__name__)

# Lade Alarm-Konfiguration
ALARM_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "HTML", "alarm_button.json")
try:
    alarm_config = AlarmConfig.from_json(ALARM_CONFIG_PATH)
    log.info(f"Alarm-Konfiguration geladen: {alarm_config}")
except Exception as e:
    log.warning(f"Alarm-Konfiguration konnte nicht geladen werden: {e}")
    alarm_config = None

app = Flask(__name__)


@app.route("/update", methods=["POST"])
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
    if alarm_config is None:
        return jsonify({"ok": False, "error": "Alarm-Konfiguration nicht geladen"}), 500
    return jsonify({"ok": True, "alarms": alarm_config.to_dict()}), 200


@app.route("/api/alarms", methods=["POST"])
def update_alarms():
    """Update Alarm-Einstellungen"""
    if alarm_config is None:
        return jsonify({"ok": False, "error": "Alarm-Konfiguration nicht geladen"}), 500

    try:
        data = request.get_json()
        
        # Aktualisiere Alarm-Einstellungen
        if "enbutton" in data:
            for btn_data in data["enbutton"]:
                try:
                    alarm = alarm_config.get_alarm_by_sensor(btn_data["sensor_alias"])
                    alarm.default = btn_data.get("default", alarm.default)
                    alarm.default_alarm = tuple(btn_data.get("default_alarm", alarm.default_alarm))
                except ValueError:
                    log.warning(f"Sensor nicht gefunden: {btn_data['sensor_alias']}")

        # Speichere in JSON
        alarm_config.to_json(ALARM_CONFIG_PATH)
        log.info("Alarm-Einstellungen aktualisiert und gespeichert")
        
        return jsonify({"ok": True, "message": "Alarm-Einstellungen gespeichert"}), 200

    except Exception as e:
        log.exception("Fehler beim Update der Alarm-Einstellungen")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/alarms/<sensor_alias>", methods=["GET"])
def get_alarm_by_sensor(sensor_alias):
    """Gebe Alarm-Einstellung für einen Sensor zurück"""
    if alarm_config is None:
        return jsonify({"ok": False, "error": "Alarm-Konfiguration nicht geladen"}), 500

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
