# models.py
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple, Union


Number = Union[int, float]


# ---------------------------
# Helpers
# ---------------------------

def _to_tuple2(value: Any) -> Tuple[Optional[float], Optional[float]]:
    """
    Converts [min,max] or (min,max) to tuple(float|None, float|None).
    Returns (None, None) if missing/invalid.
    """
    #print("value:", value)
    if value is None:
        return (None, None)
    if isinstance(value, (list, tuple)) and len(value) == 2:
        a, b = value
        return (None if a is None else float(a), None if b is None else float(b))
    return (None, None)


def _as_str_key(v: Any) -> str:
    """
    Keys in invalid_map are strings in JSON. We compare against the raw input as string.
    """
    #print("value str:", v)
    if v is None:
        return "null"
    return str(v).strip()

def _parse_bool(v: Any) -> Optional[int]:
    """
    Returns 0/1 or None.
    Accepts True/False, 0/1, "true"/"false", "0"/"1".
    """
    #print("value bool:", v)
    if v is None:
        return None
    if isinstance(v, bool):
        return 1 if v else 0
    if isinstance(v, (int, float)):
        if v == 0:
            return 0
        if v == 1:
            return 1
        # allow any nonzero? I'd rather be strict:
        return None
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("true", "1", "yes", "y", "on", "ok"):
            return 1
        if s in ("false", "0", "no", "n", "off", "low"):
            return 0
    return None


# ---------------------------
# Models
# ---------------------------

@dataclass
class Sensor:
    key: str                         # key in JSON under SENSORS, e.g. "temperature1"
    name: str
    alias: str
    field_type: str                  # "float" | "string" | "boolean" | ...
    unit: str = ""
    round: Optional[int] = None

    limits: Tuple[Optional[float], Optional[float]] = (None, None)
    warn: Tuple[Optional[float], Optional[float]] = (None, None)
    alarm: Tuple[Optional[float], Optional[float]] = (None, None)

    color: Optional[str] = None
    invalid_map: Dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        return f"Sensor(key={self.key}, alias={self.alias}, type={self.field_type}, unit={self.unit}, round={self.round}, limits={self.limits}, warn={self.warn}, alarm={self.alarm}, color={self.color}, invalid_map={self.invalid_map})"

    @staticmethod
    def from_dict(key: str, d: Dict[str, Any]) -> "Sensor":
        return Sensor(
            key=key,
            name=d.get("name", key),
            alias=d.get("alias", key),
            field_type=d.get("field_type", "string"),
            unit=d.get("unit", ""),
            round=d.get("round", None),
            limits=_to_tuple2(d.get("limits")),
            warn=_to_tuple2(d.get("warn")),
            alarm=_to_tuple2(d.get("alarm")),
            color=d.get("color"),
            invalid_map=d.get("invalid_map", {}) or {},
        )

    def sanitize_value(self, raw: Any) -> Any:
        """
        Applies invalid_map, converts types, rounding.
        Returns value ready for DB insert (None allowed).
        """
        #print("sanitize raw:", raw, "type:", self.field_type)
        # 1) invalid_map mapping (compare using string key)
        k = _as_str_key(raw)
        if k in self.invalid_map:
            raw = self.invalid_map[k]

        # 2) If mapping already produced None -> done
        if raw is None:
            return None

        # 3) Type conversion
        t = (self.field_type or "string").lower()

        # Take first element of tuple/list for numeric types
        if raw is not None and isinstance(raw, (list, tuple)) and len(raw) > 0:
            raw = raw[0]

        if t in ("float", "double", "number"):
            try:
                val = float(raw)
            except Exception:
                return None
            if self.round is not None:
                try:
                    val = round(val, int(self.round))
                except Exception:
                    pass
            return val

        if t in ("int", "integer"):
            try:
                return int(float(raw))
            except Exception:
                return None

        if t in ("bool", "boolean"):
            b = _parse_bool(raw)
            return b  # 0/1/None

        # default: string
        try:
            s = str(raw)
        except Exception:
            return None
        s = s.strip()
        return s if s != "" else None

    def is_outside(self, value: Any, rng: Tuple[Optional[float], Optional[float]]) -> bool:
        """
        True if numeric value is outside given [min,max]. If rng not fully defined, returns False.
        """
        if value is None:
            return False
        lo, hi = rng
        if lo is None and hi is None:
            return False
        try:
            v = float(value)
        except Exception:
            return False
        if lo is not None and v < lo:
            return True
        if hi is not None and v > hi:
            return True
        return False

    def check_levels(self, value: Any) -> Dict[str, bool]:
        """
        Returns dict flags: {"limits": bool, "warn": bool, "alarm": bool}
        Meaning: True if outside that band.
        """
        return {
            "limits": self.is_outside(value, self.limits),
            "warn": self.is_outside(value, self.warn),
            "alarm": self.is_outside(value, self.alarm),
        }


