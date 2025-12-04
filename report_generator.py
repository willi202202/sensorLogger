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

# Unterdrückt Matplotlib-Warnungen, die manchmal im figtext-Bereich auftreten
warnings.filterwarnings("ignore", category=UserWarning)

# Importiere Konfiguration aus der config.py
import config

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

    # 1. Zeitfenster definieren (Bericht endet heute um Mitternacht UTC)
    
    # Enddatum ist heute 00:00:00 UTC (der Zeitpunkt des Skriptstarts)
    report_end_dt = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    # Startdatum ist Enddatum minus Dauer
    report_start_dt = report_end_dt - timedelta(days=duration_days)
    
    start_time_str = report_start_dt.strftime('%Y-%m-%d %H:%M:%S')
    end_time_str = report_end_dt.strftime('%Y-%m-%d %H:%M:%S')

    # Filename basiert auf dem ENDDATUM des Berichts
    report_date_str = (report_end_dt - timedelta(seconds=1)).strftime('%Y-%m-%d')
    file_name = f"{report_id}_{report_date_str}.pdf"
    full_file_path = os.path.join(log_path, file_name)

    # 2. Existenzprüfung
    # Verhindert Duplikate für einen spezifischen Endzeitpunkt. Bei rollierenden
    # Berichten wird die Datei täglich mit neuem Enddatum überschrieben/ersetzt.
    if os.path.exists(full_file_path):
        print(f"   ⚠️ Bericht für {report_date_str} existiert bereits. Überspringe Generierung.")
        # Führt trotzdem die Archiv-Wartung durch, falls max_pdfs überschritten wurde
        cleanup_old_reports(log_path, report_id, report_config["max_pdfs"])
        return

    print(f"   -> Datenzeitraum: {start_time_str} bis {end_time_str} (UTC)")
    
    # 3. Datenbankabfrage und Glättung
    
    conn = None
    all_data = [] # Zum Speichern der Statistikdaten
    
    try:
        conn = sqlite3.connect(config.DB_FILE)
        
        # Liste der DB-Spaltennamen für die Abfrage
        db_cols_to_query = [config.COLUMN_NAMES.get(s['key']) for s in report_config['sensors']]
        # Entferne None-Werte, falls ein Key in reports.json, aber nicht in config.py existiert
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
        
        if df_raw.empty:
            print("   ℹ️ Keine Daten für diesen Zeitraum gefunden.")
            return

        # Zeitstempel konvertieren und als Index setzen
        df_raw[time_col] = pd.to_datetime(df_raw[time_col], utc=True)
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
                # Resampling auf Minimum
                df_resampled = df_raw[db_col].resample(resample_rule).min()
            else: # Standard oder "mean"
                # Resampling auf Mittelwert
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
        
        ensure_dir_exists(log_path) # Stellt sicher, dass der Zielordner existiert
        
        # Größere Figur, um Platz für die Statistik rechts zu schaffen
        fig, ax = plt.subplots(figsize=(14, 8)) 
        
        # Plotten der einzelnen Sensor-Linien
        for sensor_spec in report_config['sensors']:
            db_col = config.COLUMN_NAMES.get(sensor_spec['key'])
            unit = sensor_spec['unit']
            
            # Nur plotten, wenn die Spalte im df_plot existiert
            if db_col in df_plot.columns:
                ax.plot(df_plot.index, df_plot[db_col], label=f'{db_col} ({unit})', linewidth=2)
        
        # Titel und Achsenbeschriftungen
        ax.set_title(f"{report_config['name']}\nBerichtszeitraum: {report_start_dt.strftime('%d.%m.%Y %H:%M')} - {report_end_dt.strftime('%d.%m.%Y %H:%M')} UTC", fontsize=14)
        ax.set_xlabel("Zeit (UTC)", fontsize=12)
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
            # Sicherheitsprüfung, falls min/max/mean None sind (was bei leeren Daten passieren kann)
            min_val = f"{data['min']:.2f}" if pd.notna(data['min']) else "N/A"
            max_val = f"{data['max']:.2f}" if pd.notna(data['max']) else "N/A"
            mean_val = f"{data['mean']:.2f}" if pd.notna(data['mean']) else "N/A"

            stats_text += f" {data['sensor']} ({data['unit']}):\n"
            stats_text += f"   - Min: {min_val}{data['unit']} \n"
            stats_text += f"   - Max: {max_val}{data['unit']} \n"
            stats_text += f"   - Mittelwert: {mean_val}{data['unit']} \n\n"

        # Füge den Text rechts in die Abbildung ein (Position x=0.95, y=0.5)
        plt.figtext(0.95, 0.5, stats_text, 
                    wrap=True, 
                    horizontalalignment='left', 
                    verticalalignment='center',
                    fontsize=10, 
                    bbox={'facecolor':'#F0F0F0', 'alpha':0.8, 'pad':5, 'edgecolor':'gray'})
        
        # Layout anpassen (passt den Graphen an, um Platz für den Text zu schaffen)
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