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
        return f"Sensor(key={self.key}, alias={self.alias}, type={self.field_type}, unit={self.unit})"

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

        

        if t in ("tuple_float", "tuple_number"):
            try:
                val = float(raw[0])
            except Exception:
                return None
            if self.round is not None:
                try:
                    val = round(val, int(self.round))
                except Exception:
                    pass
            return val

        if t in ("float", "number"):
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
class MailTrigger:
    enabled: bool = False

    # generic rate limiting
    repeat_every_hours: Optional[int] = None
    max_repeat_every_hours: Optional[int] = None

    # window checks
    window_minutes: Optional[int] = None

    # db size
    check_every_hours: Optional[int] = None
    warn_mb: Optional[int] = None
    crit_mb: Optional[int] = None

    payload_preview_chars: Optional[int] = None
    min_count_before_mail: Optional[int] = None

    # Exception policy flags
    raise_on_unknown_sensor_error: Optional[bool] = False
    raise_on_non_dict_payload: Optional[bool] = False
    raise_on_missing_timestamp: Optional[bool] = False
    raise_on_json_decode_error: Optional[bool] = False

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "MailTrigger":
        return MailTrigger(
            enabled=bool(d.get("ENABLED", False)),
            repeat_every_hours=d.get("REPEAT_EVERY_HOURS"),
            max_repeat_every_hours=d.get("MAX_REPEAT_EVERY_HOURS"),
            window_minutes=d.get("WINDOW_MINUTES"),
            check_every_hours=d.get("CHECK_EVERY_HOURS"),
            warn_mb=d.get("WARN_MB"),
            crit_mb=d.get("CRIT_MB"),
            payload_preview_chars=d.get("PAYLOAD_PREVIEW_CHARS"),
            min_count_before_mail=d.get("MIN_COUNT_BEFORE_MAIL"),
            raise_on_unknown_sensor_error=bool(d.get("RAISE_ON_UNKNOWN_SENSOR_ERROR", False)),
            raise_on_non_dict_payload=bool(d.get("RAISE_ON_NON_DICT_PAYLOAD", False)),
            raise_on_missing_timestamp=bool(d.get("RAISE_ON_MISSING_TIMESTAMP", False)),
            raise_on_json_decode_error=bool(d.get("RAISE_ON_JSON_DECODE_ERROR", False)),
        )


@dataclass
class MailConfig:
    enabled: bool = False
    sender: str = ""
    recipient: str = ""
    subject_prefix: str = "[MQTT-LOGGER]"

    trigger_info: MailTrigger = field(default_factory=MailTrigger)
    trigger_missing_data: MailTrigger = field(default_factory=MailTrigger)
    trigger_db_size: MailTrigger = field(default_factory=MailTrigger)
    trigger_bad_values: MailTrigger = field(default_factory=MailTrigger)
    trigger_exceptions: MailTrigger = field(default_factory=MailTrigger)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "MailConfig":
        return MailConfig(
            enabled=bool(d.get("ENABLED", False)),
            sender=d.get("SENDER", ""),
            recipient=d.get("RECIPIENT", ""),
            subject_prefix=d.get("SUBJECT_PREFIX", "[MQTT-LOGGER]"),

            trigger_info=MailTrigger.from_dict(d.get("TRIGGER_INFO", {}) or {}),
            trigger_missing_data=MailTrigger.from_dict(d.get("TRIGGER_ALARM_ON_MISSING_DATA", {}) or {}),
            trigger_db_size=MailTrigger.from_dict(d.get("TRIGGER_ALARM_ON_DB_SIZE", {}) or {}),
            trigger_bad_values=MailTrigger.from_dict(d.get("TRIGGER_ALARM_ON_BAD_VALUES", {}) or {}),
            trigger_exceptions=MailTrigger.from_dict(d.get("TRIGGER_ALARM_ON_EXCEPTIONS", {}) or {}),
        )

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
# Demo / quick test
# ---------------------------

if __name__ == "__main__":
    config = SystemConfig.load("sensor_config.json")

    print("DB File:", config.db_file)
    print("MQTT   :", config.mqtt.host, config.mqtt.port, config.mqtt.topic)
    print("Tables :", list(config.tables.keys()))

    th = config.tables.get("measurements_th")
    if th:
        s = th.get_sensor("temperature1")
        print("Sensor:", s)
        print("sanitize -9999.0 ->", s.sanitize_value(-9999.0))
        print("sanitize '21.37' ->", s.sanitize_value("21.37"))
