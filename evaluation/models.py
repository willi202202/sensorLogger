# models.py
import json


class Sensor:
    def __init__(self, sensor_id, data):
        self.id = sensor_id
        self.name = data.get("name", sensor_id)
        self.alias = data.get("alias", sensor_id)
        self.unit = data.get("unit", "N/A")
        self.round = data.get("round", 3)

        self.limits = tuple(data.get("limits", (None, None)))
        self.warn = tuple(data.get("warn", (None, None)))
        self.alarm = tuple(data.get("alarm", (None, None)))

        self.plot = data.get("plot", {})

    def __repr__(self):
        return f"Sensor(id={self.id}, alias={self.alias}, unit={self.unit})"


class SystemConfig:
    def __init__(self, json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)

        self.db_file = cfg.get("DB_FILE", "")
        self.table_name = cfg.get("TABLE_NAME", "")
        self.timestamp_field = cfg.get("TIMESTAMP_FIELD", "")

        self.sensors = {}
        for sensor_id, sensor_data in cfg.get("SENSORS", {}).items():
            self.sensors[sensor_id] = Sensor(sensor_id, sensor_data)

    def get_sensor(self, sensor_id):
        return self.sensors.get(sensor_id)

    def get_sensor_by_alias(self, alias):
        for s in self.sensors.values():
            if s.alias == alias:
                return s
        return None

if __name__ == "__main__":
    config = SystemConfig("sensors.json")

    print(config)
    print("DB File         :", config.db_file)
    print("Table Name      :", config.table_name)
    print("Timestamp Field :", config.timestamp_field)

    s = config.get_sensor_by_alias("temp1")
    print(s)