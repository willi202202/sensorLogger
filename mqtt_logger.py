#!/usr/bin/env python3
# mqtt_logger.py

import time
import datetime
import sys
import json
import sqlite3
import subprocess

from paho.mqtt import client as mqtt

import config


def safe_extract_value(data, key):
    """
    Extrahiert einen Messwert robust aus dem JSON-Payload.
    Unterstützt int, float, string-Zahlen und 1-elementige Listen.
    """
    if key not in data:
        return None

    value = data[key]

    # Wenn Liste: ersten Eintrag nehmen (z.B. ["21.3"])
    if isinstance(value, list):
        if not value:
            return None
        value = value[0]

    # ints/floats direkt zurückgeben
    if isinstance(value, (int, float)):
        return value

    # Strings versuchen zu Float zu parsen
    if isinstance(value, str):
        s = value.strip().replace(",", ".")
        try:
            return float(s)
        except ValueError:
            return None

    return None


def normalize_battery(value):
    """
    Normalisiert den Battery-Status auf int(0/1) oder None.
    Akzeptiert bool, "ok"/"low", "true"/"false", 0/1 etc.
    """
    if value is None:
        return None

    # bool direkt
    if isinstance(value, bool):
        return int(value)

    # int 0/1
    if isinstance(value, int):
        return 1 if value != 0 else 0

    # String
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("ok", "good", "true", "ja", "yes"):
            return 1
        if v in ("low", "bad", "false", "nein", "no"):
            return 0
        # Fallback: versuchen int
        try:
            i = int(v)
            return 1 if i != 0 else 0
        except ValueError:
            return None

    return None


class DatabaseManager:
    """
    Kapselt alle Zugriffe auf die SQLite-Datenbank.
    DB-Spaltennamen entsprechen exakt den JSON-Keys aus config.REQUIRED_FIELDS.
    """

    def __init__(self, db_file: str, table_name: str, field_defs: dict[str, str]):
        self.db_file = db_file
        self.table_name = table_name
        self.field_defs = dict(field_defs)       # name -> SQL-Typ
        self.field_names = list(field_defs.keys())  # Reihenfolge für INSERT

    def _connect(self):
        return sqlite3.connect(self.db_file)

    def initialize(self):
        """
        Erzeugt die Tabelle, falls sie noch nicht existiert.
        Spalten- und Typdefinition kommt direkt aus config.REQUIRED_FIELDS.
        """
        columns_sql_parts = [
            f"{name} {type_}"
            for name, type_ in self.field_defs.items()
        ]
        columns_sql = ",\n                ".join(columns_sql_parts)

        create_sql = f"""
            CREATE TABLE IF NOT EXISTS {self.table_name} (
                {columns_sql}
            )
        """

        try:
            conn = self._connect()
            cur = conn.cursor()
            cur.execute(create_sql)
            conn.commit()
            conn.close()
            print(f"✅ Datenbank initialisiert: {self.db_file}, Tabelle: {self.table_name}")
        except sqlite3.Error as e:
            print(f"❌ Fehler bei der Datenbankinitialisierung: {e}")

    def insert_record(self, record: dict):
        for attempt in range(5):  # bis zu 5 Versuche
            try:
                conn = self._connect()
                cur = conn.cursor()

                columns = self.field_names
                values = [record.get(c) for c in columns]

                placeholders = ", ".join(["?"] * len(columns))
                cols_sql = ", ".join(columns)

                sql = f"INSERT INTO {self.table_name} ({cols_sql}) VALUES ({placeholders})"
                cur.execute(sql, values)

                conn.commit()
                conn.close()
                return  # Erfolgreich

            except sqlite3.OperationalError as e:
                if "database is locked" in str(e):
                    time.sleep(0.2)  # kurze Pause
                    continue
                else:
                    print(f"❌ INSERT Fehler: {e}")
                    return

        print("❌ INSERT endgültig fehlgeschlagen – database remained locked")



class EmailNotifier:
    """
    Zuständig für das Versenden von E-Mails und das Begrenzen
    von Fehler-Mails auf maximal eine pro Tag.
    """

    def __init__(self, recipient: str, sender: str | None = None, subject_prefix: str = ""):
        self.recipient = recipient
        self.sender = sender
        self.subject_prefix = subject_prefix or ""
        self.last_error_mail_date = None  # ISO-String YYYY-MM-DD

    def _build_subject(self, subject: str) -> str:
        if self.subject_prefix:
            return f"{self.subject_prefix} {subject}"
        return subject

    def send_mail(self, subject: str, body: str) -> bool:
        """
        Versendet eine E-Mail über den lokalen 'mail'-Befehl.
        """
        full_subject = self._build_subject(subject)

        try:
            command = [
                "mail",
                "-s",
                full_subject,
                self.recipient,
            ]

            env = None
            if self.sender:
                # Hier koenntest du z.B. MAILFROM via ENV oder msmtp-Konfig setzen.
                env = {}

            subprocess.run(
                command,
                input=body.encode("utf-8"),
                capture_output=True,
                check=True,
                env=env,
            )
            print(f"📧 E-Mail gesendet: '{full_subject}'.")
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

    def send_error_once_per_day(self, subject: str, body: str):
        """
        Versendet eine Fehler-Mail höchstens einmal pro Tag.
        """
        today = datetime.date.today().isoformat()
        if self.last_error_mail_date == today:
            return

        if self.send_mail(subject, body):
            self.last_error_mail_date = today


