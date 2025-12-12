# repository.py
import os
import sqlite3
import pandas as pd
from datetime import datetime
import matplotlib.pyplot as plt
from collections import defaultdict
from pathlib import Path
from SensorStats import SensorStats
from utils import format_iso_timestamp, fmt

from errors import ConfigError, DatabaseFileNotFound, TableNotFound, ColumnNotFound


class SensorRepository:
    def __init__(self, config, validate_schema=True):
        """
        config: SystemConfig
        validate_schema: Wenn True, wird beim Initialisieren das DB-Schema geprüft.
        """
        self.config = config

        if validate_schema:
            self._validate_schema()

    # ----------------- Schema-Validierung -----------------

    def _validate_schema(self):
        """Prüft DB-File, Tabelle, Timestamp-Feld und Sensor-Felder."""

        # 1) DB-File existiert?
        if not self.config.db_file:
            raise ConfigError("DB_FILE ist in der JSON-Konfiguration nicht gesetzt.")

        if not os.path.isfile(self.config.db_file):
            raise DatabaseFileNotFound(f"DB-File existiert nicht: {self.config.db_file}")

        # Verbindung öffnen
        conn = sqlite3.connect(self.config.db_file)
        try:
            cur = conn.cursor()

            # 2) Tabelle existiert?
            if not self.config.table_name:
                raise ConfigError("TABLE_NAME ist in der JSON-Konfiguration nicht gesetzt.")

            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?;",
                (self.config.table_name,),
            )
            row = cur.fetchone()
            if row is None:
                raise TableNotFound(
                    f"Tabelle '{self.config.table_name}' existiert nicht in DB '{self.config.db_file}'."
                )

            # 3) Spalteninformationen holen
            cur.execute(f"PRAGMA table_info({self.config.table_name});")
            columns_info = cur.fetchall()
            if not columns_info:
                raise ConfigError(
                    f"Konnte keine Spalteninfo für Tabelle '{self.config.table_name}' lesen."
                )

            # Column-Namen extrahieren
            column_names = {col[1] for col in columns_info}  # col[1] = name

            # 4) Timestamp-Feld vorhanden?
            if not self.config.timestamp_field:
                raise ConfigError("TIMESTAMP_FIELD ist in der JSON-Konfiguration nicht gesetzt.")

            if self.config.timestamp_field not in column_names:
                raise ColumnNotFound(
                    f"TIMESTAMP_FIELD '{self.config.timestamp_field}' existiert nicht in Tabelle "
                    f"'{self.config.table_name}'. Verfügbare Spalten: {sorted(column_names)}"
                )

            # 5) Alle Sensor-Felder vorhanden?
            missing_sensors = []
            for sensor in self.config.sensors.values():
                #print("Prüfe Sensor-Spalte:", sensor.id)
                col = sensor.id  # Annahme: Spaltenname = sensor.id z.B. "temperature1"
                if col not in column_names:
                    missing_sensors.append(col)

            if missing_sensors:
                raise ColumnNotFound(
                    "Folgende Sensor-Spalten fehlen in der Tabelle "
                    f"'{self.config.table_name}': {missing_sensors}. "
                    f"Verfügbare Spalten: {sorted(column_names)}"
                )

        finally:
            conn.close()

    # ----------------- Datenabfrage -----------------
    def get_last_battery_status(self, printnow=False):
        sensor, df = self.get_sensor_values("battery", start_time=None, stop_time=None)
        
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
                print(f"Battery: OK at {last_ts_str}")
            else:
                print(f"Battery: NOK at {last_ts_str}")

        return last_val == 1, last_ts


    def get_last_sensor_value(self, sensor_keys, printnow=False):
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

        for key in sensor_keys:
            sensor, df = self.get_sensor_values(key, start_time=None, stop_time=None)

            if df.empty:
                results[key] = (None, None, sensor)
                if printnow:
                    print(f"{sensor.alias or key}: keine Daten vorhanden")
                continue

            # timestamp sicher konvertieren
            df["timestamp"] = pd.to_datetime(df["timestamp"])

            last_row = df.iloc[-1]
            last_val = last_row["value"]
            last_ts = last_row["timestamp"]
            last_ts = format_iso_timestamp(last_ts, "%Y-%m-%d %H:%M")

            results[key] = (last_val, last_ts, sensor)

            if printnow:
                # Rundung aus JSON
                decimals = sensor.round if sensor.round is not None else 2
                val_str = f"{last_val:.{decimals}f}"

                print(f"{sensor.alias or sensor.id}: {val_str} {sensor.unit} at {last_ts}")

        return results

    def get_sensor_values(self, sensor_key, start_time=None, stop_time=None):
        """
        Liefert Werte eines Sensors als DataFrame:
        Spalten: [timestamp, value]

        sensor_key : Sensor-ID (z.B. "temperature1") oder Alias ("temp1", wenn by_alias=True)
        """
        # Sensorobjekt holen
        sensor = self.config.get_sensor_by_alias(sensor_key)
        if sensor is None:
            sensor = self.config.get_sensor(sensor_key)
            if sensor is None:
                raise ConfigError(f"Unbekannter Sensor: {sensor_key} (by_alias={by_alias})")

        ts_col = self.config.timestamp_field
        val_col = sensor.id  # Spaltenname in der DB

        query = f"""
            SELECT {ts_col} AS timestamp, {val_col} AS value
            FROM {self.config.table_name}
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

        return sensor, df

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

    def plot_sensor_values(self, sensor_key, start_time=None, stop_time=None,
                       filename=None, show=False):
        """
        Plottet die Werte eines Sensors, inklusive:
        - Sensorfarbe aus JSON
        - Min/Max/Mean Beschriftung
        - Warn- und Alarmbereiche
        """

        # Sensor & Werte laden
        sensor, df = self.get_sensor_values(sensor_key, start_time, stop_time)

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
        color = sensor.plot.get("color", "tab:blue")

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
        plt.title(
            f"{sensor.alias} ({sensor.id})\n"
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
       
    def multiplot_sensor_values(self, sensor_keys, start_time=None, stop_time=None,
                            filename=None, show=False):
        """
        Plottet mehrere Sensoren.
        
        - Sensoren mit gleicher Einheit werden im gleichen Subplot dargestellt.
        - Unterschiedliche Einheiten -> eigene Subplots untereinander.
        - Keine Warn-/Alarmbereiche, nur Kurven.
        """

        # Sensoren nach Einheit gruppieren: {unit: [(sensor, df), ...], ...}
        grouped = defaultdict(list)

        for key in sensor_keys:
            sensor, df = self.get_sensor_values(key, start_time, stop_time)

            if df.empty:
                print(f"⚠️ Keine Daten für Sensor '{key}' – wird übersprungen.")
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
                color = sensor.plot.get("color") if hasattr(sensor, "plot") else None
                label = f"{sensor.alias} ({sensor.id})"

                ax.plot(df["timestamp"], df["value"],
                        linestyle="-",
                        label=label,
                        color=color)

            # Achsenbeschriftungen
            if unit:
                ax.set_ylabel(f"[{unit}]")
                ax.set_title(f"Sensors ({unit})")
            else:
                ax.set_ylabel("Wert")
                ax.set_title("Sensors (unitless)")

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

    def multiplot_sensor_values_describe(self, sensor_keys, start_time=None, stop_time=None, filename=None, show=False):
        """
        Erzeugt eine Tabelle mit Statistikwerten für mehrere Sensoren und speichert sie als Bild.

        Spalten:
        Sensor, First Value, Last Value, Mean, Min, Max
        """

        rows = []

        for key in sensor_keys:
            sensor, df = self.get_sensor_values(key, start_time, stop_time)

            if df.empty:
                print(f"⚠️ Keine Daten für Sensor '{key}' - wird in Tabelle übersprungen.")
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

        ax.set_title("Sensor Statistics", pad=10)

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

    def multiplot_last_sensor_values(self, sensor_keys, filename=None, show=False):
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
        last_values = self.get_last_sensor_value(sensor_keys, printnow=False)

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

        ax.set_title("Last Sensor Values", pad=10)

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

    def get_latest_timestamp(self):
        """Gibt das jüngste Timestamp-Feld aus der Datenbank zurück, oder None wenn DB leer."""
        ts_col = self.config.timestamp_field
        query = f"""
            SELECT MAX({ts_col}) AS ts
            FROM {self.config.table_name}
        """

        conn = sqlite3.connect(self.config.db_file)
        try:
            cur = conn.cursor()
            cur.execute(query)
            row = cur.fetchone()
        finally:
            conn.close()

        return row[0] if row and row[0] is not None else None

    def get_first_timestamp(self):
        """Gibt das älteste Timestamp-Feld aus der Datenbank zurück, oder None wenn DB leer."""
        ts_col = self.config.timestamp_field
        query = f"""
            SELECT MIN({ts_col}) AS ts
            FROM {self.config.table_name}
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