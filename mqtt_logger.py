#!/usr/bin/env python3
# mqtt_logger.py
#
# MQTT -> SQLite logger (multi-table) basierend auf JSON Config + models.py
#
# Topics:
#   mobilealerts/<sensor_id>/json
#
# Features:
# - Insert-only (kein CREATE TABLE!)
# - Schema-Check beim Start: fehlende Spalten -> Warnung + Tabelle deaktiviert
# - Missing-Data Alarm
# - Bad-Values Alarm (invalid_map -> NULL)
# - DB-Size Check (WARN/CRIT)
# - Exceptions: alles als Exceptions modelliert -> zentraler Mail-Handler (rate-limited)
#
# Windows: Mail wird simuliert (print)
# Linux: /usr/bin/mail wird genutzt
#
# To monitor mails on Linux, use:
# mosquitto_sub -h 127.0.0.1 -p 1883 -t 'mobilealerts/+/json'

from __future__ import annotations

import os
import sys
import time
import json
import datetime
import sqlite3
import subprocess
from typing import Any, Dict, Optional, Set

from paho.mqtt import client as mqtt

from config.models import SystemConfig, TableConfig
from msg_sender import MessageSender
from exceptions import (
    MQTTLoggerError,
    DatabaseError,
    ConfigError,
    InternalLoggerError,
)

import urllib.request
import urllib.error
import ssl


# --------------------------
# Constants
# --------------------------

CONFIG_SENSOR_PATH = "config/sensor_config.json"
CONFIG_MESSAGE_PATH = "config/msg_config.json"


# --------------------------
# Helpers (strict)
# --------------------------

def hours_to_seconds(h: Optional[int]) -> Optional[int]:
    """
    Strict conversion:
    - None -> None
    - 0 -> 0  (no throttle)
    - invalid -> ConfigError
    """
    if h is None:
        return None

    try:
        value = int(h)
    except (TypeError, ValueError) as e:
        raise ConfigError(f"Invalid hours value: {h!r}") from e

    if value < 0:
        raise ConfigError(f"Hours value must be >= 0, got {value}")

    return value * 3600


def get_db_size_bytes(db_file: str) -> int:
    try:
        return os.path.getsize(db_file)
    except FileNotFoundError:
        return 0
    except OSError as e:
        raise DatabaseError(f"Failed to get DB file size '{db_file}': {e}") from e


def get_table_columns(db_file: str, table: str) -> Set[str]:
    try:
        conn = sqlite3.connect(db_file, timeout=5)
        try:
            cur = conn.cursor()
            cur.execute(f'PRAGMA table_info("{table}")')
            rows = cur.fetchall()
            return {r[1] for r in rows}  # column name
        finally:
            conn.close()
    except sqlite3.Error as e:
        raise DatabaseError(f"Failed to read schema for table '{table}': {e}") from e


def check_schema(db_file: str, tables: Dict[str, TableConfig]) -> Dict[str, str]:
    """
    Rueckgabe: table_key -> problem_text (nur wenn etwas fehlt)
    """
    problems: Dict[str, str] = {}
    for tkey, tcfg in tables.items():
        expected = {tcfg.timestamp.name} | set(tcfg.sensors.keys())
        actual = get_table_columns(db_file, tcfg.name)
        missing = sorted(expected - actual)
        if missing:
            problems[tkey] = f"Table '{tcfg.name}' missing columns: {', '.join(missing)}"
    return problems

def _avg_minutes(dt_seconds: float, n_intervals: int) -> Optional[float]:
    if n_intervals <= 0:
        return None
    return (dt_seconds / n_intervals) / 60.0

# --------------------------
# DB
# --------------------------