class MQTTLogger:
    """
    Hauptklasse, welche MQTT, DB und Mail-Logik zusammenführt.
    """

    def __init__(self):
        # State
        self.last_message_time = time.time()

        # Komponenten
        self.db = DatabaseManager(
            db_file=config.DB_FILE,
            table_name=config.TABLE_NAME,
            field_defs=config.REQUIRED_FIELDS,
        )

        self.mailer = EmailNotifier(
            recipient=config.MAIL_RECIPIENT,
            sender=config.MAIL_SENDER,
            subject_prefix=getattr(config, "MAIL_SUBJECT_PREFIX", ""),
        )

        # MQTT-Client
        self.client = mqtt.Client(client_id=getattr(config, "CLIENT_ID", "mqtt_sqlite_logger"))
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    # ---------- MQTT Callback-Methoden ----------

    def on_connect(self, client, userdata, flags, rc):
        print(f"✅ Verbunden mit MQTT-Broker {config.BROKER}:{config.BROKER_PORT}, Statuscode: {rc}")
        client.subscribe(config.TOPIC)
        print(f"📡 Subscribed auf Topic: {config.TOPIC}")

    def on_message(self, client, userdata, msg):
        try:
            payload_str = msg.payload.decode("utf-8", errors="replace")
            payload = json.loads(payload_str)

            if not isinstance(payload, dict):
                print(f"ℹ️ {msg.topic}: Nicht-JSON-Objekt empfangen, wird ignoriert: {payload_str}")
                return

            # Pflichtfeld für Zeitstempel prüfen (NOT NULL in DB)
            ts_key = getattr(config, "TIMESTAMP_FIELD", "utms")
            if not payload.get(ts_key):
                print(f"⚠️ Payload ohne '{ts_key}' empfangen, wird ignoriert: {payload}")
                return

            record = {}

            for field_name in config.REQUIRED_FIELDS.keys():
                # Battery-Feld speziell behandeln
                if field_name == getattr(config, "BATTERY_FIELD", "battery"):
                    record[field_name] = normalize_battery(payload.get(field_name))

                # Numerische Felder über safe_extract_value behandeln
                elif field_name in getattr(config, "NUMERIC_FIELDS", set()):
                    record[field_name] = safe_extract_value(payload, field_name)

                # Rest direkt übernehmen (Strings etc.)
                else:
                    record[field_name] = payload.get(field_name)

            # In DB schreiben
            self.db.insert_record(record)

            tin = record.get("temperatureIN")
            print(f"✅ Datensatz eingefügt | tempIN: {tin}")

            # Timeout-Überwachung zurücksetzen
            self.last_message_time = time.time()
            # Fehler-Mail-Status zurücksetzen, damit nach Erholung wieder gemeldet werden kann
            self.mailer.last_error_mail_date = None

        except json.JSONDecodeError:
            print(f"❌ {msg.topic}: Ungültiges JSON-Format.")
        except Exception as e:
            print(f"❌ Allgemeiner Fehler in on_message: {e}")

    # ---------- Haupt-Loop / Timeout-Überwachung ----------

    def check_timeout(self):
        """
        Prüft, ob seit TIMEOUT_SECONDS keine Daten mehr eingetroffen sind,
        und versendet ggf. eine Alarm-Mail (max. 1x pro Tag).
        """
        now = time.time()
        diff = now - self.last_message_time

        if diff > config.TIMEOUT_SECONDS:
            hours = round(diff / 3600, 2)
            last_ts = datetime.datetime.fromtimestamp(self.last_message_time).isoformat()

            body = (
                f"SEIT {hours} STUNDEN KEINE NEUEN MQTT-DATEN EMPFANGEN!\n"
                f"Letzter Empfangszeitpunkt: {last_ts}\n"
                f"Broker: {config.BROKER}:{config.BROKER_PORT}\n"
                f"Topic: {config.TOPIC}\n"
            )

            self.mailer.send_error_once_per_day("[ALARM] MQTT Daten-Timeout", body)

    def start(self):
        """
        Startet Logger: initialisiert DB, verbindet MQTT, verschickt Start-Mail
        und überwacht den Timeout in einer Schleife.
        """
        # DB vorbereiten
        self.db.initialize()

        # MQTT-Verbindung aufbauen
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
            ),
        )

        # MQTT-Loop in eigenem Thread
        self.client.loop_start()

        print("🏃 MQTT-Logger läuft. Drücke Ctrl+C zum Beenden.")

        try:
            # Hauptloop für Timeout-Überwachung
            while True:
                time.sleep(60)
                self.check_timeout()

        except KeyboardInterrupt:
            print("\n🛑 Beende Logger (KeyboardInterrupt).")
        except Exception as e:
            print(f"❌ KRITISCHER FEHLER: {e}")
            self.mailer.send_error_once_per_day(
                "[KRITISCH] MQTT Logger beendet",
                f"Der MQTT-Logger ist aufgrund eines kritischen Fehlers gestoppt worden:\n{e}",
            )
        finally:
            self.client.loop_stop()
            self.client.disconnect()
            print("🔌 MQTT-Verbindung getrennt.")


if __name__ == "__main__":
    logger = MQTTLogger()
    logger.start()
