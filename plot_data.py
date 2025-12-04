# plot_data.py
# python3 plot_data.py temp_innen temp_aussen1 --start "2025-12-03 18:00:00"
import sqlite3
import datetime
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.dates import DateFormatter, MinuteLocator, HourLocator
import argparse
import sys

# Importiere Konfiguration
import config

def create_multi_plot(sensor_keys, start_time_str=None, end_time_str=None):
    """
    Erstellt einen Graphen für die angegebenen Sensoren über den definierten Zeitraum
    und speichert ihn als PDF.
    
    Args:
        sensor_keys (list): Eine Liste der logischen Schlüssel der Sensoren (z.B. ['temp_in', 'temp1']).
        start_time_str (str): Startdatum/-zeit im Format YYYY-MM-DD HH:MM:SS (UTC).
        end_time_str (str): Enddatum/-zeit im Format YYYY-MM-DD HH:MM:SS (UTC).
    """
    
    # --- 1. Überprüfung der Sensor-Keys ---
    valid_keys = []
    db_column_names = []
    
    for key in sensor_keys:
        if key in config.COLUMN_NAMES:
            valid_keys.append(key)
            db_column_names.append(config.COLUMN_NAMES[key])
        else:
            print(f"❌ Fehler: Sensor-Key '{key}' ist in config.COLUMN_NAMES nicht definiert und wird ignoriert.")

    if not valid_keys:
        print("❌ Keine gültigen Sensoren zum Plotten übrig.")
        return

    # Die Zeitspalte wird immer benötigt
    time_column_name = config.COLUMN_NAMES['timestamp_iso']
    
    conn = None
    try:
        conn = sqlite3.connect(config.DB_FILE)
        
        # --- 2. SQL-Abfrage erstellen ---
        # Wähle die Zeitspalte und alle benötigten Sensor-Spalten
        select_columns = [time_column_name] + db_column_names
        select_columns_str = ", ".join(select_columns)
        
        sql_query = f"""
            SELECT {select_columns_str}
            FROM measurements 
            WHERE 1=1 
        """
        
        # Zeitfilter hinzufügen
        if start_time_str:
            sql_query += f" AND {time_column_name} >= '{start_time_str}'"
        if end_time_str:
            sql_query += f" AND {time_column_name} <= '{end_time_str}'"
            
        sql_query += f" ORDER BY {time_column_name} ASC;"

        # Daten in Pandas DataFrame laden
        df = pd.read_sql(sql_query, conn)
        
        if df.empty:
            print("ℹ️ Keine Daten für den gewählten Zeitraum gefunden.")
            return

        # --- 3. Datenvorbereitung ---
        # Konvertieren des Zeitstempels in das datetime-Format
        df[time_column_name] = pd.to_datetime(df[time_column_name], errors='coerce')
        df.dropna(subset=[time_column_name], inplace=True)

        # Optional: Entferne Zeilen, wo alle Sensorwerte NULL sind (reduziert Datenmenge)
        df.dropna(subset=db_column_names, how='all', inplace=True)
        
        if df.empty:
             print("ℹ️ Keine verwertbaren Daten für die gewählten Sensoren und Zeitraum gefunden.")
             return

        # --- 4. Plot erstellen ---
        
        # Setze das Dateiformat für den Output
        sensor_list_str = "_".join(valid_keys)
        file_name = f"plot_{sensor_list_str}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        
        fig, ax = plt.subplots(figsize=(12, 6))
        
        # Iteriere über alle gültigen Sensor-Keys und plotte die Daten
        for key in valid_keys:
            db_col = config.COLUMN_NAMES[key]
            ax.plot(df[time_column_name], df[db_col], label=f'{db_col} ({key})', linewidth=2)
        
        # Titel und Achsenbeschriftungen
        plot_title = ", ".join([config.COLUMN_NAMES[k] for k in valid_keys])
        ax.set_title(f"Verlauf von: {plot_title}\nVon {df[time_column_name].min()} bis {df[time_column_name].max()}", fontsize=14)
        ax.set_xlabel("Zeit (UTC)")
        
        # Annahme: Alle geplotteten Sensoren haben dieselbe Einheit (z.B. Temperatur ODER Feuchte)
        # Wenn Sie Sensoren mit unterschiedlichen Einheiten plotten möchten (z.B. Temp und Feuchte),
        # benötigen Sie eine zweite Y-Achse (ax.twinx()).
        first_key = valid_keys[0]
        unit = "°C" if "temp" in first_key else "%" if "feuchte" in first_key else "Wert"
        ax.set_ylabel(f"Messwert ({unit})")
        
        # X-Achsen-Formatierung
        time_diff = df[time_column_name].max() - df[time_column_name].min()
        if time_diff.total_seconds() < 3600 * 5: # Weniger als 5 Stunden
            ax.xaxis.set_major_formatter(DateFormatter('%H:%M'))
            ax.xaxis.set_major_locator(MinuteLocator(interval=15))
        elif time_diff.total_seconds() < 3600 * 48: # Weniger als 2 Tage
            ax.xaxis.set_major_formatter(DateFormatter('%H:%M\n%d.%m.'))
            ax.xaxis.set_major_locator(HourLocator(interval=6))
        else:
            ax.xaxis.set_major_formatter(DateFormatter('%Y-%m-%d'))
            
        fig.autofmt_xdate(rotation=45)
        ax.grid(True, linestyle='--', alpha=0.7)
        ax.legend()
        
        # Layout anpassen und PDF speichern
        plt.tight_layout()
        plt.savefig(file_name, format='pdf')
        plt.close(fig)

        print(f"\n✅ Graph erfolgreich erstellt und gespeichert als: {file_name}")

    except sqlite3.Error as e:
        print(f"❌ Datenbankfehler: {e}")
    except Exception as e:
        print(f"❌ Allgemeiner Fehler beim Plotten: {e}")
    finally:
        if conn:
            conn.close()

def main():
    """Definiert die Kommandozeilen-Argumente und ruft die Plot-Funktion auf."""
    
    # 1. Argument Parser einrichten
    parser = argparse.ArgumentParser(
        description="Erstellt einen Zeitverlaufsgraphen der Sensordaten als PDF.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    
    available_keys = [k for k in config.COLUMN_NAMES.keys() if k not in ['id', 'timestamp_iso', 'datum_utc', 'uhrzeit_utc', 'gateway_id', 'battery_ok', 'created_at']]
    keys_str = ", ".join(available_keys)
    
    # ⭐ Änderung: 'nargs='+' erlaubt 1 oder mehr Argumente für diesen Parameter
    parser.add_argument(
        "sensor_key", 
        nargs='+',  # Erlaubt mehrere Sensoren als Argumente
        choices=available_keys,
        help=f"Ein oder mehrere logische Namen der Sensoren, die geplottet werden sollen. Auswahl: {keys_str}"
    )
    parser.add_argument(
        "-s", "--start", 
        type=str, 
        default=None,
        help="Startzeitpunkt (UTC) im Format YYYY-MM-DD HH:MM:SS (z.B. '2025-12-01 10:00:00')"
    )
    parser.add_argument(
        "-e", "--end", 
        type=str, 
        default=None,
        help="Endzeitpunkt (UTC) im Format YYYY-MM-DD HH:MM:SS (z.B. '2025-12-02 10:00:00')"
    )
    
    # 2. Argumente parsen und Funktion aufrufen
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)
        
    args = parser.parse_args()
    
    # Rufe die Funktion mit der Liste der Sensoren auf
    create_multi_plot(args.sensor_key, args.start, args.end)

if __name__ == "__main__":
    main()