@dataclass
class TimestampConfig:
    name: str = "utms"
    type: str = "iso8601"  # you can later add "unix_ms", etc.

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "TimestampConfig":
        return TimestampConfig(
            name=d.get("name", "utms"),
            type=d.get("type", "iso8601"),
        )


@dataclass
class TableConfig:
    key: str                     # key under TABLE, e.g. "measurements_th"
    name: str                    # table name in DB (usually same)
    alias: str                   # short name / alias
    info: str                    # description/info
    sensor_id: str
    timestamp: TimestampConfig
    sensors: Dict[str, Sensor] = field(default_factory=dict)

    @staticmethod
    def from_dict(key: str, d: Dict[str, Any]) -> "TableConfig":
        ts = TimestampConfig.from_dict(d.get("TIMESTAMP", {}) or {})
        sensors = {
            sk: Sensor.from_dict(sk, sd)
            for sk, sd in (d.get("SENSORS", {}) or {}).items()
        }
        return TableConfig(
            key=key,
            name=d.get("name", key),
            alias=d.get("alias", key),
            info=d.get("info"),
            sensor_id=d.get("sensor_id", ""),
            timestamp=ts,
            sensors=sensors,
        )

    def get_sensor(self, sensor_key: str) -> Optional[Sensor]:
        return self.sensors.get(sensor_key)

    def get_sensor_by_alias(self, alias: str) -> Optional[Sensor]:
        for s in self.sensors.values():
            if s.alias == alias:
                return s
        return None


@dataclass
class MqttBrokerConfig:
    host: str = "127.0.0.1"
    port: int = 1883
    topic: str = "mobilealerts/+/json"
    compact_log_enabled: bool = False

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "MqttBrokerConfig":
        return MqttBrokerConfig(
            host=d.get("HOST", "127.0.0.1"),
            port=int(d.get("PORT", 1883)),
            topic=d.get("TOPIC", "mobilealerts/+/json"),
            compact_log_enabled=bool(d.get("COMPACT_LOG_ENABLED", False))
        )


@dataclass
class SystemConfig:
    db_file: str
    mqtt: MqttBrokerConfig
    mail: MailConfig
    ntfy: NtfyConfig
    tables: Dict[str, TableConfig]

    @staticmethod
    def load(path: str) -> "SystemConfig":
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)

        tables = {
            tk: TableConfig.from_dict(tk, td)
            for tk, td in (cfg.get("TABLE", {}) or {}).items()
        }

        return SystemConfig(
            db_file=cfg.get("DB_FILE", ""),
            mqtt=MqttBrokerConfig.from_dict(cfg.get("MQTT_BROKER", {}) or {}),
            mail=MailConfig.from_dict(cfg.get("MAIL", {}) or {}),
            ntfy=NtfyConfig.from_dict(cfg.get("NTFY", {}) or {}),
            tables=tables,
        )
    
    def get_table_by_key(self, table_key: str) -> Optional[TableConfig]:
        return self.tables.get(table_key)
    
    def get_table_by_alias(self, alias: str) -> Optional[TableConfig]:
        for t in self.tables.values():
            if t.alias == alias:
                return t
        return None
    
    def get_table_by_sensor_id(self, sensor_id: str) -> Optional[TableConfig]:
        for t in self.tables.values():
            if t.sensor_id == sensor_id:
                return t
        return None
    
    def get_sensor_by_key(self, table_key, sensor_key: str) -> Optional[Sensor]:
        table = self.get_table_by_key(table_key)
        if table is not None:
            return table.get_sensor(sensor_key)
        return None
    
    def get_sensor_by_alias(self, table_alias, sensor_alias: str) -> Optional[Sensor]:
        table = self.get_table_by_alias(table_alias)
        if table is not None:
            return table.get_sensor_by_alias(sensor_alias)
        return None


# ---------------------------
# Message Configuration Models
# ---------------------------

@dataclass
class EnabledChannels:
    ntfy: bool = False
    mail: bool = False
    stdout: bool = False
    logfile: bool = False

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "EnabledChannels":
        return EnabledChannels(
            ntfy=bool(d.get("NTFY", False)),
            mail=bool(d.get("MAIL", False)),
            stdout=bool(d.get("STDOUT", False)),
            logfile=bool(d.get("LOGFILE", False)),
        )


@dataclass
class NtfyConfig:
    enabled: bool = False
    server: str = "https://ntfy.sh"
    topic: str = ""
    token: str = ""
    priority: int = 5
    payload_preview_chars: int = 180

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "NtfyConfig":
        return NtfyConfig(
            enabled=bool(d.get("ENABLED", False)),
            server=d.get("SERVER", "https://ntfy.sh"),
            topic=d.get("TOPIC", ""),
            token=d.get("TOKEN", ""),
            priority=int(d.get("PRIORITY", 5)),
            payload_preview_chars=int(d.get("PAYLOAD_PREVIEW_CHARS", 180)),
        )


