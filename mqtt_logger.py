#!/usr/bin/env python3
# mqtt_logger.py
#
# MQTT -> SQLite logger fuer zwei (oder mehr) Sensoren:
# - Routing via Topic: mobilealerts/<sensor_id>/json
# - Insert exakt passend zu bestehenden Tabellen (kein CREATE TABLE!)
# - Schema-Check beim Start: fehlende Spalten -> Warnung + Sensor deaktiviert (statt Crash)
# - Timeout-Alarm pro Sensor (1x pro Tag)

import time
import datetime
import sys
import json
import sqlite3
import subprocess

from paho.mqtt import client as mqtt
import config


# --------------------------
# Helpers
# --------------------------

def safe_extract_value(data, key, list_policy="first"):
    """
    Extrahiert Zahlen robust aus JSON:
    - int/float -> float
    - numeric string -> float
    - list -> policy: first/last/avg (z.B. [1.9, 1.9])
    """
    if key not in data:
        return None

    value = data[key]

    if isinstance(value, list):
        if not value:
            return None

        nums = []
        for v in value:
            if isinstance(v, (int, float)):
                nums.append(float(v))
            elif isinstance(v, str):
                s = v.strip().replace(",", ".")
                try:
                    nums.append(float(s))
                except ValueError:
                    pass

        if not nums:
            return None

        if list_policy == "last":
            return nums[-1]
        if list_policy == "avg":
            return sum(nums) / len(nums)
        return nums[0]  # default: first

    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, str):
        s = value.strip().replace(",", ".")
        try:
            return float(s)
        except ValueError:
            return None

    return None


def normalize_boolish(value):
    """
    Normalisiert Battery/Boolean-ish nach 0/1 oder None.
    Akzeptiert bool, 0/1, "ok/low", "true/false", etc.
    """
    if value is None:
        return None

    if isinstance(value, bool):
        return int(value)

    if isinstance(value, int):
        return 1 if value != 0 else 0

    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("ok", "good", "true", "ja", "yes", "1", "on"):
            return 1
        if v in ("low", "bad", "false", "nein", "no", "0", "off"):
            return 0
        try:
            i = int(v)
            return 1 if i != 0 else 0
        except ValueError:
            return None

    return None


def get_table_columns(db_file: str, table: str) -> set[str]:
    conn = sqlite3.connect(db_file)
    try:
        cur = conn.cursor()
        cur.execute(f"PRAGMA table_info({table})")
        rows = cur.fetchall()
        # row: (cid, name, type, notnull, dflt_value, pk)
        return {r[1] for r in rows}
    finally:
        conn.close()


def check_schema(db_file: str, sensors_cfg: dict) -> dict[str, str]:
    """
    Prueft, ob die erwarteten Spalten vorhanden sind.
    Rueckgabe: sensor_id -> problem_text (nur wenn etwas fehlt)
    """
    problems = {}
    for sid, scfg in sensors_cfg.items():
        table = scfg["table"]
        expected = set(scfg["fields"])  # exakt deine DB-Spalten (ohne id)
        actual = get_table_columns(db_file, table)

        missing = sorted(expected - actual)
        if missing:
            problems[sid] = f"Table '{table}' missing columns: {', '.join(missing)}"

    return problems


# --------------------------
# DB
# --------------------------

class DatabaseManager:
    """
    Insert-only DB Wrapper, passend zu bestehenden Tabellen.
    """
    def __init__(self, db_file: str, table: str, fields: list[str]):
        self.db_file = db_file
        self.table = table
        self.fields = fields[:]  # Reihenfolge fuer INSERT

    def _connect(self):
        return sqlite3.connect(self.db_file)

    def insert(self, record: dict):
        cols = self.fields
        values = [record.get(c) for c in cols]

        placeholders = ", ".join("?" for _ in cols)
        cols_sql = ", ".join(cols)

        sql = f"INSERT INTO {self.table} ({cols_sql}) VALUES ({placeholders})"

        for _ in range(5):
            try:
                conn = self._connect()
                cur = conn.cursor()
                cur.execute(sql, values)
                conn.commit()
                conn.close()
                return
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e).lower() or "locked" in str(e).lower():
                    time.sleep(0.2)
                    continue
                raise

        print(f"❌ INSERT endgueltig fehlgeschlagen ({self.table}) – database remained locked")


# --------------------------
# Mail
# --------------------------

