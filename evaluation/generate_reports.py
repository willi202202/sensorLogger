import os
import shutil
import socketserver
import webbrowser
import logging
import pandas as pd

from rich import print
from pathlib import Path
from datetime import datetime, timedelta

from config.models import SystemConfig
from evaluation.utils import generate_image_json  # <== NUR DAS! start_html_server hier NICHT importieren.
from evaluation.exceptions import ReportsClean, Database
from evaluation.repository import (
    SensorRepository,
    ConfigError,
    DatabaseFileNotFound,
    TableNotFound,
    ColumnNotFound,
)



# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------

# Projektwurzel = Ordner oberhalb von evaluation/
REPORT_ROOT = Path(__file__).resolve().parent.parent

#REPORT_DIR = Path("/var/www/log/reports")
REPORT_DIR = Path("log/reports")
#HTML_DIR = Path("/var/www/weather")
HTML_DIR =  Path("log/reports")
CONFIG_PATH = REPORT_ROOT / "config" / "sensor_config.json"
FILENAME_TABLE_STATISTICS="table_statistics.html"
PRINT_TABLE_STATS = True

# globales Throttling
_MIN_REGEN_INTERVAL = timedelta(minutes=1)
_last_regen: datetime | None = None


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _parse_db_timestamp(ts: str) -> datetime:
    """Konvertiert DB-ISO-String '...Z' in datetime."""
    return datetime.fromisoformat(ts.rstrip("Z"))


def _ensure_dir(path: Path) -> None:
    """Legt ein Verzeichnis inkl. Eltern an, falls nicht vorhanden."""
    path.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Report-Generierung
# ---------------------------------------------------------------------------

def generate_html_table_statistics(repo, output_dir, filename) -> None:
    """Generiert eine HTML-Datei mit Tabellen-Statistiken."""

    stats = {}
    infos = {}
    for table_alias in repo.get_all_table_aliases():
        try:
            table_info = repo.get_table_info(table_alias, by_alias=True)
            infos[table_alias] = table_info
            stats_text = repo.get_table_statistics(table_alias, by_alias=True)
            stats[table_alias] = stats_text
        except Exception as e:
            stats[table_alias] = f"Error getting statistics: {e}"

    # Erzeuge HTML
    html_parts = ["<html><head><title>Table Statistics</title></head><body>"]
    html_parts.append("<h1>Table Statistics</h1>")
    for table_alias, stats_text in stats.items():
        html_parts.append(f"<h2>{infos[table_alias]} ({table_alias})</h2>")
        html_parts.append(f"<pre>{stats_text}</pre>")
    html_parts.append("</body></html>")

    html_content = "\n".join(html_parts)

    output_path = output_dir / filename
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"✅ Tabelle Statistiken gespeichert in: {output_path}")

def print_table_statistics(repo) -> None:
    """Druckt Tabellen-Statistiken auf die Konsole."""
    for table_alias in repo.get_all_table_aliases():
        try:
            table_info = repo.get_table_info(table_alias, by_alias=True)
            table_id = repo.get_table_id(table_alias, by_alias=True)
            print(f"---- {table_info} ({table_alias}, {table_id}) ----")
            stats_text = repo.get_table_statistics(table_alias, by_alias=True)
            print(stats_text)
        except Exception as e:
            print(f"[red]Error getting table statistics for '{table_alias}': {e}[/red]")