@dataclass
class MailConfig:
    enabled: bool = False
    sender: str = ""
    recipient: str = ""
    payload_preview_chars: int = 1800

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "MailConfig":
        return MailConfig(
            enabled=bool(d.get("ENABLED", False)),
            sender=d.get("SENDER", ""),
            recipient=d.get("RECIPIENT", ""),
            payload_preview_chars=int(d.get("PAYLOAD_PREVIEW_CHARS", 1800)),
        )


@dataclass
class StdoutConfig:
    enabled: bool = False
    payload_preview_chars: int = 180

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "StdoutConfig":
        return StdoutConfig(
            enabled=bool(d.get("ENABLED", False)),
            payload_preview_chars=int(d.get("PAYLOAD_PREVIEW_CHARS", 180)),
        )


@dataclass
class LogfileConfig:
    enabled: bool = False
    path: str = ""
    payload_preview_chars: int = 1800

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "LogfileConfig":
        return LogfileConfig(
            enabled=bool(d.get("ENABLED", False)),
            path=d.get("PATH", ""),
            payload_preview_chars=int(d.get("PAYLOAD_PREVIEW_CHARS", 1800)),
        )


@dataclass
class MessageTrigger:
    enabled: EnabledChannels
    title: str

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "MessageTrigger":
        return MessageTrigger(
            enabled=EnabledChannels.from_dict(d.get("ENABLED", {})),
            title=d.get("TITLE", ""),
        )


@dataclass
class InfoTrigger(MessageTrigger):
    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "InfoTrigger":
        return InfoTrigger(
            enabled=EnabledChannels.from_dict(d.get("ENABLED", {})),
            title=d.get("TITLE", ""),
        )


@dataclass
class MissingDataTrigger(MessageTrigger):
    window_minutes: int = 30

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "MissingDataTrigger":
        return MissingDataTrigger(
            enabled=EnabledChannels.from_dict(d.get("ENABLED", {})),
            title=d.get("TITLE", ""),
            window_minutes=int(d.get("WINDOW_MINUTES", 30)),
        )


@dataclass
class DbSizeTrigger(MessageTrigger):
    check_every_hours: int = 24
    warn_mb: int = 500
    crit_mb: int = 800

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "DbSizeTrigger":
        return DbSizeTrigger(
            enabled=EnabledChannels.from_dict(d.get("ENABLED", {})),
            title=d.get("TITLE", ""),
            check_every_hours=int(d.get("CHECK_EVERY_HOURS", 24)),
            warn_mb=int(d.get("WARN_MB", 500)),
            crit_mb=int(d.get("CRIT_MB", 800)),
        )


@dataclass
class BadValuesTrigger(MessageTrigger):
    window_minutes: int = 30
    max_repeat_every_hours: int = 6

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "BadValuesTrigger":
        return BadValuesTrigger(
            enabled=EnabledChannels.from_dict(d.get("ENABLED", {})),
            title=d.get("TITLE", ""),
            window_minutes=int(d.get("WINDOW_MINUTES", 30)),
            max_repeat_every_hours=int(d.get("MAX_REPEAT_EVERY_HOURS", 6)),
        )


@dataclass
class NonDictPayloadTrigger(MessageTrigger):
    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "NonDictPayloadTrigger":
        return NonDictPayloadTrigger(
            enabled=EnabledChannels.from_dict(d.get("ENABLED", {})),
            title=d.get("TITLE", ""),
        )


@dataclass
class MissingTimestampTrigger(MessageTrigger):
    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "MissingTimestampTrigger":
        return MissingTimestampTrigger(
            enabled=EnabledChannels.from_dict(d.get("ENABLED", {})),
            title=d.get("TITLE", ""),
        )


@dataclass
class JsonDecodeErrorTrigger(MessageTrigger):
    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "JsonDecodeErrorTrigger":
        return JsonDecodeErrorTrigger(
            enabled=EnabledChannels.from_dict(d.get("ENABLED", {})),
            title=d.get("TITLE", ""),
        )


@dataclass
class UnknownSensorErrorTrigger(MessageTrigger):
    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "UnknownSensorErrorTrigger":
        return UnknownSensorErrorTrigger(
            enabled=EnabledChannels.from_dict(d.get("ENABLED", {})),
            title=d.get("TITLE", ""),
        )