class DatabaseManager:
    """
    Insert-only DB Wrapper, passend zu bestehenden Tabellen.
    Wirft DatabaseError statt still zu printen.
    """
    def __init__(self, db_file: str, table: str, fields_in_order: list[str]):
        self.db_file = db_file
        self.table = table
        self.fields = fields_in_order[:]  # Reihenfolge fuer INSERT

        cols_sql = ", ".join(self.fields)
        placeholders = ", ".join("?" for _ in self.fields)
        self._sql = f"INSERT INTO {self.table} ({cols_sql}) VALUES ({placeholders})"

    def _connect(self):
        return sqlite3.connect(self.db_file, timeout=5)

    def insert(self, record: dict):
        values = [record.get(c) for c in self.fields]
        last_err: Exception | None = None

        for _ in range(5):
            try:
                conn = self._connect()
                try:
                    cur = conn.cursor()
                    cur.execute(self._sql, values)
                    conn.commit()
                    return
                finally:
                    conn.close()

            except sqlite3.OperationalError as e:
                last_err = e
                if "locked" in str(e).lower():
                    time.sleep(0.2)
                    continue
                raise DatabaseError(f"DB insert failed ({self.table}): {e}") from e

            except sqlite3.Error as e:
                raise DatabaseError(f"DB error ({self.table}): {e}") from e

        raise DatabaseError(
            f"DB insert failed after retries ({self.table}): database remained locked. Last error: {last_err}"
        )


# Note: Email and Ntfy notifiers are now handled by MessageSender class in msg_sender.py


# --------------------------
# Logger
# --------------------------

