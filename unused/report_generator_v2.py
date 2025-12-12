import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import json
import os
import sys
import glob
from datetime import datetime, timedelta
import warnings
import pytz # NEU: Für Zeitzonen-Handling

# Unterdrückt Matplotlib-Warnungen, die manchmal im figtext-Bereich auftreten
warnings.filterwarnings("ignore", category=UserWarning)

# Importiere Konfiguration aus der config.py
import config

# ⭐ WICHTIG: Ihre lokale Zeitzone definieren (z.B. Europe/Berlin für CET/CEST)
# Prüfen Sie Ihre Zeitzone mit dem Befehl 'timedatectl' auf dem Raspberry Pi.
LOCAL_TIMEZONE = 'Europe/Berlin' 

# --- Konstanten und Utility-Funktionen ---

def ensure_dir_exists(path):
    """Stellt sicher, dass das Verzeichnis existiert."""
    os.makedirs(path, exist_ok=True)

def cleanup_old_reports(log_path, report_id, max_pdfs):
    """
    Löscht die ältesten PDF-Dateien in einem Verzeichnis, 
    wenn die maximale Anzahl überschritten wird.
    """
    try:
        # Suchmuster für die Berichte basierend auf der report_id
        search_pattern = os.path.join(log_path, f"{report_id}_*.pdf")
        list_of_files = glob.glob(search_pattern)

        if len(list_of_files) > max_pdfs:
            # Sortiert nach Änderungszeitpunkt (getmtime) - ältester zuerst
            list_of_files.sort(key=os.path.getmtime)
            
            # Berechnet die Anzahl der zu löschenden Dateien
            num_to_delete = len(list_of_files) - max_pdfs
            
            print(f"   🧹 Max. Limit ({max_pdfs}) überschritten. Lösche {num_to_delete} älteste Dateien.")
            
            for i in range(num_to_delete):
                file_to_delete = list_of_files[i]
                os.remove(file_to_delete)
                print(f"     -> Gelöscht: {os.path.basename(file_to_delete)}")
                
    except Exception as e:
        print(f"   ❌ Fehler bei der Archiv-Wartung in {log_path}: {e}")

# --- Hauptlogik: Datenabfrage und Plot-Generierung ---

