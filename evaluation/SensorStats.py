from dataclasses import dataclass

from evaluation.utils import format_iso_timestamp

@dataclass
class SensorStats:
    sensor: object
    df: object
    first_val: float
    first_timestamp: str
    last_val: float
    last_timestamp: str
    min_val: float
    min_timestamp: str
    max_val: float
    max_timestamp: str
    mean_value: float

    def formatted_first_timestamp(self, fmt="%Y-%m-%d %H:%M"):
        return format_iso_timestamp(self.first_timestamp, fmt)

    def formatted_last_timestamp(self, fmt="%Y-%m-%d %H:%M"):
        return format_iso_timestamp(self.last_timestamp, fmt)

    def formatted_min_timestamp(self, fmt="%Y-%m-%d %H:%M"):
        return format_iso_timestamp(self.min_timestamp, fmt)

    def formatted_max_timestamp(self, fmt="%Y-%m-%d %H:%M"):
        return format_iso_timestamp(self.max_timestamp, fmt)