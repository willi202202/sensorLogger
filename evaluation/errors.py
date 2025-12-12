# errors.py
class ConfigError(Exception):
    """Allgemeiner Konfigurationsfehler."""


class DatabaseFileNotFound(ConfigError):
    """DB-File existiert nicht."""


class TableNotFound(ConfigError):
    """Tabelle in der DB existiert nicht."""


class ColumnNotFound(ConfigError):
    """Spalte in der Tabelle existiert nicht."""
