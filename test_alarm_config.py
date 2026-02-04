# test_alarm_config.py
"""
Test-Skript zum Anzeigen der Alarm-Konfiguration
"""

from alarm_config import AlarmConfig
import os

# Lade Konfiguration
config_path = os.path.join(os.path.dirname(__file__), "HTML", "alarm_button.json")
alarm_config = AlarmConfig.from_json(config_path)

print(f"\n📊 Alarm-Konfiguration: {alarm_config}")
print(f"   Gesamt: {len(alarm_config.enbutton)} Alarme")
print(f"   Aktiv: {len(alarm_config.get_active_alarms())}")
print(f"   Inaktiv: {len(alarm_config.get_inactive_alarms())}")

print("\n" + "="*80)
print("📋 ALARM-KONFIGURATION DETAILS")
print("="*80)

# Tabellen-Header
print(f"\n{'Nr.':<4} {'Status':<10} {'Button':<25} {'Sensor':<25} {'Min':<6} {'Max':<6}")
print("-" * 80)

# Einträge
for i, alarm in enumerate(alarm_config.enbutton, 1):
    status = "✓ AKTIV" if alarm.default else "✗ INAKTIV"
    print(f"{i:<4} {status:<10} {alarm.button_title:<25} {alarm.sensor_alias:<25} {alarm.alarm_min:<6} {alarm.alarm_max:<6}")

print("\n" + "="*80)
print("Detaillierte Ansicht:")
print("="*80)

for i, alarm in enumerate(alarm_config.enbutton, 1):
    status_icon = "✓" if alarm.default else "✗"
    print(f"\n{i}. {alarm.button_title} [{status_icon}]")
    print(f"   Sensor Alias:    {alarm.sensor_alias}")
    print(f"   Alarmbereich:    [{alarm.alarm_min}, {alarm.alarm_max}]")
    print(f"   Bereich-Größe:   {alarm.alarm_max - alarm.alarm_min}")
    print(f"   Status:          {'AKTIV' if alarm.default else 'INAKTIV'}")

print("\n" + "="*80 + "\n")

