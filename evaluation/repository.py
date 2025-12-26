# repository.py
import os
import sqlite3
import pandas as pd
import matplotlib.pyplot as plt

from datetime import datetime
from collections import defaultdict
from pathlib import Path

from evaluation.utils import format_iso_timestamp, fmt
from evaluation.SensorStats import SensorStats
from evaluation.exceptions import ConfigError, DatabaseFileNotFound, TableNotFound, ColumnNotFound


class SensorRepository:
    def __init__(self, config, validate_schema=True):
        """
        config: SystemConfig
        validate_schema: Wenn True, wird beim Initialisieren das DB-Schema geprüft.
        """
        self.config = config

        if validate_schema:
            self._validate_schema()

    def _validate_schema(self):
        """
        Prüft:
        - DB-File existiert
        - jede konfigurierte Tabelle existiert
        - Timestamp-Spalte existiert
        - alle Sensor-Spalten existieren

        Rueckgabe:
        inactive_tables: dict[table_key, reason]
        """
        cfg = self.config  # SystemConfig

        # 1) DB-File existiert?
        if not cfg.db_file:
            raise ConfigError("DB_FILE ist in der JSON-Konfiguration nicht gesetzt.")

        if not os.path.isfile(cfg.db_file):
            raise DatabaseFileNotFound(f"DB-File existiert nicht: {cfg.db_file}")

        # 2) Tabellen definiert?
        if not cfg.tables:
            raise ConfigError("TABLE ist in der JSON-Konfiguration nicht gesetzt oder leer.")

        inactive_tables = {}

        conn = sqlite3.connect(cfg.db_file)
        try:
            cur = conn.cursor()

            for table_key, tcfg in cfg.tables.items():
                table_name = tcfg.name
                ts_field = tcfg.timestamp.name

                # 2a) Tabelle existiert?
                cur.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?;",
                    (table_name,),
                )
                if cur.fetchone() is None:
                    inactive_tables[table_key] = (
                        f"Tabelle '{table_name}' existiert nicht in DB '{cfg.db_file}'."
                    )
                    continue

                # 2b) Spalteninfos holen
                cur.execute(f"PRAGMA table_info({table_name});")
                columns_info = cur.fetchall()
                if not columns_info:
                    inactive_tables[table_key] = (
                        f"Konnte keine Spalteninfo für Tabelle '{table_name}' lesen."
                    )
                    continue

                column_names = {col[1] for col in columns_info}

                # 2c) Timestamp-Feld vorhanden?
                if ts_field not in column_names:
                    inactive_tables[table_key] = (
                        f"Timestamp-Feld '{ts_field}' fehlt in Tabelle '{table_name}'. "
                        f"Verfügbare Spalten: {sorted(column_names)}"
                    )
                    continue

                # 2d) Sensor-Felder vorhanden?
                missing = []
                for sensor_key in tcfg.sensors.keys():
                    if sensor_key not in column_names:
                        missing.append(sensor_key)

                if missing:
                    inactive_tables[table_key] = (
                        f"Sensor-Spalten fehlen in Tabelle '{table_name}': {missing}. "
                        f"Verfügbare Spalten: {sorted(column_names)}"
                    )
                    continue

        finally:
            conn.close()

        if inactive_tables:
            raise ColumnNotFound("Schema mismatch:\n" + "\n".join(f"{k}: {v}" for k,v in inactive_tables.items()))

    # ----------------- Datenabfrage -----------------
    def get_last_battery_status(self, table_key, printnow=False):
        table, sensor, df = self.get_sensor_values(table_key, "Battery_Status", start_time=None, stop_time=None, by_alias=True)
        
        if df is None:
            if printnow:
                print("Battery: keine Daten vorhanden")
            return None, None

        df["timestamp"] = pd.to_datetime(df["timestamp"])

        last_row = df.iloc[-1]
        last_val = last_row["value"]
        last_ts = last_row["timestamp"]

        if printnow:
            last_ts_str = format_iso_timestamp(last_ts, "%Y-%m-%d %H:%M")
            if last_val == 1:
                print(f"Sensor {table.sensor_id} ({table_key}) Battery: OK at {last_ts_str}")
            else:
                print(f"Sensor {table.sensor_id} ({table_key}) Battery: NOK at {last_ts_str}")

        return last_val == 1, last_ts

    def get_last_sensor_value(self, table_key, sensor_keys, printnow=False, by_alias=True):
        """
        Liest den letzten bekannten Wert eines oder mehrerer Sensoren aus der Datenbank.

        sensor_keys: Liste oder einzelner Sensor-Key
        printnow:    Wenn True, wird die Ausgabe sofort formatiert ausgegeben

        Rückgabe: dict { sensor_key: (value, timestamp, sensor_obj) }
        """

        # Einzelnen Sensor als Liste verarbeiten
        if isinstance(sensor_keys, str):
            sensor_keys = [sensor_keys]

        results = {}

        for sensor_key in sensor_keys:
            table, sensor, df = self.get_sensor_values(table_key, sensor_key, start_time=None, stop_time=None, by_alias=by_alias)

            if df.empty:
                results[sensor_key] = (None, None, sensor)
                if printnow:
                    print(f"{sensor.alias or sensor_key}: keine Daten vorhanden")
                continue

            # timestamp sicher konvertieren
            df["timestamp"] = pd.to_datetime(df["timestamp"])

            last_row = df.iloc[-1]
            last_val = last_row["value"]
            last_ts = last_row["timestamp"]
            last_ts = format_iso_timestamp(last_ts, "%Y-%m-%d %H:%M")

            results[sensor_key] = (last_val, last_ts, sensor)

            if printnow:
                # Rundung aus JSON
                decimals = sensor.round if sensor.round is not None else 2
                val_str = f"{last_val:.{decimals}f}"

                print(f"{sensor.alias or sensor.id}: {val_str} {sensor.unit} at {last_ts}")

        return results
    
    def get_table(self, table_key, by_alias=True):
        """
        Liefert das TableConfig-Objekt für den angegebenen table_key.
        """
        if by_alias:
            table = self.config.get_table_by_alias(table_key)
        else:
            table = self.config.get_table_by_key(table_key)

        if table is None:
            raise ConfigError(f"Unbekannte Tabelle: {table_key} (by_alias={by_alias})")

        return table
    
    def get_table_and_sensor(self, table_key, sensor_key, by_alias=True):
        """
        Liefert das Sensor-Objekt für den angegebenen sensor_key in der angegebenen Tabelle.
        """
        table = self.get_table(table_key, by_alias=by_alias)

        if by_alias:
            sensor = table.get_sensor_by_alias(sensor_key)
        else:
            sensor = table.get_sensor(sensor_key)

        if sensor is None:
            raise ConfigError(f"Unbekannter Sensor: {sensor_key} in Tabelle {table_key} (by_alias={by_alias})")

        return table, sensor

    def get_sensor_values(self, table_key, sensor_key, start_time=None, stop_time=None, by_alias=True):
        """
        Liefert Werte eines Sensors als DataFrame:
        Spalten: [timestamp, value]

        sensor_key : Sensor-ID (z.B. "temperature1") oder Alias ("temp1", wenn by_alias=True)
        """
        table, sensor = self.get_table_and_sensor(table_key, sensor_key, by_alias=by_alias)

        ts_col = table.timestamp.name # Timestamp-Spaltenname in der DB
        val_col = sensor.name         # Spaltenname in der DB

        query = f"""
            SELECT {ts_col} AS timestamp, {val_col} AS value
            FROM {table.name}
            WHERE 1=1
        """

        params = []

        if start_time is not None:
            start_time = self._convert_to_db_timestamp(start_time)
            query += f" AND {ts_col} >= ?"
            params.append(start_time)


        if stop_time is not None:
            stop_time = self._convert_to_db_timestamp(stop_time)
            query += f" AND {ts_col} <= ?"
            params.append(stop_time)


        query += f" ORDER BY {ts_col} ASC;"

        conn = sqlite3.connect(self.config.db_file)
        try:
            df = pd.read_sql_query(query, conn, params=params)
        finally:
            conn.close()

        return table, sensor, df

    def get_sensor_values_describe(self, sensor_key, start_time=None, stop_time=None, printnow=False):
        """
        Liefert beschreibende Statistik (describe) eines Sensors als DataFrame.

        sensor_key : Sensor-ID (z.B. "temperature1") oder Alias ("temp1", wenn by_alias=True)
        """
        sensor, df = self.get_sensor_values(sensor_key, start_time, stop_time)
        
        min_row = df.loc[df["value"].idxmin()]
        max_row = df.loc[df["value"].idxmax()]

        sSt = SensorStats(
            sensor=sensor,
            df=df,
            first_val=df['value'].iloc[0],
            first_timestamp=df['timestamp'].iloc[0],
            last_val=df['value'].iloc[-1],
            last_timestamp=df['timestamp'].iloc[-1],
            min_val=min_row['value'],
            min_timestamp=min_row['timestamp'],
            max_val=max_row['value'],
            max_timestamp=max_row['timestamp'],
            mean_value=df["value"].mean())
        
        if printnow:
            print(f"Sensor: {sensor.alias} ({sensor.id})")
            #print(f"From {first_timestamp} to {last_timestamp}")
            print(f"First Value: {sSt.first_val} {sensor.unit} at {sSt.formatted_first_timestamp()}")
            print(f"Last Value: {sSt.last_val} {sensor.unit} at {sSt.formatted_last_timestamp()}")
            print(f"Mean: {sSt.mean_value:.2f} {sensor.unit}")
            print(f"Max: {sSt.max_val} {sensor.unit} at {sSt.formatted_max_timestamp()}")
            print(f"Min: {sSt.min_val} {sensor.unit} at {sSt.formatted_min_timestamp()}")
        return sSt

    def plot_sensor_values(self, table_key, sensor_key, start_time=None, stop_time=None,
                       title=None, filename=None, show=False, by_alias=True):
        """
        Plottet die Werte eines Sensors, inklusive:
        - Sensorfarbe aus JSON
        - Min/Max/Mean Beschriftung
        - Warn- und Alarmbereiche
        """

        # Sensor & Werte laden
        table, sensor, df = self.get_sensor_values(table_key, sensor_key, start_time, stop_time, by_alias=by_alias)

        if df.empty:
            print("⚠️ Keine Daten zum Plotten vorhanden!")
            return

        # timestamp sicher in datetime umwandeln
        df["timestamp"] = pd.to_datetime(df["timestamp"])

        # Statistik berechnen
        min_row = df.loc[df["value"].idxmin()]
        max_row = df.loc[df["value"].idxmax()]
        mean_value = df["value"].mean()

        # Plot Farbe aus JSON (fallback: blue)
        color = sensor.color
        if color is None:
            print("⚠️ Keine Plot-Farbe im Sensor definiert, verwende Standardfarbe 'blue'.")
            color = "blue"

        # Diagramm erstellen
        plt.figure(figsize=(11, 6))
        plt.plot(df["timestamp"], df["value"], linestyle="-", color=color, label="Messwerte")

        # Warn- & Alarmbereiche einzeichnen (horizontal)
        if sensor.warn != (None, None):
            if sensor.alarm != (None, None):
                plt.axhspan(sensor.warn[0], sensor.alarm[0], color="yellow", alpha=0.2, label="Warnbereich")
                plt.axhspan(sensor.warn[1], sensor.alarm[1], color="yellow", alpha=0.2)

        if sensor.alarm != (None, None):
            plt.axhspan(sensor.alarm[0]-10, sensor.alarm[0], color="red", alpha=0.15, label="Alarmbereich")
            plt.axhspan(sensor.alarm[1], sensor.alarm[1]+10, color="red", alpha=0.15)

        # Einzelne Punkte hervorheben
        plt.scatter(min_row["timestamp"], min_row["value"], color="blue", s=80, label="Minimum")
        plt.scatter(max_row["timestamp"], max_row["value"], color="red", s=80, label="Maximum")

        # Titel mit Werten
        if title is None:
            title = f"{sensor.alias} ({sensor.key})\n"
        
        plt.title(
            f"{title} \n"
            f"min={min_row['value']:.2f} | mean={mean_value:.2f} | max={max_row['value']:.2f} {sensor.unit}"
        )

        plt.xlabel("Zeit")
        plt.ylabel(f"Wert [{sensor.unit}]")
        plt.grid(True)

        # x-Ticks sauber formatieren
        plt.xticks(rotation=30)
        plt.tight_layout()

        # Legende anzeigen
        plt.legend()

        # Speichern?
        if filename:
            plt.savefig(filename, transparent=True)
            print(f"📁 Plot gespeichert unter: {filename}")

        if show:
            plt.show()

        plt.close()
       
    def multiplot_sensor_values(self, table_key, sensor_keys, start_time=None, stop_time=None,
                            filename=None, title=None, show=False, by_alias=True):
        """
        Plottet mehrere Sensoren.
        
        - Sensoren mit gleicher Einheit werden im gleichen Subplot dargestellt.
        - Unterschiedliche Einheiten -> eigene Subplots untereinander.
        - Keine Warn-/Alarmbereiche, nur Kurven.
        """

        # Sensoren nach Einheit gruppieren: {unit: [(sensor, df), ...], ...}
        grouped = defaultdict(list)

        for sensor_key in sensor_keys:
            table, sensor, df = self.get_sensor_values(table_key, sensor_key, start_time, stop_time, by_alias=by_alias)

            if df.empty:
                print(f"⚠️ Keine Daten für Sensor '{sensor_key}' – wird übersprungen.")
                continue

            # Timestamps in datetime wandeln
            df["timestamp"] = pd.to_datetime(df["timestamp"])

            unit = sensor.unit or ""
            grouped[unit].append((sensor, df))

        if not grouped:
            print("⚠️ Keine Daten zum Plotten gefunden.")
            return

        n_units = len(grouped)
        fig, axes = plt.subplots(n_units, 1, sharex=True, figsize=(11, 3 * n_units))

        if n_units == 1:
            axes = [axes]

        # stabile Reihenfolge
        units_order = list(grouped.keys())

        for ax, unit in zip(axes, units_order):
            entries = grouped[unit]

            for sensor, df in entries:
                color = sensor.color if hasattr(sensor, "plot") else None
                if by_alias:
                    label = f"{sensor.alias}"
                else:
                    label = f"{sensor.name}"

                ax.plot(df["timestamp"], df["value"],
                        linestyle="-",
                        label=label,
                        color=color)

            # Achsenbeschriftungen
            if title is None:
                title = "Sensor"
            if unit:
                ax.set_ylabel(f"[{unit}]")
                ax.set_title(f"{title} ({unit})")
            else:
                ax.set_ylabel("Value")
                ax.set_title(f"{title} (unitless)")

            ax.grid(True)
            ax.legend(loc="best")

        axes[-1].set_xlabel("Zeit")
        plt.xticks(rotation=30)
        plt.tight_layout()

        if filename:
            path = Path(filename)
            path.parent.mkdir(parents=True, exist_ok=True)
            plt.savefig(path, transparent=True)
            print(f"📁 Multiplot gespeichert unter: {path}")

        if show:
            plt.show()

        plt.close(fig)

    def multiplot_sensor_values_describe(self, table_key, sensor_keys, start_time=None, stop_time=None, filename=None, title=None, show=False, by_alias=True):
        """
        Erzeugt eine Tabelle mit Statistikwerten für mehrere Sensoren und speichert sie als Bild.

        Spalten:
        Sensor, First Value, Last Value, Mean, Min, Max
        """

        rows = []

        for sensor_key in sensor_keys:
            table, sensor, df = self.get_sensor_values(table_key, sensor_key, start_time, stop_time, by_alias=by_alias)

            if df.empty:
                print(f"⚠️ Keine Daten für Sensor '{sensor_key}' - wird in Tabelle übersprungen.")
                continue

            # Sicherstellen, dass sortiert ist (falls nicht schon)
            df = df.sort_values("timestamp").reset_index(drop=True)

            

            # First / Last
            first_val = df["value"].iloc[0]
            last_val = df["value"].iloc[-1]
            # Min / Max / Mean
            min_val = df["value"].min()
            max_val = df["value"].max()
            mean_val = df["value"].mean()

            sensor_name = sensor.alias or sensor.id

            

            rows.append([
                sensor_name,
                fmt(first_val, sensor),
                fmt(last_val, sensor),
                fmt(mean_val, sensor),
                fmt(min_val, sensor),
                fmt(max_val, sensor),
            ])

        if not rows:
            print("⚠️ Keine Daten für irgendeinen Sensor gefunden – keine Tabelle erzeugt.")
            return

        col_labels = ["Sensor", "First Value", "Last Value", "Mean", "Min", "Max"]

        # --- Tabelle als Bild zeichnen ---
        n_rows = len(rows)
        fig_height = 1.2 + 0.4 * n_rows  # dynamische Höhe abhängig von Anzahl Zeilen
        fig, ax = plt.subplots(figsize=(10, fig_height))
        ax.axis("off")
        
        table = ax.table(
            cellText=rows,
            colLabels=col_labels,
            cellLoc="center",
            loc="center"
        )

        table.auto_set_font_size(False)
        table.set_fontsize(9)
        table.scale(1, 1.4)  # etwas höher machen

        if title is None:
            title = "Sensor Statistics"
        ax.set_title(title, pad=5)

        plt.tight_layout()

        # Speichern
        if filename:
            path = Path(filename)
            path.parent.mkdir(parents=True, exist_ok=True)
            plt.savefig(path, bbox_inches="tight", dpi=150)
            print(f"📁 Tabelle gespeichert unter: {path}")

        if show:
            plt.show()

        plt.close(fig)

    def multiplot_last_sensor_values(self, table_key, sensor_keys, filename=None, title=None, show=False):
        """
        Erstellt eine Tabelle als Bild mit dem letzten Wert mehrerer Sensoren.

        Spalten:
        Sensor | Last Value | Time | Status (normal / warning / alarm)

        Status-Logik:
        - alarm:  value < alarm_low  oder value > alarm_high
        - warning: value < warn_low oder value > warn_high (sofern nicht schon alarm)
        - normal: sonst
        """

        # Einzelstring -> Liste
        if isinstance(sensor_keys, str):
            sensor_keys = [sensor_keys]

        # nutzt deine bereits existierende Funktion
        last_values = self.get_last_sensor_value(table_key, sensor_keys, printnow=False)

        rows = []
        statuses = []

        for key, (last_val, last_ts, sensor) in last_values.items():
            name = sensor.alias or sensor.id
            unit = sensor.unit or ""

            if last_val is None:
                value_str = "-"
                time_str = "-"
                status = "no data"
            else:
                # Rundung aus JSON
                decimals = getattr(sensor, "round", None)
                if decimals is None:
                    decimals = 2

                value_str = f"{last_val:.{decimals}f}{(' ' + unit) if unit else ''}"

                # Zeit formatieren – falls du format_iso_timestamp hast:
                try:
                    from utils import format_iso_timestamp  # oder deinen Pfad
                    time_str = format_iso_timestamp(last_ts, "%Y-%m-%d %H:%M")
                except Exception:
                    time_str = str(last_ts)

                # Status bestimmen
                status = "normal"
                warn_low, warn_high = sensor.warn
                alarm_low, alarm_high = sensor.alarm

                if alarm_low is not None and alarm_high is not None:
                    if last_val < alarm_low:
                        status = "alarm (to low)"
                    elif last_val > alarm_high:
                        status = "alarm (to high)"
                    elif warn_low is not None and warn_high is not None:
                        if last_val < warn_low:
                            status = "warning (to low)"
                        elif last_val > warn_high:
                            status = "warning (to high)"    
                elif warn_low is not None and warn_high is not None:
                    if last_val < warn_low:
                        status = "warning (to low)"
                    elif last_val > warn_high:
                        status = "warning (to high)"    
                else:
                    status = ""

            rows.append([name, value_str, time_str, status])
            statuses.append(status)

        if not rows:
            print("⚠️ Keine Daten für die angegebenen Sensoren.")
            return

        col_labels = ["Sensor", "Last Value", "Time", "Status"]

        # --- Tabelle als Bild zeichnen ---
        n_rows = len(rows)
        fig_height = 1.2 + 0.4 * n_rows
        fig, ax = plt.subplots(figsize=(10, fig_height))
        ax.axis("off")

        table = ax.table(
            cellText=rows,
            colLabels=col_labels,
            cellLoc="center",
            loc="center"
        )

        table.auto_set_font_size(False)
        table.set_fontsize(9)
        table.scale(1, 1.4)

        if title is None:
            title = "Last sensor values"
        ax.set_title(title, pad=0)

        # Status-Spalte einfärben
        status_col_idx = col_labels.index("Status")
        for row_idx, status in enumerate(statuses, start=1):  # row 0 = Header
            cell = table[row_idx, status_col_idx]
            if status == "alarm (to low)" or status == "alarm (to high)":
                cell.set_facecolor("lightcoral")
            elif status == "warning (to low)" or status == "warning (to high)":
                cell.set_facecolor("khaki")
            elif status == "normal":
                cell.set_facecolor("lightgreen")
            else:  # "no data" o.ä.
                cell.set_facecolor("lightgray")

        plt.tight_layout()

        if filename:
            path = Path(filename)
            path.parent.mkdir(parents=True, exist_ok=True)
            plt.savefig(path, bbox_inches="tight", dpi=150)
            print(f"📁 Status-Tabelle gespeichert unter: {path}")

        if show:
            plt.show()

        plt.close(fig)

    def get_latest_timestamp(self, table_key, by_alias=True):
        """Gibt das jüngste Timestamp-Feld aus der Datenbank zurück, oder None wenn DB leer."""
        # Table holen
        table = self.config.get_table_by_key(table_key) if not by_alias else self.config.get_table_by_alias(table_key)
        if table is None:
            raise ConfigError(f"Unbekannte Tabelle: {table_key} (by_alias={by_alias})")

        ts_col = table.timestamp.name # Timestamp-Spaltenname in der DB
        query = f"""
            SELECT MAX({ts_col}) AS ts
            FROM {table.name}
        """

        conn = sqlite3.connect(self.config.db_file)
        try:
            cur = conn.cursor()
            cur.execute(query)
            row = cur.fetchone()
        finally:
            conn.close()

        return row[0] if row and row[0] is not None else None

    def get_first_timestamp(self, table_key, by_alias=True):
        """Gibt das älteste Timestamp-Feld aus der Datenbank zurück, oder None wenn DB leer."""
        # Table holen
        table = self.config.get_table_by_key(table_key) if not by_alias else self.config.get_table_by_alias(table_key)
        if table is None:
            raise ConfigError(f"Unbekannte Tabelle: {table_key} (by_alias={by_alias})")

        ts_col = table.timestamp.name # Timestamp-Spaltenname in der DB
        query = f"""
            SELECT MIN({ts_col}) AS ts
            FROM {table.name}
        """

        conn = sqlite3.connect(self.config.db_file)
        try:
            cur = conn.cursor()
            cur.execute(query)
            row = cur.fetchone()
        finally:
            conn.close()

        return row[0] if row and row[0] is not None else None
    
    def _convert_to_db_timestamp(self, ts):
        """
        Wandelt verschiedene Datumsformate ins DB-kompatible ISO8601 'Z'-Format.
        Erlaubt:
        - String  (ISO, mit oder ohne 'Z')
        - datetime.datetime
        - pandas.Timestamp
        """
        if ts is None:
            return None

        # Fall 1: pandas Timestamp
        if isinstance(ts, pd.Timestamp):
            dt = ts.to_pydatetime()
            return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")

        # Fall 2: datetime.datetime
        if isinstance(ts, datetime):
            return ts.strftime("%Y-%m-%dT%H:%M:%S.000Z")

        # Fall 3: String
        if isinstance(ts, str):

            # Wenn schon im Ziel-Format
            if ts.endswith("Z"):
                return ts

            # Millisekunden + ohne Z akzeptieren
            try:
                dt = datetime.fromisoformat(ts)
            except ValueError:
                raise ValueError(f"Ungültiges Zeitformat: {ts}")

            return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")

        # Unbekannter Typ
        raise TypeError(f"Kann Timestamp nicht konvertieren: {ts} ({type(ts)})")

    def _convert_to_db_timestamp_old(self, ts):
        """
        Wandelt verschiedene Datumsformate ins DB-kompatible Format:
        Storage-Format: ISO8601 mit 'Z'
        """
        if ts is None:
            return None

        # wenn schon korrekt:
        if ts.endswith("Z"):
            return ts

        # Beispiel: "2025-12-05 18:00:00"
        try:
            dt = datetime.fromisoformat(ts)
        except ValueError:
            raise ValueError(
                f"Ungültiges Zeitformat: '{ts}' — erwartet ISO-8601 wie 'YYYY-MM-DD HH:MM:SS'"
            )

        # in korrektes DB-Format wandeln
        return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")