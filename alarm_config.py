# alarm_config.py
from dataclasses import dataclass
from typing import List, Tuple
import json
from pathlib import Path


@dataclass
class AlarmButton:
    """Einzelne Alarm-Einstellung"""
    button_title: str
    default: bool
    sensor_alias: str
    default_alarm: Tuple[int, int]  # (min, max)

    def __post_init__(self):
        """Konvertiere default_alarm zu Tuple wenn nötig"""
        if isinstance(self.default_alarm, list):
            self.default_alarm = tuple(self.default_alarm)

    @property
    def alarm_min(self) -> int:
        return self.default_alarm[0]

    @property
    def alarm_max(self) -> int:
        return self.default_alarm[1]

    def to_dict(self) -> dict:
        """Konvertiere zu Dictionary für JSON"""
        return {
            "button_title": self.button_title,
            "default": self.default,
            "sensor_alias": self.sensor_alias,
            "default_alarm": list(self.default_alarm)
        }


@dataclass
class AlarmConfig:
    """Gesamte Alarm-Konfiguration"""
    enbutton: List[AlarmButton]

    @classmethod
    def from_json(cls, filepath: str) -> "AlarmConfig":
        """Lade Konfiguration aus JSON-Datei"""
        try:
            path = Path(filepath)
            if not path.exists():
                raise FileNotFoundError(f"Datei nicht gefunden: {filepath}")

            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            buttons = [AlarmButton(**btn) for btn in data.get("enbutton", [])]
            return cls(enbutton=buttons)

        except json.JSONDecodeError as e:
            raise ValueError(f"JSON-Fehler in {filepath}: {e}")

    def to_json(self, filepath: str) -> None:
        """Speichere Konfiguration in JSON-Datei"""
        path = Path(filepath)
        data = {
            "enbutton": [btn.to_dict() for btn in self.enbutton]
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def get_alarm_by_sensor(self, sensor_alias: str) -> AlarmButton:
        """Finde Alarm-Einstellung nach Sensor-Alias"""
        for btn in self.enbutton:
            if btn.sensor_alias == sensor_alias:
                return btn
        raise ValueError(f"Sensor nicht gefunden: {sensor_alias}")

    def get_active_alarms(self) -> List[AlarmButton]:
        """Gebe nur aktivierte Alarme zurück"""
        return [btn for btn in self.enbutton if btn.default]

    def get_inactive_alarms(self) -> List[AlarmButton]:
        """Gebe nur deaktivierte Alarme zurück"""
        return [btn for btn in self.enbutton if not btn.default]

    def update_alarm(self, sensor_alias: str, min_val: int, max_val: int, enabled: bool = None) -> None:
        """Update Alarm-Werte für einen Sensor"""
        alarm = self.get_alarm_by_sensor(sensor_alias)
        alarm.default_alarm = (min_val, max_val)
        if enabled is not None:
            alarm.default = enabled

    def to_dict(self) -> dict:
        """Konvertiere zu Dictionary"""
        return {
            "enbutton": [btn.to_dict() for btn in self.enbutton]
        }

    def __repr__(self) -> str:
        return f"AlarmConfig(alarms={len(self.enbutton)}, active={len(self.get_active_alarms())})"
