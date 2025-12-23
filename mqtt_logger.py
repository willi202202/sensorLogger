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
from exceptions import (
    MQTTLoggerError,
    JSONPayloadDecodeError,
    PayloadFormatError,
    MissingTimestampError,
    UnknownSensorError,
    DatabaseError,
    ConfigError,
    InternalLoggerError,
)


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


# --------------------------
# Mail
# --------------------------

class EmailNotifier:
    def __init__(self, enabled: bool, recipient: str, sender: Optional[str] = None, subject_prefix: str = ""):
        self.enabled = bool(enabled)
        self.recipient = recipient
        self.sender = sender
        self.subject_prefix = subject_prefix or ""
        self._last_sent_ts: Dict[str, float] = {}  # key -> last sent unix time

    def _build_subject(self, subject: str) -> str:
        s = f"{self.subject_prefix} {subject}".strip()
        return " ".join(s.split())

    def send_mail(self, subject: str, body: str) -> bool:
        if not self.enabled:
            return False

        full_subject = self._build_subject(subject)

        # Windows: Simulation
        if os.name == "nt":
            print("📧 [MAIL-SIMULATION – WINDOWS]")
            print("SUBJECT:", full_subject)
            print("BODY:\n", body)
            print("-" * 60)
            return True

        # Linux: absolute path (systemd PATH safe)
        cmd = ["/usr/bin/mail", "-s", full_subject, self.recipient]

        try:
            subprocess.run(
                cmd,
                input=body.encode("utf-8"),
                capture_output=True,
                check=True,
            )
            print(f"📧 E-Mail gesendet: '{full_subject}'")
            return True

        except FileNotFoundError:
            print("❌ Fehler: /usr/bin/mail nicht gefunden. (mailutils/bsd-mailx installiert?)")
            return False
        except subprocess.CalledProcessError as e:
            print(f"❌ Fehler beim Senden der E-Mail: {e}")
            return False
        except Exception as e:
            print(f"❌ Unbekannter Fehler beim Senden der E-Mail: {e}")
            return False

    def send_throttled(
        self,
        key: str,
        subject: str,
        body: str,
        min_interval_hours: Optional[int] = 6
    ) -> bool:
        """
        Sends an email with rate limiting per key.
        - min_interval_hours=None -> no limit
        - min_interval_hours=0 -> no limit (useful for testing)
        - min_interval_hours>0 -> limit
        """
        if not self.enabled:
            return False

        if min_interval_hours is None:
            return self.send_mail(subject, body)

        try:
            h = int(min_interval_hours)
        except (TypeError, ValueError) as e:
            raise ConfigError(f"Invalid min_interval_hours: {min_interval_hours!r}") from e

        if h < 0:
            raise ConfigError(f"min_interval_hours must be >= 0, got {h}")

        if h == 0:
            return self.send_mail(subject, body)

        min_interval_s = h * 3600
        now = time.time()
        last = self._last_sent_ts.get(key)

        if last is not None and (now - last) < min_interval_s:
            return False

        ok = self.send_mail(subject, body)
        if ok:
            self._last_sent_ts[key] = now
        return ok


# --------------------------
# Logger
# --------------------------

