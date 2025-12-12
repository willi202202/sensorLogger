import os
import json
import webbrowser
import http.server
import socketserver
from threading import Thread
from pathlib import Path
from datetime import datetime
from models import Sensor
import pandas as pd

def format_iso_timestamp(ts, fmt="%Y-%m-%d %H:%M"):
    """
    Akzeptiert:
      - ISO-String: "2025-12-05T23:45:12.000Z"
      - pandas.Timestamp
      - datetime.datetime
      - None

    Gibt formatierten String zurück.
    """

    if ts is None:
        return "-"

    # Falls pandas.Timestamp
    if isinstance(ts, pd.Timestamp):
        return ts.strftime(fmt)

    # Falls datetime.datetime
    if isinstance(ts, datetime):
        return ts.strftime(fmt)

    # Falls String
    if isinstance(ts, str):
        s = ts

        # 'Z' entfernen
        if s.endswith("Z"):
            s = s[:-1]

        # ISO-String in datetime
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            return ts  # unverändert zurückgeben

        return dt.strftime(fmt)

    # Unbekannter Typ – einfach zurückgeben
    return str(ts)


# Schöne Formatierung mit Einheit
def fmt(v, sensor):
    if pd.isna(v):
        return "-"
    unit = sensor.unit or ""
    value_str = f"{v:.{sensor.round}f}"
    return f"{value_str} {unit}" if unit else value_str

def generate_image_json(image_dir, output_json="images.json", status_image="status.png"):
    """
    Erzeugt eine images.json Datei.
    - 'status_image' bleibt ein separates Feld
    - das Statusbild wird NICHT in der List 'plots' aufgeführt
    """

    image_dir = Path(image_dir)

    # PNG-Dateien sammeln
    png_files = sorted(
        [f.name for f in image_dir.glob("*.png")],
        key=lambda x: x.lower()
    )

    # Statusbild rausfiltern
    plots = [f for f in png_files if f != status_image]

    data = {
        "status_image": status_image,
        "plots": plots
    }

    # JSON-Pfad bestimmen
    json_path = image_dir / output_json
    json_path.parent.mkdir(parents=True, exist_ok=True)

    # JSON schreiben
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print(f"📄 images.json erzeugt: {json_path}")
    #print(f"   {len(plots)} Plotbilder gefunden (Statusbild ausgeschlossen).")