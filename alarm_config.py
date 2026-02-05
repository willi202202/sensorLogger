# alarm_config.py
from dataclasses import dataclass
from typing import List, Tuple, Dict, Any


@dataclass
class AlarmButton:
    """Einzelne Alarm-Einstellung (In-Memory-Modell)"""
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

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiere zu Dictionary für API/JSON"""
        return {
            "button_title": self.button_title,
            "default": self.default,
            "sensor_alias": self.sensor_alias,
            "default_alarm": list(self.default_alarm)
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AlarmButton":
        """Erstelle aus Dictionary (von API/JSON)"""
        return cls(**data)


@dataclass
class AlarmConfig:
    """Gesamte Alarm-Konfiguration (In-Memory-Modell)
    
    Wird vom Backend über APIs aktualisiert, nicht von JSON geladen/gespeichert.
    """
    enbutton: List[AlarmButton]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AlarmConfig":
        """Erstelle Config aus Dictionary (z.B. von API)"""
        buttons = [AlarmButton.from_dict(btn) for btn in data.get("enbutton", [])]
        config = cls(enbutton=buttons)
        print(f"📥 ALARM CONFIG UPDATED: {len(buttons)} Alarme geladen")
        return config

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiere zu Dictionary für API/JSON-Response"""
        return {
            "enbutton": [btn.to_dict() for btn in self.enbutton]
        }

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
        old_alarm = alarm.default_alarm
        old_enabled = alarm.default
        
        alarm.default_alarm = (min_val, max_val)
        if enabled is not None:
            alarm.default = enabled
        
        print(f"🔔 UPDATE ALARM: {sensor_alias}")
        if old_alarm != alarm.default_alarm:
            print(f"   Alarm-Bereich: {old_alarm} → {alarm.default_alarm}")
        if old_enabled != alarm.default:
            print(f"   Aktiviert: {old_enabled} → {alarm.default}")

    def add_alarm(self, button_title: str, sensor_alias: str, default_alarm: Tuple[int, int], enabled: bool = True) -> None:
        """Füge neue Alarm-Einstellung hinzu"""
        new_alarm = AlarmButton(
            button_title=button_title,
            default=enabled,
            sensor_alias=sensor_alias,
            default_alarm=default_alarm
        )
        self.enbutton.append(new_alarm)
        print(f"➕ ADD ALARM: {sensor_alias} ({button_title})")
        print(f"   Bereich: {default_alarm}, Aktiviert: {enabled}")

    def remove_alarm(self, sensor_alias: str) -> None:
        """Entferne Alarm-Einstellung"""
        old_count = len(self.enbutton)
        self.enbutton = [btn for btn in self.enbutton if btn.sensor_alias != sensor_alias]
        if len(self.enbutton) < old_count:
            print(f"➖ REMOVE ALARM: {sensor_alias}")

    def toggle_alarm(self, sensor_alias: str) -> None:
        """Toggle Ein/Aus für einen Sensor"""
        alarm = self.get_alarm_by_sensor(sensor_alias)
        alarm.default = not alarm.default
        print(f"🔄 TOGGLE ALARM: {sensor_alias} → {'ON' if alarm.default else 'OFF'}")

    def __repr__(self) -> str:
        return f"AlarmConfig(alarms={len(self.enbutton)}, active={len(self.get_active_alarms())})"