class EmailNotifier:
    """
    Mail senden + Begrenzen von Alarm-Mails: max. 1x pro Tag pro Key.
    """
    def __init__(self, recipient: str, sender: str | None = None, subject_prefix: str = ""):
        self.recipient = recipient
        self.sender = sender
        self.subject_prefix = subject_prefix or ""
        self._last_error_mail_date = {}  # key -> YYYY-MM-DD

    def _build_subject(self, subject: str) -> str:
        return f"{self.subject_prefix} {subject}".strip()

    def send_mail(self, subject: str, body: str) -> bool:
        full_subject = self._build_subject(subject)

        try:
            cmd = ["mail", "-s", full_subject, self.recipient]
            subprocess.run(
                cmd,
                input=body.encode("utf-8"),
                capture_output=True,
                check=True,
                env=None,
            )
            print(f"📧 E-Mail gesendet: '{full_subject}'")
            return True

        except subprocess.CalledProcessError as e:
            print(f"❌ Fehler beim Senden der E-Mail (mailutils/msmtp): {e}")
            return False
        except FileNotFoundError:
            print("❌ Fehler: Der 'mail'-Befehl wurde nicht gefunden. Ist mailutils installiert?")
            return False
        except Exception as e:
            print(f"❌ Unbekannter Fehler beim Senden der E-Mail: {e}")
            return False

    def send_error_once_per_day(self, key: str, subject: str, body: str):
        today = datetime.date.today().isoformat()
        if self._last_error_mail_date.get(key) == today:
            return
        if self.send_mail(subject, body):
            self._last_error_mail_date[key] = today

    def clear_error_day(self, key: str):
        if key in self._last_error_mail_date:
            del self._last_error_mail_date[key]


# --------------------------
# Logger
# --------------------------

