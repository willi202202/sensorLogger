#!/usr/bin/env python3
# plot_data.py
#
# Beispiel:
#   python3 plot_data.py temp_in temp1 --start "2025-12-03 18:00:00"

import os
import sys
import sqlite3
import datetime
import argparse

import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.dates import DateFormatter, MinuteLocator, HourLocator

import config


def create_multi_plot(sensor_keys, start_time_str=None, end_time_str=None):
    """
    Erstellt einen Graphen für die angegebenen Sensoren über den definierten Zeitraum
    und speichert ihn als PDF.

    Args:
        sensor_keys (list): Liste der Aliasnamen (z.B. ['temp_in', 'temp1']).
        start_time_str (str): Startdatum/-zeit im Format YYYY-MM-DD HH:MM:SS (UTC).
        end_time_str (str): Enddatum/-zeit im Format YYYY-MM-DD HH:MM:SS (UTC).
    """

    # --- 1. Überprüfung der Sensor-Alias-Keys ---
    valid_keys = []
    db_column_names = []

    for key in sensor_keys:
        if key in config.SENSOR_ALIASES:
            valid_keys.append(key)
            db_column_names.append(config.SENSOR_ALIASES[key])
        else:
            print(f"❌ Fehler: Sensor-Alias '{key}' ist in config.SENSOR_ALIASES nicht definiert und wird ignoriert.")

    if not valid_keys:
        print("❌ Keine gültigen Sensoren zum Plotten übrig.")
        return

    # Zeitspalte (DB-Spaltenname, z.B. 'utms')
    time_column_name = config.TIMESTAMP_FIELD

    conn = None
    try:
        conn = sqlite3.connect(config.DB_FILE)

        # --- 2. SQL-Abfrage erstellen ---
        select_columns = [time_column_name] + db_column_names
        select_columns_str = ", ".join(select_columns)

        sql_query = f"""
            SELECT {select_columns_str}
            FROM {config.TABLE_NAME}
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
        # Zeitspalte in datetime konvertieren
        df[time_column_name] = pd.to_datetime(df[time_column_name], errors='coerce')
        df.dropna(subset=[time_column_name], inplace=True)

        # Zeilen entfernen, wo alle Sensorwerte NULL sind
        df.dropna(subset=db_column_names, how='all', inplace=True)

        if df.empty:
            print("ℹ️ Keine verwertbaren Daten für die gewählten Sensoren und Zeitraum gefunden.")
            return

        # --- 4. Plot erstellen ---

        sensor_list_str = "_".join(valid_keys)
        timestamp_str = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        output_filename = f"plot_{sensor_list_str}_{timestamp_str}.pdf"
        output_path = os.path.join(config.REPORTS_PATH, output_filename)

        fig, ax = plt.subplots(figsize=(12, 6))

        # aus valid_keys die DB-Spalten bestimmen
        db_cols = [config.SENSOR_ALIASES[k] for k in valid_keys]

        # Einheit pro Spalte aus config.UNIT_MAP bestimmen
        def col_unit(col_name):
            return config.UNIT_MAP.get(col_name, "Wert")

        # prüfen, ob es Temperatur- und Feuchtewerte gibt
        has_temp = any(col_unit(c) == "°C" for c in db_cols)
        has_hum = any(col_unit(c) == "%RH" for c in db_cols)

        # zweite Y-Achse, falls nötig
        ax2 = None
        if has_temp and has_hum:
            ax2 = ax.twinx()

        # Listen zum Sammeln der Spalten pro Achse (für Limits)
        left_axis_cols = []
        right_axis_cols = []

        # Linien plotten
        for key in valid_keys:
            col = config.SENSOR_ALIASES[key]
            unit = col_unit(col)

            # Achse auswählen
            target_ax = ax
            if unit == "%RH" and ax2 is not None:
                target_ax = ax2

            target_ax.plot(
                df[time_column_name],
                df[col],
                label=f'{key} [{col}]',
                linewidth=2
            )

            # für Limits merken
            if target_ax is ax:
                left_axis_cols.append(col)
            else:
                right_axis_cols.append(col)

        # Titel
        t_min = df[time_column_name].min()
        t_max = df[time_column_name].max()
        plot_title = ", ".join(valid_keys)
        ax.set_title(f"Verlauf von: {plot_title}\nVon {t_min} bis {t_max}", fontsize=14)
        ax.set_xlabel("Zeit (UTC)")

        # Y-Achsen-Beschriftungen
        if has_temp and has_hum:
            ax.set_ylabel("Temperatur (°C)")
            ax2.set_ylabel("Feuchte (%RH)")
        elif has_temp:
            ax.set_ylabel("Temperatur (°C)")
        elif has_hum:
            ax.set_ylabel("Feuchte (%RH)")
        else:
            # irgendeine andere Einheit (z.B. battery)
            if db_cols:
                ax.set_ylabel(f"Messwert ({col_unit(db_cols[0])})")
            else:
                ax.set_ylabel("Messwert")

        # Y-Limits aus SENSOR_LIMITS ableiten (optional)
        def compute_limits(cols):
            mins = []
            maxs = []
            for c in cols:
                if c in config.SENSOR_LIMITS:
                    mn, mx = config.SENSOR_LIMITS[c]
                    mins.append(mn)
                    maxs.append(mx)
            if mins and maxs:
                return min(mins), max(maxs)
            return None

        left_limits = compute_limits(left_axis_cols)
        right_limits = compute_limits(right_axis_cols)

        if left_limits is not None:
            ax.set_ylim(*left_limits)
        if ax2 is not None and right_limits is not None:
            ax2.set_ylim(*right_limits)

        # X-Achsen-Formatierung
        time_diff = df[time_column_name].max() - df[time_column_name].min()
        if time_diff.total_seconds() < 3600 * 5:      # < 5 h
            ax.xaxis.set_major_formatter(DateFormatter('%H:%M'))
            ax.xaxis.set_major_locator(MinuteLocator(interval=15))
        elif time_diff.total_seconds() < 3600 * 48:   # < 2 Tage
            ax.xaxis.set_major_formatter(DateFormatter('%H:%M\n%d.%m.'))
            ax.xaxis.set_major_locator(HourLocator(interval=6))
        else:
            ax.xaxis.set_major_formatter(DateFormatter('%Y-%m-%d'))

        fig.autofmt_xdate(rotation=45)
        ax.grid(True, linestyle='--', alpha=0.7)

        # Legende aus beiden Achsen zusammensetzen (falls es zwei gibt)
        handles1, labels1 = ax.get_legend_handles_labels()
        if ax2 is not None:
            handles2, labels2 = ax2.get_legend_handles_labels()
            handles = handles1 + handles2
            labels = labels1 + labels2
        else:
            handles, labels = handles1, labels1

        ax.legend(handles, labels, loc='best')

        # Layout anpassen und PDF speichern
        os.makedirs(config.REPORTS_PATH, exist_ok=True)
        plt.tight_layout()
        plt.savefig(output_path, format='pdf')
        plt.close(fig)

        print(f"\n✅ Graph erfolgreich erstellt und gespeichert unter:\n{output_path}")

    except sqlite3.Error as e:
        print(f"❌ Datenbankfehler: {e}")
    except Exception as e:
        print(f"❌ Allgemeiner Fehler beim Plotten: {e}")
    finally:
        if conn:
            conn.close()


def main():
    """Definiert die Kommandozeilen-Argumente und ruft die Plot-Funktion auf."""

    parser = argparse.ArgumentParser(
        description="Erstellt einen Zeitverlaufsgraphen der Sensordaten als PDF.",
        formatter_class=argparse.RawTextHelpFormatter
    )

    available_keys = list(config.SENSOR_ALIASES.keys())
    keys_str = ", ".join(available_keys)

    parser.add_argument(
        "sensor_key",
        nargs='+',  # ein oder mehrere Aliase
        choices=available_keys,
        help=f"Ein oder mehrere Alias-Namen der Sensoren, die geplottet werden sollen.\nAuswahl: {keys_str}"
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

    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()
    create_multi_plot(args.sensor_key, args.start, args.end)


if __name__ == "__main__":
    main()