@dataclass
class MessageConfig:
    subject_prefix: str = ""
    max_repeat_hours: int = 48
    ntfy: NtfyConfig = field(default_factory=NtfyConfig)
    mail: MailConfig = field(default_factory=MailConfig)
    stdout: StdoutConfig = field(default_factory=StdoutConfig)
    logfile: LogfileConfig = field(default_factory=LogfileConfig)
    info: InfoTrigger = field(default_factory=InfoTrigger)
    missing_data: MissingDataTrigger = field(default_factory=MissingDataTrigger)
    db_size: DbSizeTrigger = field(default_factory=DbSizeTrigger)
    bad_values: BadValuesTrigger = field(default_factory=BadValuesTrigger)
    non_dict_payload: NonDictPayloadTrigger = field(default_factory=NonDictPayloadTrigger)
    missing_timestamp: MissingTimestampTrigger = field(default_factory=MissingTimestampTrigger)
    json_decode_error: JsonDecodeErrorTrigger = field(default_factory=JsonDecodeErrorTrigger)
    unknown_sensor_error: UnknownSensorErrorTrigger = field(default_factory=UnknownSensorErrorTrigger)

    @staticmethod
    def load(path: str) -> "MessageConfig":
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)

        msg_triggers = cfg.get("MSG_TRIGGER", {})

        return MessageConfig(
            subject_prefix=cfg.get("SUBJECT_PREFIX", ""),
            max_repeat_hours=int(cfg.get("MAX_REPEAT_HOURS", 48)),
            ntfy=NtfyConfig.from_dict(cfg.get("NTFY", {})),
            mail=MailConfig.from_dict(cfg.get("MAIL", {})),
            stdout=StdoutConfig.from_dict(cfg.get("STDOUT", {})),
            logfile=LogfileConfig.from_dict(cfg.get("LOGFILE", {})),
            info=InfoTrigger.from_dict(msg_triggers.get("INFO", {})),
            missing_data=MissingDataTrigger.from_dict(msg_triggers.get("MISSING_DATA", {})),
            db_size=DbSizeTrigger.from_dict(msg_triggers.get("DB_SIZE", {})),
            bad_values=BadValuesTrigger.from_dict(msg_triggers.get("BAD_VALUES", {})),
            non_dict_payload=NonDictPayloadTrigger.from_dict(msg_triggers.get("NON_DICT_PAYLOAD", {})),
            missing_timestamp=MissingTimestampTrigger.from_dict(msg_triggers.get("MISSING_TIMESTAMP", {})),
            json_decode_error=JsonDecodeErrorTrigger.from_dict(msg_triggers.get("JSON_DECODE_ERROR", {})),
            unknown_sensor_error=UnknownSensorErrorTrigger.from_dict(msg_triggers.get("UNKNOWN_SENSOR_ERROR", {})),
        )


# ---------------------------
# Demo / quick test
# ---------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("SYSTEM CONFIG TEST")
    print("=" * 60)
    config = SystemConfig.load("sensor_config.json")

    print("DB File:", config.db_file)
    print("MQTT   :", config.mqtt.host, config.mqtt.port, config.mqtt.topic)
    print("Tables :", list(config.tables.keys()))

    th = config.tables.get("measurements_th")
    if th:
        s = th.get_sensor("temperature1")
        print("Sensor:", s)
        print("sanitize -9999.0 ->", s.sanitize_value("-9999.0"))
        print("sanitize '21.37' ->", s.sanitize_value("21.37"))

    print("\n" + "=" * 60)
    print("MESSAGE CONFIG TEST")
    print("=" * 60)
    msg_config = MessageConfig.load("msg_config.json")

    print("Subject Prefix:", msg_config.subject_prefix)
    print("Max Repeat Hours:", msg_config.max_repeat_hours)
    print("Ntfy Enabled:", msg_config.ntfy.enabled)
    print("Ntfy Server:", msg_config.ntfy.server)
    print("Ntfy Topic:", msg_config.ntfy.topic)
    print("Mail Enabled:", msg_config.mail.enabled)
    print("Mail From:", msg_config.mail.sender)
    print("Mail To:", msg_config.mail.recipient)
    print("Stdout Enabled:", msg_config.stdout.enabled)
    print("Logfile Enabled:", msg_config.logfile.enabled)
    print("Logfile Path:", msg_config.logfile.path)

    print("\nMessage Triggers:")
    print(f"  INFO: {msg_config.info.title} - {msg_config.info.enabled.logfile}")
    print(f"  MISSING_DATA: {msg_config.missing_data.title} - Window: {msg_config.missing_data.window_minutes}min")
    print(f"  DB_SIZE: {msg_config.db_size.title} - Warn: {msg_config.db_size.warn_mb}MB, Crit: {msg_config.db_size.crit_mb}MB")
    print(f"  BAD_VALUES: {msg_config.bad_values.title} - Max Repeat: {msg_config.bad_values.max_repeat_every_hours}h")