def fetch_and_plot_report(report_config):
    """
    Führt die Datenabfrage, Berechnung, Glättung und PDF-Generierung für
    einen einzelnen Bericht aus.
    """
    report_id = report_config["report_id"]
    log_path = report_config["log_path"]
    duration_days = report_config["duration_days"]
    values_period_m = report_config["values_period_m"]
    interpolation_method = report_config["interpolate"]
    
    print(f"\n--- Starte Bericht: {report_config['name']} ({report_id}) ---")

    # 1. Zeitfenster definieren (NEUE, zeitzonenbewusste Berechnung)
    
    local_tz = pytz.timezone(LOCAL_TIMEZONE)
    
    # Heutiges Datum in lokaler Zeit (ohne Zeitangabe)
    today_local = datetime.now(local_tz).replace(hour=0, minute=0, second=0, microsecond=0)
    
    # report_end_dt ist heute um 00:00:00 in lokaler Zeit
    report_end_dt = today_local 
    
    # report_start_dt ist duration_days Tage zurück
    report_start_dt = report_end_dt - timedelta(days=duration_days)
    
    # Wir verwenden NICHT UTC-Strings mehr, sondern lokale, zeitzonenunabhängige Strings 
    # für die Abfrage, da SQLite Strings ohne Zeitzonen speichert.
    start_time_str = report_start_dt.strftime('%Y-%m-%d %H:%M:%S')
    end_time_str = report_end_dt.strftime('%Y-%m-%d %H:%M:%S')

    # Filename basiert auf dem ENDDATUM des Berichts (gestern, 23:59:59 Uhr)
    report_date_str = (report_end_dt - timedelta(seconds=1)).strftime('%Y-%m-%d')
    file_name = f"{report_id}_{report_date_str}.pdf"
    full_file_path = os.path.join(log_path, file_name)

    # 2. Existenzprüfung
    if os.path.exists(full_file_path):
        print(f"   ⚠️ Bericht für {report_date_str} existiert bereits. Überspringe Generierung.")
        cleanup_old_reports(log_path, report_id, report_config["max_pdfs"])
        return

    # ⭐ Wichtig: Ausgabe zeigt nun lokale Zeitzone an (obwohl der String selbst keine TZ hat)
    print(f"   -> Datenzeitraum (Lokal): {start_time_str} bis {end_time_str}")
    
    # 3. Datenbankabfrage und Glättung
    
    conn = None
    all_data = [] 
    
    try:
        conn = sqlite3.connect(config.DB_FILE)
        
        # Liste der DB-Spaltennamen für die Abfrage
        db_cols_to_query = [config.COLUMN_NAMES.get(s['key']) for s in report_config['sensors']]
        db_cols_to_query = [col for col in db_cols_to_query if col]
        
        if not db_cols_to_query:
            print("   ❌ Fehler: Keine gültigen Sensoren oder fehlende Spaltennamen in config.py gefunden.")
            return

        time_col = config.COLUMN_NAMES['timestamp_iso']
        select_cols_str = time_col + ", " + ", ".join(db_cols_to_query)
        
        # SQL-Abfrage mit Zeitfilter
        sql_query = f"""
            SELECT {select_cols_str}
            FROM measurements 
            WHERE {time_col} >= '{start_time_str}' AND {time_col} < '{end_time_str}'
            ORDER BY {time_col} ASC;
        """
        
        df_raw = pd.read_sql(sql_query, conn)
        
        # 🚨 Hinzugefügte Prüfung: Wenn die Abfrage Daten liefert, aber keine Zeile mit Werten
        if df_raw.empty or len(df_raw.dropna(subset=db_cols_to_query)) == 0:
            print("   ℹ️ Keine verwertbaren Daten für diesen Zeitraum gefunden.")
            return

        # Zeitstempel konvertieren und als Index setzen
        # Wichtig: Pandas liest den String als NAIVEN (lokalen) Zeitstempel
        df_raw[time_col] = pd.to_datetime(df_raw[time_col]) 
        df_raw.set_index(time_col, inplace=True)
        
        # DataFrame für den Plot (nach Resampling)
        df_plot = pd.DataFrame(index=df_raw.index)

        # Resampling und Statistik-Erstellung für jeden Sensor
        for sensor_spec in report_config['sensors']:
            key = sensor_spec['key']
            db_col = config.COLUMN_NAMES.get(key)
            unit = sensor_spec['unit']

            if db_col not in df_raw.columns:
                print(f"   ⚠️ Spalte '{db_col}' nicht in der Datenbank gefunden. Sensor übersprungen.")
                continue

            # Glättungsperiode definieren (Pandas Resampling Rule)
            resample_rule = f'{values_period_m}T'
            
            # Resampling-Operation
            if interpolation_method == "min":
                df_resampled = df_raw[db_col].resample(resample_rule).min()
            else: 
                df_resampled = df_raw[db_col].resample(resample_rule).mean()

            # Lineare Interpolation für Datenlücken nach dem Resampling
            df_resampled = df_resampled.interpolate(method='linear')
            
            # Statistik (basiert auf den resampelten/geglätteten Daten)
            stats = {
                'sensor': db_col,
                'unit': unit,
                'min': df_resampled.min(),
                'max': df_resampled.max(),
                'mean': df_resampled.mean()
            }
            all_data.append(stats)
            
            # Füge die resampelten Daten dem Plot-DataFrame hinzu
            df_plot[db_col] = df_resampled
            
        # 4. Plot erstellen (Matplotlib)
        
        ensure_dir_exists(log_path) 
        
        fig, ax = plt.subplots(figsize=(14, 8)) 
        
        # Plotten der einzelnen Sensor-Linien
        for sensor_spec in report_config['sensors']:
            db_col = config.COLUMN_NAMES.get(sensor_spec['key'])
            unit = sensor_spec['unit']
            
            if db_col in df_plot.columns:
                ax.plot(df_plot.index, df_plot[db_col], label=f'{db_col} ({unit})', linewidth=2)
        
        # Titel und Achsenbeschriftungen
        # Ausgabe der Zeit nun als LOKALE Zeit
        ax.set_title(f"{report_config['name']}\nBerichtszeitraum (Lokal): {report_start_dt.strftime('%d.%m.%Y %H:%M')} - {report_end_dt.strftime('%d.%m.%Y %H:%M')}", fontsize=14)
        ax.set_xlabel(f"Zeit (Lokal {local_tz.zone})", fontsize=12)
        ax.set_ylabel(f"Messwert (Einheit: {report_config['sensors'][0]['unit']})", fontsize=12)

        # X-Achsen-Formatierung
        date_format = '%d.%m %H:%M'
        if duration_days > 7:
             date_format = '%d.%m.%Y'
        
        ax.xaxis.set_major_formatter(mdates.DateFormatter(date_format))
        fig.autofmt_xdate(rotation=30)
        ax.grid(True, linestyle='--', alpha=0.7)
        ax.legend(loc='best')
        
        # 5. Statistik-Tabelle in den Plot einfügen (figtext)
        stats_text = "Statistiken für den Berichtszeitraum:\n"
        for data in all_data:
            min_val = f"{data['min']:.2f}" if pd.notna(data['min']) else "N/A"
            max_val = f"{data['max']:.2f}" if pd.notna(data['max']) else "N/A"
            mean_val = f"{data['mean']:.2f}" if pd.notna(data['mean']) else "N/A"

            stats_text += f" {data['sensor']} ({data['unit']}):\n"
            stats_text += f"   - Min: {min_val}{data['unit']} \n"
            stats_text += f"   - Max: {max_val}{data['unit']} \n"
            stats_text += f"   - Mittelwert: {mean_val}{data['unit']} \n\n"

        plt.figtext(0.95, 0.5, stats_text, 
                    wrap=True, 
                    horizontalalignment='left', 
                    verticalalignment='center',
                    fontsize=10, 
                    bbox={'facecolor':'#F0F0F0', 'alpha':0.8, 'pad':5, 'edgecolor':'gray'})
        
        plt.tight_layout(rect=[0, 0, 0.88, 1]) 
        
        plt.savefig(full_file_path, format='pdf')
        plt.close(fig)

        print(f"   ✅ Bericht erfolgreich erstellt und gespeichert als: {full_file_path}")

        # 6. Archiv-Wartung
        cleanup_old_reports(log_path, report_id, report_config["max_pdfs"])


    except sqlite3.Error as e:
        print(f"   ❌ Datenbankfehler für Bericht {report_id}: {e}")
    except Exception as e:
        print(f"   ❌ Allgemeiner Fehler bei der Berichtserstellung für {report_id}: {e}")
    finally:
        if conn:
            conn.close()

# --- Hauptfunktion ---

def main():
    """Liest die Konfiguration und startet die Berichtsgenerierung."""
    
    try:
        with open(config.REPORTS_CONFIG_FILE, 'r') as f:
            reports_config_list = json.load(f)
            
    except FileNotFoundError:
        print(f"FATAL ERROR: Konfigurationsdatei {config.REPORTS_CONFIG_FILE} nicht gefunden.")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"FATAL ERROR: Fehler beim Parsen der JSON-Datei {config.REPORTS_CONFIG_FILE}: {e}")
        sys.exit(1)

    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starte Berichtsgenerator für {len(reports_config_list)} Berichte.")

    for report in reports_config_list:
        fetch_and_plot_report(report)

    print("\nAlle Berichte verarbeitet. Generator beendet.")

if __name__ == "__main__":
    main()