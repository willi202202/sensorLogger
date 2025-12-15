# errors.py
class ConfigError(Exception):
    """Allgemeiner Konfigurationsfehler."""


class DatabaseFileNotFound(ConfigError):
    """DB-File existiert nicht."""

class Database(ConfigError):
    """Werte nicht gültig oder nicht gefunden."""

class TableNotFound(ConfigError):
    """Tabelle in der DB existiert nicht."""


class ColumnNotFound(ConfigError):
    """Spalte in der Tabelle existiert nicht."""

class ReportsClean(ConfigError):
    """Reports noch frisch genug, keine Neugenerierung."""