class MQTTLogger:
    def __init__(self):
        try:
            self.cfg = SystemConfig.load(CONFIG_SENSOR_PATH)
        except Exception as e:
            print(f"⚠️ Failed to load system config: {e}")
            exit(1)

        # active tables after schema check
        self.active_tables: Dict[str, TableConfig] = {}
        self.inactive_tables: Dict[str, str] = {}  # table_key -> reason

        # per sensor-id last message time
        self.last_message_time: Dict[str, float] = {}

        # for bad-values mail
        self.bad_value_events: Dict[str, int] = {}

        # per sensor exception counts (for MIN_COUNT_BEFORE_MAIL)
        self.exception_counts: Dict[str, int] = {}

        # DB managers per table_key
        self.dbs: Dict[str, DatabaseManager] = {}

        # per sensor stats
        self.rx_stats: Dict[str, Dict[str, float]] = {}
        # Struktur pro sensor_id:
        # { "count": int, "first_ts": float, "last_ts": float }

        # MessageSender for handling all notifications
        try:
            self.msg_sender = MessageSender(CONFIG_MESSAGE_PATH)
        except Exception as e:
            print(f"⚠️ Failed to initialize MessageSender: {e}")
            self.msg_sender = None
            exit(1)    

        # mqtt
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="mqtt_sqlite_logger")
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

        # schedule bookkeeping
        self._last_db_size_check_ts: float = 0.0
        self._last_info_mail_ts: float = 0.0

    # ---------- routing ----------

    def _sensor_id_from_topic(self, topic: str) -> Optional[str]:
        parts = topic.split("/")
        if len(parts) >= 3 and parts[0] == "mobilealerts":
            return parts[1]
        return None

    def _get_table_for_sensor(self, sensor_id: str) -> Optional[TableConfig]:
        # config mapping via sensor_id in TABLE blocks
        t = self.cfg.get_table_by_sensor_id(sensor_id)
        if not t:
            return None
        # is it active?
        for tcfg in self.active_tables.values():
            if tcfg.sensor_id == sensor_id:
                return tcfg
        return None

    # ---------- exception handler ----------

    def _handle_exception(self, sensor_id: str, topic: str, payload_str: str, exc: Exception):
        """Handle exceptions and send notifications via MessageSender."""
        print(f"❌ {type(exc).__name__} ({sensor_id}): {exc}")

        if not self.msg_sender:
            return

        self.exception_counts[sensor_id] = self.exception_counts.get(sensor_id, 0) + 1

        payload_preview = payload_str[:self.msg_sender.config.logfile.payload_preview_chars]

        body = (
            f"Exception im MQTT Logger\n\n"
            f"Exception: {type(exc).__name__}\n"
            f"Sensor-ID: {sensor_id}\n"
            f"Topic: {topic}\n"
            f"Zeit: {datetime.datetime.now().isoformat()}\n"
            f"Fehler: {repr(exc)}\n"
            f"Count: {self.exception_counts[sensor_id]}\n"
            f"DB: {self.cfg.db_file}\n"
            f"Broker: {self.cfg.mqtt.host}:{self.cfg.mqtt.port}\n"
            f"Topic-Filter: {self.cfg.mqtt.topic}\n"
        )
        if payload_preview:
            body += f"\nPayload-Preview:\n{payload_preview}\n"

        trigger_key = f"EXCEPTION_{type(exc).__name__}"
        trigger_title = f"[ERROR] {type(exc).__name__} ({sensor_id})"
        
        sent = self.msg_sender.send(
            trigger_key=trigger_key,
            trigger_title=trigger_title,
            enabled_channels=self.msg_sender.config.info.enabled,  # Use default config channels
            payload=body,
            payload_full=body,
        )
        
        if sent:
            self.exception_counts[sensor_id] = 0

    # ---------- mqtt callbacks ----------

    def on_connect(self, client, userdata, connect_flags, reason_code, properties):
        client.subscribe(self.cfg.mqtt.topic)
        body = (
            f"Verbunden mit MQTT-Broker\n\n"
            f"Broker: {self.cfg.mqtt.host}:{self.cfg.mqtt.port}\n"
            f"Statuscode: {reason_code}\n"
            f"Topic: {self.cfg.mqtt.topic}\n"
            f"DB: {self.cfg.db_file}\n"
        )
        if self.msg_sender:
            self.msg_sender.send(
                trigger_key="MQTT_CONNECTED",
                trigger_title="[INFO] MQTT Broker connected",
                enabled_channels=self.msg_sender.config.info.enabled,
                payload=body,
            )

    def on_message(self, client, userdata, message):
        sensor_id = self._sensor_id_from_topic(message.topic)
        payload_str = ""
        payload_str = message.payload.decode("utf-8", errors="replace")

        try:
            if not sensor_id:
                msg_txt = f"Sensor unbekannt ({sensor_id})"
                self.msg_sender.send(
                    trigger_key=f"UNKNOWN_SENSOR_ERROR",
                    trigger_title=self.msg_sender.config.unknown_sensor_error.title,
                    enabled_channels=self.msg_sender.config.unknown_sensor_error.enabled,
                    payload=f"Topic: {message.topic}\n{msg_txt}",
                )
                return
        
            table = self._get_table_for_sensor(sensor_id)
            if not table:
                msg_txt = f"Sensor unbekannt ({sensor_id})"
                self.msg_sender.send(
                    trigger_key=f"UNKNOWN_SENSOR_ERROR",
                    trigger_title=self.msg_sender.config.unknown_sensor_error.title,
                    enabled_channels=self.msg_sender.config.unknown_sensor_error.enabled,
                    payload=f"Topic: {message.topic}\n{msg_txt}",
                )
                return

            # JSON parse
            try:
                payload = json.loads(payload_str)
            except json.JSONDecodeError as e:
                msg_txt = f"Ungueltiges JSON-Format ({e})"
                self.msg_sender.send(
                    trigger_key=f"JSON_DECODE_ERROR",
                    trigger_title=self.msg_sender.config.json_decode_error.title,
                    enabled_channels=self.msg_sender.config.json_decode_error.enabled,
                    payload=f"Topic: {message.topic}\n{msg_txt}",
                )
                return

            # must be dict
            if not isinstance(payload, dict):
                msg_txt = f"Payload ist kein JSON-Objekt (type={type(payload).__name__})"
                self.msg_sender.send(
                    trigger_key=f"NON_DICT_PAYLOAD",
                    trigger_title=self.msg_sender.config.non_dict_payload.title,
                    enabled_channels=self.msg_sender.config.non_dict_payload.enabled,
                    payload=f"Topic: {message.topic}\n{msg_txt}",
                )
                return

            # timestamp required
            ts_key = table.timestamp.name
            utms = payload.get(ts_key)
            if not utms:
                msg_txt = f"Pflichtfeld '{ts_key}' fehlt oder ist leer"
                self.msg_sender.send(
                    trigger_key=f"MISSING_TIMESTAMP",
                    trigger_title=self.msg_sender.config.missing_timestamp.title,
                    enabled_channels=self.msg_sender.config.missing_timestamp.enabled,
                    payload=f"Topic: {message.topic}\n{msg_txt}",
                )
                return

            record: Dict[str, Any] = {ts_key: utms}

            # bad value detection: count fields where invalid_map matched and mapped to None
            bad_hit = 0

            for skey, sensor in table.sensors.items():
                raw = payload.get(skey)
                #print(f"Debug: sensor field '{skey}' raw value: {raw!r} raw typ {type(raw).__name__}")
                value, is_good = sensor.sanitize_value(raw)
                record[skey] = value
                if not is_good:
                    bad_hit += 1

                

            # Insert
            self.dbs[table.key].insert(record)

            # compact log
            compact = bool(getattr(self.cfg.mqtt, "compact_log_enabled", True))
            if compact:
                print(f"✅ {sensor_id} -> {table.name} | ts={utms}")
            else:
                print(f"✅ {sensor_id} -> {table.name} | record={record}")

            # state update
            now = time.time()
            self.last_message_time[sensor_id] = now
            
            st = self.rx_stats.get(sensor_id)
            if st is None:
                self.rx_stats[sensor_id] = {
                    "count_total": 1,
                    "first_ts": now,
                    "last_ts": now,
                    "last_info_count": 0,   # Referenz: beim ersten Info-Mail ist das Intervall "alles bisher"
                    "last_info_ts": 0.0
                }
            else:
                st["count_total"] += 1
                st["last_ts"] = now

            if bad_hit > 0:
                self.bad_value_events[sensor_id] = self.bad_value_events.get(sensor_id, 0) + bad_hit

        except MQTTLoggerError as e:
            self._handle_exception(sensor_id, message.topic, payload_str, e)

        except Exception as e:
            # unexpected -> treat as internal bug
            self._handle_exception(sensor_id, message.topic, payload_str, InternalLoggerError(repr(e)))

    # --------------------------
    # Periodic checks
    # --------------------------

    def check_missing_data(self):
        """Check for missing MQTT data using MessageSender."""
        if not self.msg_sender:
            return

        window_s = int((self.msg_sender.config.missing_data.window_minutes or 0) * 60)
        if window_s <= 0:
            return

        now = time.time()
        for t in self.active_tables.values():
            sid = t.sensor_id
            last = self.last_message_time.get(sid)
            if last is None:
                continue

            diff = now - last
            if diff > window_s:
                hours = round(diff / 3600, 2)
                last_ts = datetime.datetime.fromtimestamp(last).isoformat()

                body = (
                    f"SEIT {hours} STUNDEN KEINE NEUEN MQTT-DATEN!\n\n"
                    f"Sensor-ID: {sid}\n"
                    f"Tabelle: {t.name}\n"
                    f"Letzter Empfang: {last_ts}\n"
                    f"Broker: {self.cfg.mqtt.host}:{self.cfg.mqtt.port}\n"
                    f"Topic: {self.cfg.mqtt.topic}\n"
                    f"DB: {self.cfg.db_file}\n"
                )

                self.msg_sender.send(
                    trigger_key=f"MISSING_DATA_{sid}",
                    trigger_title=f"[ALARM] Missing MQTT data ({sid})",
                    enabled_channels=self.msg_sender.config.missing_data.enabled,
                    payload=body,
                    payload_full=body,
                )

    def check_bad_values(self):
        """Check for bad values using MessageSender."""
        if not self.msg_sender:
            return

        for t in self.active_tables.values():
            sid = t.sensor_id
            count = self.bad_value_events.get(sid, 0)
            if count <= 0:
                continue

            body = (
                f"BAD VALUES erkannt (invalid_map -> NULL)!\n\n"
                f"Sensor-ID: {sid}\n"
                f"Tabelle: {t.name}\n"
                f"Anzahl bad-field hits seit letztem Mail: {count}\n"
                f"Broker: {self.cfg.mqtt.host}:{self.cfg.mqtt.port}\n"
                f"Topic: {self.cfg.mqtt.topic}\n"
                f"DB: {self.cfg.db_file}\n"
            )

            sent = self.msg_sender.send(
                trigger_key=f"BAD_VALUES_{sid}",
                trigger_title=f"[WARN] Bad values ({sid})",
                enabled_channels=self.msg_sender.config.bad_values.enabled,
                payload=body,
                payload_full=body,
            )
            if sent:
                self.bad_value_events[sid] = 0

    def check_db_size(self):
        """Check database size using MessageSender."""
        if not self.msg_sender:
            return

        check_hours = self.msg_sender.config.db_size.check_every_hours
        if check_hours is None or check_hours <= 0:
            return

        now = time.time()
        if self._last_db_size_check_ts and (now - self._last_db_size_check_ts) < (int(check_hours) * 3600):
            return
        self._last_db_size_check_ts = now

        size_b = get_db_size_bytes(self.cfg.db_file)
        size_mb = size_b / (1024 * 1024)

        warn = self.msg_sender.config.db_size.warn_mb or 0
        crit = self.msg_sender.config.db_size.crit_mb or 0

        if crit and size_mb >= crit:
            body = f"DB GROESSE KRITISCH: {size_mb:.1f} MB (CRIT={crit} MB)\nDB: {self.cfg.db_file}\n"
            self.msg_sender.send(
                trigger_key="DB_SIZE_CRITICAL",
                trigger_title="[ALARM] DB size critical",
                enabled_channels=self.msg_sender.config.db_size.enabled,
                payload=body,
                payload_full=body,
            )

        elif warn and size_mb >= warn:
            body = f"DB GROESSE WARNUNG: {size_mb:.1f} MB (WARN={warn} MB)\nDB: {self.cfg.db_file}\n"
            self.msg_sender.send(
                trigger_key="DB_SIZE_WARNING",
                trigger_title="[WARN] DB size warning",
                enabled_channels=self.msg_sender.config.db_size.enabled,
                payload=body,
                payload_full=body,
            )

    def maybe_send_info_mail(self):
        """Send periodic info message using MessageSender."""
        if not self.msg_sender:
            return

        repeat_s = self.msg_sender.config.max_repeat_hours * 3600  # Use max_repeat_hours from config
        if self._last_info_mail_ts and (time.time() - self._last_info_mail_ts) < repeat_s:
            return

        start_time_iso = datetime.datetime.now().isoformat()

        lines = []
        now = time.time()

        for t in self.active_tables.values():
            sid = t.sensor_id
            st = self.rx_stats.get(sid)

            if not st:
                lines.append(f"- {sid}: noch keine Daten empfangen")
                continue

            count_total = int(st["count_total"])
            first_ts = float(st["first_ts"])
            last_ts = float(st["last_ts"])

            # Ø seit Start
            if count_total <= 1:
                avg_start = None
            else:
                avg_start = _avg_minutes(last_ts - first_ts, count_total - 1)

            # Intervall seit letztem Info-Mail
            last_info_count = int(st.get("last_info_count", 0))
            last_info_ts = float(st.get("last_info_ts", 0.0))

            count_interval = count_total - last_info_count
            if last_info_ts <= 0:
                # erstes Info-Mail: "Intervall" = alles bisher
                interval_dt = last_ts - first_ts if count_total > 1 else 0.0
                interval_intervals = count_total - 1
                interval_minutes = (last_ts - first_ts) / 60.0 if count_total > 1 else 0.0
            else:
                interval_dt = now - last_info_ts
                interval_intervals = max(0, count_interval - 1)
                interval_minutes = interval_dt / 60.0

            avg_interval = _avg_minutes(interval_dt, interval_intervals)

            # format
            if avg_start is None:
                start_txt = "Ø seit Start: n/a"
            else:
                start_txt = f"Ø seit Start: {avg_start:.2f} min"

            if avg_interval is None:
                interval_txt = f"Intervall: {count_interval} Paket(e) in {interval_minutes:.1f} min"
            else:
                interval_txt = f"Intervall: {count_interval} Pakete | Ø {avg_interval:.2f} min (in {interval_minutes:.1f} min)"

            lines.append(f"- {sid}: total {count_total} | {start_txt} | {interval_txt}")

        stats_text = "\n".join(lines)

        body = (
            f"MQTT-SQLite-Logger laeuft.\n"
            f"Zeit: {start_time_iso}\n"
            f"Broker: {self.cfg.mqtt.host}:{self.cfg.mqtt.port}\n"
            f"Topic: {self.cfg.mqtt.topic}\n"
            f"DB: {self.cfg.db_file}\n\n"
            f"Empfangs-Statistik:\n"
            f"{stats_text}\n"
        )

        sent = self.msg_sender.send(
            trigger_key="INFO_PERIODIC",
            trigger_title="[INFO] MQTT Logger gestartet",
            enabled_channels=self.msg_sender.config.info.enabled,
            payload=body,
            payload_full=body,
        )

        if sent:
            self._last_info_mail_ts = time.time()

            # Referenz fuer Intervall setzen
            for t in self.active_tables.values():
                sid = t.sensor_id
                st = self.rx_stats.get(sid)
                if st:
                    st["last_info_count"] = int(st["count_total"])
                    st["last_info_ts"] = self._last_info_mail_ts

    # --------------------------
    # Start
    # --------------------------

    def start(self):
        # Schema check -> aktive Tabellen bestimmen
        try:
            problems = check_schema(self.cfg.db_file, self.cfg.tables)
        except Exception as e:
            # schema read failed -> treat as fatal, mail via exception handler with a synthetic sensor_id
            self._handle_exception("global", "schema_check", "", DatabaseError(str(e)))
            sys.exit(1)

        for tkey, tcfg in self.cfg.tables.items():
            if tkey in problems:
                self.inactive_tables[tkey] = problems[tkey]
            else:
                self.active_tables[tkey] = tcfg

        # warn + mail about inactive tables (schema mismatch)
        for tkey, msg in self.inactive_tables.items():
            warn = f"⚠️ SCHEMA WARNING (Table {tkey} / sensor_id={self.cfg.tables[tkey].sensor_id}): {msg}"
            print(warn)
            if self.msg_sender:
                self.msg_sender.send(
                    trigger_key=f"SCHEMA_MISMATCH_{tkey}",
                    trigger_title="[WARN] DB Schema mismatch",
                    enabled_channels=self.msg_sender.config.info.enabled,
                    payload=f"{warn}\nDB: {self.cfg.db_file}\n",
                    payload_full=f"{warn}\nDB: {self.cfg.db_file}\n",
                )

        if not self.active_tables:
            print("❌ Keine aktiven Tabellen (Schema passt nicht). Abbruch.")
            sys.exit(2)

        # DB managers pro aktiver Tabelle erstellen
        for tkey, tcfg in self.active_tables.items():
            fields = [tcfg.timestamp.name] + list(tcfg.sensors.keys())
            self.dbs[tkey] = DatabaseManager(
                db_file=self.cfg.db_file,
                table=tcfg.name,
                fields_in_order=fields,
            )

        active_sensors = ", ".join(sorted([t.sensor_id for t in self.active_tables.values()]))
        startup_body = (
            f"MQTT Logger startet\n\n"
            f"Active Sensor IDs: {active_sensors}\n"
            f"DB: {self.cfg.db_file}\n"
            f"Broker: {self.cfg.mqtt.host}:{self.cfg.mqtt.port}\n"
            f"Topic: {self.cfg.mqtt.topic}\n"
        )
        if self.msg_sender:
            self.msg_sender.send(
                trigger_key="LOGGER_STARTUP",
                trigger_title="[INFO] MQTT Logger startup",
                enabled_channels=self.msg_sender.config.info.enabled,
                payload=startup_body,
            )

        # MQTT verbinden
        try:
            self.client.connect(self.cfg.mqtt.host, self.cfg.mqtt.port, 60)
        except Exception as e:
            self._handle_exception("global", "mqtt_connect", "", InternalLoggerError(repr(e)))
            sys.exit(1)

        # Start Info Mail (optional)
        self.maybe_send_info_mail()

        # MQTT loop
        self.client.loop_start()
        running_body = (
            f"MQTT Logger laeuft und wartet auf Signale\n\n"
            f"Broker: {self.cfg.mqtt.host}:{self.cfg.mqtt.port}\n"
            f"DB: {self.cfg.db_file}\n"
            f"Start: {datetime.datetime.now().isoformat()}\n\n"
            f"Druecke Ctrl+C zum Beenden.\n"
        )
        if self.msg_sender:
            self.msg_sender.send(
                trigger_key="LOGGER_RUNNING",
                trigger_title="[INFO] MQTT Logger running",
                enabled_channels=self.msg_sender.config.info.enabled,
                payload=running_body,
            )

        try:
            while True:
                time.sleep(60)
                self.check_missing_data()
                self.check_bad_values()
                self.check_db_size()
                self.maybe_send_info_mail()

        except KeyboardInterrupt:
            shutdown_body = (
                f"MQTT Logger Shutdown\n\n"
                f"Reason: KeyboardInterrupt\n"
                f"Time: {datetime.datetime.now().isoformat()}\n"
                f"DB: {self.cfg.db_file}\n"
            )
            if self.msg_sender:
                self.msg_sender.send(
                    trigger_key="LOGGER_SHUTDOWN",
                    trigger_title="[INFO] MQTT Logger shutdown",
                    enabled_channels=self.msg_sender.config.info.enabled,
                    payload=shutdown_body,
                )
        finally:
            self.client.loop_stop()
            self.client.disconnect()


def main():
    logger = MQTTLogger()
    logger.start()

if __name__ == "__main__":
    main()
