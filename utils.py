# utils.py
import sqlite3
import subprocess 
import datetime
import sys

# Importiere Konfiguration
import config

# Globale Status-Variablen für die Fehlerbegrenzung
LAST_ERROR_MAIL_DATE = None 

# --- E-MAIL-FUNKTIONEN ---

def send_mail(subject, body):
    """Versendet eine E-Mail über den lokalen 'mail'-Befehl."""
    try:
        command = [
            "mail",
            "-s", subject,
            config.MAIL_RECIPIENT
        ]
        
        subprocess.run(
            command,
            input=body.encode('utf-8'),
            capture_output=True,
            check=True
        )
        print(f"📧 E-Mail gesendet: '{subject}'.")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Fehler beim Senden der E-Mail (mailutils/msmtp): {e}")
        return False
    except FileNotFoundError:
        print("❌ Fehler: Der 'mail'-Befehl wurde nicht gefunden. Ist mailutils installiert?")
        return False
    except Exception as e:
        print(f"❌ Unbekannter Fehler beim Senden der E-Mail: {e}")
        return False


def check_and_send_error_mail(subject, body):
    """Versendet eine E-Mail nur einmal pro Tag."""
    global LAST_ERROR_MAIL_DATE
    current_date = datetime.date.today().isoformat()
    
    if LAST_ERROR_MAIL_DATE == current_date:
        return

    if send_mail(subject, body):
        LAST_ERROR_MAIL_DATE = current_date
        
# --- DATENBANKFUNKTIONEN ---

def initialize_database():
    """Erstellt die Datenbankverbindung und die Tabelle."""
    try:
        conn = sqlite3.connect(config.DB_FILE)
        cursor = conn.cursor()
        
        col = config.COLUMN_NAMES
        
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS measurements (
                {col["id"]} INTEGER PRIMARY KEY AUTOINCREMENT,
                {col["timestamp_iso"]} TEXT NOT NULL,
                {col["datum_utc"]} TEXT,
                {col["uhrzeit_utc"]} TEXT,
                {col["gateway_id"]} TEXT,
                {col["temp1"]} REAL,
                {col["feuchte1"]} REAL,
                {col["temp2"]} REAL,
                {col["feuchte2"]} REAL,
                {col["temp3"]} REAL,
                {col["feuchte3"]} REAL,
                {col["temp_in"]} REAL,
                {col["feuchte_in"]} REAL,
                {col["battery_ok"]} BOOLEAN,
                {col["created_at"]} TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()
        print(f"✅ Datenbank {config.DB_FILE} initialisiert.")
        
    except sqlite3.Error as e:
        print(f"❌ Fehler bei der Datenbankinitialisierung: {e}")
        
def insert_record(record):
    """Fügt einen einzelnen Messdatensatz in die Datenbank ein."""
    try:
        conn = sqlite3.connect(config.DB_FILE)
        cursor = conn.cursor()
        
        columns = config.INSERT_COLUMNS
        placeholders = ', '.join(['?'] * len(columns))
        
        # Logische Keys
        logical_keys = [
            "timestamp_iso", "datum_utc", "uhrzeit_utc", "gateway_id",
            "temp1", "feuchte1", "temp2", "feuchte2", "temp3", "feuchte3", 
            "temp_in", "feuchte_in", "battery_ok"
        ]
        values = [record.get(key) for key in logical_keys]

        sql = f"INSERT INTO measurements ({', '.join(columns)}) VALUES ({placeholders})"
        cursor.execute(sql, values)
        
        conn.commit()
        conn.close()
        
    except sqlite3.Error as e:
        print(f"❌ Fehler beim Einfügen des Datensatzes: {e}")

# --- DATENEXTRAKTIONSFUNKTION ---

def safe_extract_value(data, key):
    """Extrahiert einen Messwert robust."""
    value = data.get(key)
    if isinstance(value, list):
        return value[0] if value else None
    elif isinstance(value, (int, float)):
        return value
    elif isinstance(value, str) and value.replace('.', '', 1).isdigit():
        try:
            return float(value)
        except ValueError:
            return None
    return None