class MQTTLogger:
    def __init__(self):
        self.list_policy = getattr(config, "LIST_POLICY", "first")

        # Sensor state: last receive time (epoch)
        self.last_message_time: dict[str, float] = {}

        # Active sensors after schema check
        self.active_sensors: set[str] = set()

        # DB managers per sensor id
        self.dbs: dict[str, DatabaseManager] = {}
        for sid, scfg in config.SENSORS.items():
            self.dbs[sid] = DatabaseManager(
                db_file=config.DB_FILE,
                table=scfg["table"],
                fields=scfg["fields"],
            )

        self.mailer = EmailNotifier(
            recipient=config.MAIL_RECIPIENT,
            sender=getattr(config, "MAIL_SENDER", None),
            subject_prefix=getattr(config, "MAIL_SUBJECT_PREFIX", ""),
        )

        self.client = mqtt.Client(client_id=getattr(config, "CLIENT_ID", "mqtt_sqlite_logger"))
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def _sensor_id_from_topic(self, topic: str) -> str | None:
        # erwartet: mobilealerts/<id>/json
        parts = topic.split("/")
        if len(parts) >= 3 and parts[0] == "mobilealerts":
            return parts[1]
        return None

    def on_connect(self, client, userdata, flags, rc):
        print(f"✅ Verbunden mit MQTT-Broker {config.BROKER}:{config.BROKER_PORT}, Statuscode: {rc}")
        client.subscribe(config.TOPIC)
        print(f"📡 Subscribed auf Topic: {config.TOPIC}")

    def on_message(self, client, userdata, msg):
        sensor_id = self._sensor_id_from_topic(msg.topic)

        if sensor_id not in self.active_sensors:
            # Unbekannt oder wegen Schema-Problem deaktiviert
            return

        scfg = config.SENSORS[sensor_id]

        try:
            payload_str = msg.payload.decode("utf-8", errors="replace")
            payload = json.loads(payload_str)

            if not isinstance(payload, dict):
                print(f"ℹ️ {msg.topic}: Nicht-JSON-Objekt empfangen, wird ignoriert.")
                return

            ts_key = getattr(config, "TIMESTAMP_FIELD", "utms")
            utms = payload.get(ts_key)
            if not utms:
                print(f"⚠️ Sensor {sensor_id}: Payload ohne '{ts_key}', wird ignoriert.")
                return

            record = {"utms": utms}

            numeric_fields = scfg.get("numeric_fields", set())
            battery_field = getattr(config, "BATTERY_FIELD", "battery")

            for field in scfg["fields"]:
                if field == "utms":
                    continue

                if field == battery_field:
                    record[field] = normalize_boolish(payload.get(field))
                elif field in numeric_fields:
                    record[field] = safe_extract_value(payload, field, self.list_policy)
                else:
                    record[field] = payload.get(field)

            # In DB schreiben
            self.dbs[sensor_id].insert(record)

            # Log-Ausgabe kompakt
            if "temperatureIN" in record:
                print(f"✅ {sensor_id} -> {scfg['table']} | tempIN={record.get('temperatureIN')}")
            elif "windSpeed" in record:
                print(f"✅ {sensor_id} -> {scfg['table']} | wind={record.get('windSpeed')} gust={record.get('gustSpeed')}")
            else:
                print(f"✅ {sensor_id} -> {scfg['table']} | inserted")

            # Timeout-Status pro Sensor
            self.last_message_time[sensor_id] = time.time()
            self.mailer.clear_error_day(sensor_id)

        except json.JSONDecodeError:
            print(f"❌ {msg.topic}: Ungueltiges JSON-Format.")
        except Exception as e:
            print(f"❌ Allgemeiner Fehler in on_message ({sensor_id}): {e}")

    def check_timeout(self):
        """
        Alarm pro Sensor, wenn seit TIMEOUT_SECONDS keine Daten mehr eingetroffen sind.
        Alarm-Mail max. 1x pro Tag pro Sensor.
        """
        now = time.time()

        for sensor_id in sorted(self.active_sensors):
            last = self.last_message_time.get(sensor_id)
            if last is None:
                # noch nie Daten gesehen -> keinen Alarm
                continue

            diff = now - last
            if diff > config.TIMEOUT_SECONDS:
                hours = round(diff / 3600, 2)
                last_ts = datetime.datetime.fromtimestamp(last).isoformat()

                body = (
                    f"SEIT {hours} STUNDEN KEINE NEUEN MQTT-DATEN (Sensor {sensor_id})!\n"
                    f"Letzter Empfangszeitpunkt: {last_ts}\n"
                    f"Broker: {config.BROKER}:{config.BROKER_PORT}\n"
                    f"Topic: {config.TOPIC}\n"
                    f"Datenbank: {config.DB_FILE}\n"
                    f"Tabelle: {config.SENSORS[sensor_id]['table']}\n"
                )

                self.mailer.send_error_once_per_day(
                    sensor_id,
                    f"[ALARM] MQTT Daten-Timeout ({sensor_id})",
                    body,
                )

    def start(self):
        # Schema check -> aktive Sensoren bestimmen
        try:
            problems = check_schema(config.DB_FILE, config.SENSORS)
        except Exception as e:
            print(f"❌ Schema-Check fehlgeschlagen: {e}")
            sys.exit(1)

        all_sensors = set(config.SENSORS.keys())
        self.active_sensors = all_sensors - set(problems.keys())

        for sid, msg in problems.items():
            warn = f"⚠️ SCHEMA WARNING (Sensor {sid}): {msg}"
            print(warn)
            # optional: Mail einmalig (kein daily-limit, absichtlich)
            self.mailer.send_mail(
                subject="[WARN] DB Schema mismatch",
                body=f"{warn}\nDB: {config.DB_FILE}\n",
            )

        if not self.active_sensors:
            print("❌ Keine aktiven Sensoren (Schema passt nicht). Abbruch.")
            sys.exit(2)

        print(f"✅ Active sensors: {', '.join(sorted(self.active_sensors))}")

        # MQTT verbinden
        print(f"Verbinde zu Broker {config.BROKER}:{config.BROKER_PORT} ...")
        try:
            self.client.connect(config.BROKER, config.BROKER_PORT, 60)
        except Exception as e:
            print(f"❌ Konnte nicht zum MQTT-Broker verbinden: {e}")
            sys.exit(1)

        # Info-Mail beim Start
        start_time_iso = datetime.datetime.now().isoformat()
        self.mailer.send_mail(
            subject="[INFO] MQTT Logger gestartet",
            body=(
                f"Der MQTT-SQLite-Logger wurde gestartet.\n"
                f"Startzeit: {start_time_iso}\n"
                f"Broker: {config.BROKER}:{config.BROKER_PORT}\n"
                f"Topic: {config.TOPIC}\n"
                f"Datenbank: {config.DB_FILE}\n"
                f"Aktive Sensoren: {', '.join(sorted(self.active_sensors))}\n"
            ),
        )

        # MQTT loop
        self.client.loop_start()
        print("🏃 MQTT-Logger laeuft. Druecke Ctrl+C zum Beenden.")

        try:
            while True:
                time.sleep(60)
                self.check_timeout()

        except KeyboardInterrupt:
            print("\n🛑 Beende Logger (KeyboardInterrupt).")
        except Exception as e:
            print(f"❌ KRITISCHER FEHLER: {e}")
            self.mailer.send_error_once_per_day(
                "global",
                "[KRITISCH] MQTT Logger beendet",
                f"Der MQTT-Logger ist aufgrund eines kritischen Fehlers gestoppt worden:\n{e}",
            )
        finally:
            self.client.loop_stop()
            self.client.disconnect()
            print("🔌 MQTT-Verbindung getrennt.")


if __name__ == "__main__":
    MQTTLogger().start()