def generate_reports() -> None:
    """Generiert alle Reports (day/week/month/year), falls nötig."""
    global _last_regen

    # Throttling
    if _last_regen and datetime.now() - _last_regen < _MIN_REGEN_INTERVAL:
        raise ReportsClean("Reports noch frisch genug, keine Neugenerierung.")

    cfg = SystemConfig.load(str(CONFIG_PATH))
    cfg.__str__

    repo = SensorRepository(cfg, validate_schema=True)

    if PRINT_TABLE_STATS:
        print_table_statistics(repo)

    # Zeitbereichs-Berechnung
    first, last = repo.get_db_time_range("th", by_alias=True)

    th_first_dt = _parse_db_timestamp(first)
    th_last_dt = _parse_db_timestamp(last)

    # Zeitbereiche
    th_last_minus_24h = th_last_dt - timedelta(hours=24)
    th_last_minus_1w = th_last_dt - timedelta(weeks=1)
    th_last_minus_1Mt = th_last_dt - timedelta(days=30)
    th_last_minus_1y = th_last_dt - timedelta(days=365)
    
    #print("last_minus_24h: ", th_last_minus_24h)
    #print("last_minus_1w : ", th_last_minus_1w)
    #print("last_minus_1Mt: ", th_last_minus_1Mt)
    #print("last_minus_1y : ", th_last_minus_1y)

    first, last = repo.get_db_time_range("w", by_alias=True)

    w_first_dt = _parse_db_timestamp(first)
    w_last_dt = _parse_db_timestamp(last)

    # Zeitbereiche
    w_last_minus_24h = w_last_dt - timedelta(hours=24)
    w_last_minus_1w = w_last_dt - timedelta(weeks=1)
    w_last_minus_1Mt = w_last_dt - timedelta(days=30)
    w_last_minus_1y = w_last_dt - timedelta(days=365)

    #print("last_minus_24h: ", w_last_minus_24h)
    #print("last_minus_1w : ", w_last_minus_1w)
    #print("last_minus_1Mt: ", w_last_minus_1Mt)
    #print("last_minus_1y : ", w_last_minus_1y)

    # ------------------------------------------------------------------
    # HIER deine "wilde" Liste – nur mit Path statt r"..\..."
    # ------------------------------------------------------------------
    generate_html_table_statistics(repo, HTML_DIR, FILENAME_TABLE_STATISTICS)

    day_dir = REPORT_DIR / "day"
    week_dir = REPORT_DIR / "week"
    month_dir = REPORT_DIR / "month"
    year_dir = REPORT_DIR / "year"

    for d in (day_dir, week_dir, month_dir, year_dir):
        _ensure_dir(d)

    # DAY Plots
    show = False
    #print("Erzeuge DAY-Reports ...")
    repo.multiplot_last_sensor_values("th",
        ["Indoor_Temperature", "Outdoor_Temperature", "Garden_Temperature", "Basement_Temperature",
         "Indoor_Humidity", "Outdoor_Humidity", "Basement_Humidity", "Battery_Status"],
        filename=day_dir / "status.png",
        title="Current Sensor Values",
        show=show,
    )

    repo.multiplot_sensor_values_describe("th",
        ["Indoor_Temperature", "Outdoor_Temperature", "Garden_Temperature", "Basement_Temperature",
         "Indoor_Humidity", "Outdoor_Humidity", "Basement_Humidity", "Battery_Status"],
        th_last_minus_24h,
        th_last_dt,
        filename=day_dir / "00_describe.png",
        title="Sensor Values Description - Last 24 Hours",
        show=show,
    )

    repo.plot_sensor_values("th",
        "Indoor_Temperature",
        th_last_minus_24h,
        th_last_dt,
        filename=day_dir / "01_Indoor_Temperature_last_minus_24h.png",
        title="Indoor Temperature - Last 24 Hours",
        show=show,
    )

    repo.plot_sensor_values("th",
        "Outdoor_Temperature",
        th_last_minus_24h,
        th_last_dt,
        filename=day_dir / "02_Outdoor_Temperature_last_minus_24h.png",
        title="Outdoor Temperature - Last 24 Hours",
        show=show,
    )

    repo.plot_sensor_values("th",
        "Garden_Temperature",
        th_last_minus_24h,
        th_last_dt,
        filename=day_dir / "03_Garden_Temperature_last_minus_24h.png",
        title="Garden Temperature - Last 24 Hours",
        show=show,
    )

    repo.plot_sensor_values("th",
        "Basement_Temperature",
        th_last_minus_24h,
        th_last_dt,
        filename=day_dir / "04_Basement_Temperature_last_minus_24h.png",
        title="Basement Temperature - Last 24 Hours",
        show=show,
    )

    repo.multiplot_sensor_values("th",
        ["Indoor_Temperature", "Outdoor_Temperature", "Garden_Temperature", "Basement_Temperature"],
        th_last_minus_24h,
        th_last_dt,
        filename=day_dir / "05_Temperatures_last_minus_24h.png",
        title="Temperatures - Last 24 Hours",
        show=show,
    )

    generate_image_json(day_dir, output_json="images.json", status_image="status.png")

    # WEEK Plots
    show = False
    #print("Erzeuge WEEK-Reports ...")
    shutil.copy2(day_dir / "status.png", week_dir / "status.png")

    repo.multiplot_sensor_values_describe("th",
        ["Indoor_Temperature", "Outdoor_Temperature", "Garden_Temperature",
         "Indoor_Humidity", "Outdoor_Humidity", "Garden_Humidity", "Battery_Status"],
        th_last_minus_1w,
        th_last_dt,
        filename=week_dir / "00_describe.png",
        title="Sensor Values Description - Last Week",
        show=show,
    )

    repo.plot_sensor_values("th",
        "Indoor_Temperature",
        th_last_minus_1w,
        th_last_dt,
        filename=week_dir / "01_Indoor_Temperature_last_minus_1w.png",
        title="Indoor Temperature - Last Week",
        show=show,
    )

    repo.plot_sensor_values("th",
        "Outdoor_Temperature",
        th_last_minus_1w,
        th_last_dt,
        filename=week_dir / "02_Outdoor_Temperature_last_minus_1w.png",
        title="Outdoor Temperature - Last Week",
        show=show,
    )

    repo.plot_sensor_values("th",
        "Garden_Temperature",
        th_last_minus_1w,
        th_last_dt,
        filename=week_dir / "03_Garden_Temperature_last_minus_1w.png",
        title="Garden Temperature - Last Week",
        show=show,
    )

    repo.plot_sensor_values("th",
        "Basement_Temperature",
        th_last_minus_1w,
        th_last_dt,
        filename=week_dir / "04_Basement_Temperature_last_minus_1w.png",
        title="Basement Temperature - Last Week",
        show=show,
    )

    repo.multiplot_sensor_values("th",
        ["Indoor_Temperature", "Outdoor_Temperature", "Garden_Temperature", "Basement_Temperature"],
        th_last_minus_1w,
        th_last_dt,
        filename=week_dir / "05_Temperatures_last_minus_1w.png",
        title="Temperatures - Last Week",
        show=show,
    )

    generate_image_json(week_dir, output_json="images.json", status_image="status.png")

    # MONTH Plots
    show = False
    #print("Erzeuge MONTH-Reports ...")
    shutil.copy2(day_dir / "status.png", month_dir / "status.png")

    repo.multiplot_sensor_values_describe("th",
        ["Indoor_Temperature", "Outdoor_Temperature", "Garden_Temperature", "Basement_Temperature",
         "Indoor_Humidity", "Outdoor_Humidity", "Basement_Humidity", "Battery_Status"],
        th_last_minus_1Mt,
        th_last_dt,
        filename=month_dir / "00_describe.png",
        title="Sensor Values Description - Last Month",
        show=show,
    )

    repo.plot_sensor_values("th",
        "Indoor_Temperature",
        th_last_minus_1Mt,
        th_last_dt,
        filename=month_dir / "01_Indoor_Temperature_last_minus_1Mt.png",
        title="Indoor Temperature - Last Month",
        show=show,
    )

    repo.plot_sensor_values("th",
        "Outdoor_Temperature",
        th_last_minus_1Mt,
        th_last_dt,
        filename=month_dir / "02_Outdoor_Temperature_last_minus_1Mt.png",
        title="Outdoor Temperature - Last Month",
        show=show,
    )

    repo.plot_sensor_values("th",
        "Garden_Temperature",
        th_last_minus_1Mt,
        th_last_dt,
        filename=month_dir / "03_Garden_Temperature_last_minus_1Mt.png",
        title="Garden Temperature - Last Month",
        show=show,
    )

    repo.plot_sensor_values("th",
        "Basement_Temperature",
        th_last_minus_1Mt,
        th_last_dt,
        filename=month_dir / "04_Basement_Temperature_last_minus_1Mt.png",
        title="Basement Temperature - Last Month",
        show=show,
    )

    repo.multiplot_sensor_values("th",
        ["Indoor_Temperature", "Outdoor_Temperature", "Garden_Temperature", "Basement_Temperature"],
        th_last_minus_1Mt,
        th_last_dt,
        filename=month_dir / "05_Temperatures_last_minus_1Mt.png",
        title="Temperatures - Last Month",
        show=show,
    )

    generate_image_json(month_dir, output_json="images.json", status_image="status.png")

    # YEAR Plots
    show = False
    #print("Erzeuge YEAR-Reports ...")
    shutil.copy2(day_dir / "status.png", year_dir / "status.png")

    repo.multiplot_sensor_values_describe("th",
        ["Indoor_Temperature", "Outdoor_Temperature", "Garden_Temperature", "Basement_Temperature",
         "Indoor_Humidity", "Outdoor_Humidity", "Basement_Humidity", "Battery_Status"],
        th_last_minus_1y,
        th_last_dt,
        filename=year_dir / "00_describe.png",
        title="Sensor Values Description - Last Year",
        show=show,
    )

    repo.plot_sensor_values("th",
        "Indoor_Temperature",
        th_last_minus_1y,
        th_last_dt,
        filename=year_dir / "01_Indoor_Temperature_last_minus_1y.png",
        title="Indoor Temperature - Last Year",
        show=show,
    )

    repo.plot_sensor_values("th",
        "Outdoor_Temperature",
        th_last_minus_1y,
        th_last_dt,
        filename=year_dir / "02_Outdoor_Temperature_last_minus_1y.png",
        title="Outdoor Temperature - Last Year",
        show=show,
    )

    repo.plot_sensor_values("th",
        "Garden_Temperature",
        th_last_minus_1y,
        th_last_dt,
        filename=year_dir / "03_Garden_Temperature_last_minus_1y.png",
        title="Garden Temperature - Last Year",
        show=show,
    )

    repo.plot_sensor_values("th",
        "Basement_Temperature",
        th_last_minus_1y,
        th_last_dt,
        filename=year_dir / "04_Basement_Temperature_last_minus_1y.png",
        title="Basement Temperature - Last Year",
        show=show,
    )

    repo.multiplot_sensor_values("th",
        ["Indoor_Temperature", "Outdoor_Temperature", "Garden_Temperature", "Basement_Temperature"],
        th_last_minus_1y,
        th_last_dt,
        filename=year_dir / "05_Temperatures_last_minus_1y.png",
        title="Temperatures - Last Year",
        show=show,
    )


    generate_image_json(year_dir, output_json="images.json", status_image="status.png")

    # ------------------------------------------------------------------
    _last_regen = datetime.now()
    #print("✅ Reports aktualisiert.")


if __name__ == "__main__":
    generate_reports()
