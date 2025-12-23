# exceptions.py
# Zentrale Exception-Hierarchie fuer mqtt_logger.py / models.py
#
# Idee:
# - Alle "erwartbaren" Fehler im Logger als MQTTLoggerError (oder Subklasse) werfen
# - Logger kann dann zentral: loggen + Mail schicken + rate-limit
#
# Naming: bewusst klar & technisch, ohne Schnickschnack.

from __future__ import annotations


class MQTTLoggerError(RuntimeError):
    """Base class for all MQTT logger related errors."""
    pass


# ----------------------------
# Payload / Protokoll / Parsing
# ----------------------------

class JSONPayloadDecodeError(MQTTLoggerError):
    """Payload is not valid JSON / cannot be decoded."""
    pass


class PayloadFormatError(MQTTLoggerError):
    """Payload has unexpected structure/type (e.g. not a dict)."""
    pass


class MissingTimestampError(MQTTLoggerError):
    """Required timestamp field is missing or empty."""
    pass


class UnknownSensorError(MQTTLoggerError):
    """Sensor ID not found in config / no routing possible."""
    pass


# ----------------------------
# Data content / validation
# ----------------------------

class InvalidFieldTypeError(MQTTLoggerError):
    """A field has an unexpected type (e.g., list where scalar expected)."""
    pass


class InvalidFieldValueError(MQTTLoggerError):
    """A field has an invalid/unparseable value (e.g., 'abc' for float)."""
    pass


class MissingRequiredFieldError(MQTTLoggerError):
    """A required field (other than timestamp) is missing."""
    pass


# ----------------------------
# Configuration / Model errors
# ----------------------------

class ConfigError(MQTTLoggerError):
    """Configuration is invalid or inconsistent."""
    pass


class SchemaMismatchError(MQTTLoggerError):
    """Database schema does not match expected columns."""
    pass


# ----------------------------
# Database / IO errors
# ----------------------------

class DatabaseError(MQTTLoggerError):
    """Database operation failed (insert, locked too long, etc.)."""
    pass


class MailError(MQTTLoggerError):
    """Mail sending failed (optional use if you want to escalate)."""
    pass


# ----------------------------
# Internal / unexpected
# ----------------------------

class InternalLoggerError(MQTTLoggerError):
    """Unexpected internal error (bug)."""
    pass