class MQTTLogger:
    def __init__(self, config_path: str):
        self.cfg = SystemConfig.load(config_path)

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

        # mailer
        self.mailer = EmailNotifier(
            enabled=self.cfg.mail.enabled,
            recipient=self.cfg.mail.recipient,
            sender=self.cfg.mail.sender,
            subject_prefix=self.cfg.mail.subject_prefix,
        )

        # mqtt
        self.client = mqtt.Client(client_id="mqtt_sqlite_logger")
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

    # ---------- exception mail handler ----------

    def _handle_exception(self, sensor_id: str, topic: str, payload_str: str, exc: Exception):
        print(f"❌ {type(exc).__name__} ({sensor_id}): {exc}")

        trig = self.cfg.mail.trigger_exceptions
        if not (self.cfg.mail.enabled and trig.enabled):
            return

        self.exception_counts[sensor_id] = self.exception_counts.get(sensor_id, 0) + 1
        min_count = int(trig.min_count_before_mail or 1)
        if self.exception_counts[sensor_id] < min_count:
            return

        preview_len = int(trig.payload_preview_chars or 0)
        payload_preview = payload_str[:preview_len] if preview_len > 0 else ""

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

        # pro Exception-Typ separat throttlen (praktisch!)
        key = f"exc:{sensor_id}:{type(exc).__name__}"

        sent = self.mailer.send_throttled(
            key=key,
            subject=f"[ERROR] {type(exc).__name__} ({sensor_id})",
            body=body,
            min_interval_hours=int(trig.max_repeat_every_hours),
        )
        if sent:
            self.exception_counts[sensor_id] = 0

    # ---------- mqtt callbacks ----------

    def on_connect(self, client, userdata, flags, rc):
        print(f"✅ Verbunden mit MQTT-Broker {self.cfg.mqtt.host}:{self.cfg.mqtt.port}, Statuscode: {rc}")
        client.subscribe(self.cfg.mqtt.topic)
        print(f"📡 Subscribed auf Topic: {self.cfg.mqtt.topic}")

    def on_message(self, client, userdata, msg):
        trig_exc = self.cfg.mail.trigger_exceptions
        sensor_id = self._sensor_id_from_topic(msg.topic)
        payload_str = ""
        payload_str = msg.payload.decode("utf-8", errors="replace")

        try:
            if not sensor_id:
                msg_txt = f"Sensor unbekannt ({sensor_id})"
                if trig_exc.raise_on_unknown_sensor_error:
                    raise UnknownSensorError(msg_txt)
                else:
                    print(f"❌ {msg.topic}: {msg_txt}")
                return
        
            table = self._get_table_for_sensor(sensor_id)
            if not table:
                msg_txt = f"Sensor unbekannt ({sensor_id})"
                if trig_exc.raise_on_unknown_sensor_error:
                    raise UnknownSensorError(msg_txt)
                else:
                    print(f"❌ {msg.topic}: {msg_txt}")
                return

            # JSON parse
            try:
                payload = json.loads(payload_str)
            except json.JSONDecodeError as e:
                msg_txt = f"Ungueltiges JSON-Format ({e})"
                if trig_exc.raise_on_json_decode_error:
                    raise JSONPayloadDecodeError(msg_txt) from e
                else:
                    print(f"❌ {msg.topic}: {msg_txt}")
                return

            # must be dict
            if not isinstance(payload, dict):
                msg_txt = f"Payload ist kein JSON-Objekt (type={type(payload).__name__})"
                if trig_exc.raise_on_non_dict_payload:
                    raise PayloadFormatError(msg_txt)
                else:
                    print(f"❌ {msg.topic}: {msg_txt}")
                return

            # timestamp required
            ts_key = table.timestamp.name
            utms = payload.get(ts_key)
            if not utms:
                msg_txt = f"Pflichtfeld '{ts_key}' fehlt oder ist leer"
                if trig_exc.raise_on_missing_timestamp:
                    raise MissingTimestampError(msg_txt)
                else:
                    print(f"❌ {msg.topic}: {msg_txt}")
                return

            record: Dict[str, Any] = {ts_key: utms}

            # bad value detection: count fields where invalid_map matched and mapped to None
            bad_hit = 0

            for skey, sensor in table.sensors.items():
                raw = payload.get(skey)

                if raw is not None and sensor.invalid_map:
                    raw_str = str(raw).strip()
                    if raw_str in sensor.invalid_map and sensor.invalid_map[raw_str] is None:
                        bad_hit += 1

                record[skey] = sensor.sanitize_value(raw)

            # Insert
            self.dbs[table.key].insert(record)

            # compact log
            compact = bool(getattr(self.cfg.mqtt, "compact_log_enabled", True))
            if compact:
                print(f"✅ {sensor_id} -> {table.name} | ts={utms}")

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
            self._handle_exception(sensor_id, msg.topic, payload_str, e)

        except Exception as e:
            # unexpected -> treat as internal bug
            self._handle_exception(sensor_id, msg.topic, payload_str, InternalLoggerError(repr(e)))

    # --------------------------
    # Periodic checks
    # --------------------------

    def check_missing_data(self):
        trig = self.cfg.mail.trigger_missing_data
        if not (self.cfg.mail.enabled and trig.enabled):
            return

        window_s = int((trig.window_minutes or 0) * 60)
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

                self.mailer.send_throttled(
                    key=f"missing:{sid}",
                    subject=f"[ALARM] Missing MQTT data ({sid})",
                    body=body,
                    min_interval_hours=int(trig.max_repeat_every_hours),
                )

    def check_bad_values(self):
        trig = self.cfg.mail.trigger_bad_values
        if not (self.cfg.mail.enabled and trig.enabled):
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

            sent = self.mailer.send_throttled(
                key=f"bad:{sid}",
                subject=f"[WARN] Bad values ({sid})",
                body=body,
                min_interval_hours=int(trig.max_repeat_every_hours),
            )
            if sent:
                self.bad_value_events[sid] = 0

    def check_db_size(self):
        
        trig = self.cfg.mail.trigger_db_size
        if not (self.cfg.mail.enabled and trig.enabled):
            return

        # tolerate both names (CHECK_EVERY_HOUR vs CHECK_EVERY_HOURS) via model or fallback
        check_hours = getattr(trig, "check_every_hours", None)           
        if check_hours is None:
            return

        now = time.time()
        if self._last_db_size_check_ts and (now - self._last_db_size_check_ts) < (int(check_hours) * 3600):
            return
        self._last_db_size_check_ts = now

        max_repeat_every_hours = getattr(trig, "max_repeat_every_hours")
        if max_repeat_every_hours is None:
            return

        size_b = get_db_size_bytes(self.cfg.db_file)
        size_mb = size_b / (1024 * 1024)

        warn = trig.warn_mb or 0
        crit = trig.crit_mb or 0

        if crit and size_mb >= crit:
            body = f"DB GROESSE KRITISCH: {size_mb:.1f} MB (CRIT={crit} MB)\nDB: {self.cfg.db_file}\n"
            self.mailer.send_throttled(
                key="dbsize:crit",
                subject="[ALARM] DB size critical",
                body=body,
                min_interval_hours=int(max_repeat_every_hours),
            )

        elif warn and size_mb >= warn:
            body = f"DB GROESSE WARNUNG: {size_mb:.1f} MB (WARN={warn} MB)\nDB: {self.cfg.db_file}\n"
            self.mailer.send_throttled(
                key="dbsize:warn",
                subject="[WARN] DB size warning",
                body=body,
                min_interval_hours=int(max_repeat_every_hours),
            )

    def maybe_send_info_mail(self):
        trig = self.cfg.mail.trigger_info
        if not (self.cfg.mail.enabled and trig.enabled):
            return

        repeat_s = hours_to_seconds(getattr(trig, "repeat_every_hours", None))
        if repeat_s is not None and self._last_info_mail_ts and (time.time() - self._last_info_mail_ts) < repeat_s:
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

        sent = self.mailer.send_throttled(
            key="info:start",
            subject="[INFO] MQTT Logger gestartet",
            body=body,
            min_interval_hours=int(getattr(trig, "repeat_every_hours", 24)),
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
            self.mailer.send_throttled(
                key=f"schema:{tkey}",
                subject="[WARN] DB Schema mismatch",
                body=f"{warn}\nDB: {self.cfg.db_file}\n",
                min_interval_hours=24,
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

        print("✅ Active sensor_ids:", ", ".join(sorted([t.sensor_id for t in self.active_tables.values()])))
        print(f"✅ DB: {self.cfg.db_file}")

        # MQTT verbinden
        print(f"Verbinde zu Broker {self.cfg.mqtt.host}:{self.cfg.mqtt.port} ...")
        try:
            self.client.connect(self.cfg.mqtt.host, self.cfg.mqtt.port, 60)
        except Exception as e:
            self._handle_exception("global", "mqtt_connect", "", InternalLoggerError(repr(e)))
            sys.exit(1)

        # Start Info Mail (optional)
        self.maybe_send_info_mail()

        # MQTT loop
        self.client.loop_start()
        print("🏃 MQTT-Logger laeuft. Druecke Ctrl+C zum Beenden.")

        try:
            while True:
                time.sleep(60)
                self.check_missing_data()
                self.check_bad_values()
                self.check_db_size()
                self.maybe_send_info_mail()

        except KeyboardInterrupt:
            print("\n🛑 Beende Logger (KeyboardInterrupt).")
        finally:
            self.client.loop_stop()
            self.client.disconnect()
            print("🔌 MQTT-Verbindung getrennt.")


def main():
    cfg_path = "config/sensor_config.json"
    if len(sys.argv) >= 2:
        cfg_path = sys.argv[1]

    if not os.path.isfile(cfg_path):
        print(f"❌ Config nicht gefunden: {cfg_path}")
        print("Usage: ./mqtt_logger.py [config.json]")
        sys.exit(2)

    MQTTLogger(cfg_path).start()


if __name__ == "__main__":
    main()
