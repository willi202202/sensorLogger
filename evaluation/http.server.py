import os
import shutil
import http.server
import socketserver
import webbrowser
import logging
from pathlib import Path
from datetime import datetime, timedelta

from models import SystemConfig
from repository import (
    SensorRepository,
    ConfigError,
    DatabaseFileNotFound,
    TableNotFound,
    ColumnNotFound,
)
from utils import generate_image_json  # <== NUR DAS! start_html_server hier NICHT importieren.


# ---------------------------------------------------------------------------
# Logging-Konfiguration
# ---------------------------------------------------------------------------

LOG_LEVEL = logging.INFO  # für mehr Details: logging.DEBUG

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("sensor_dashboard")


# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------

# Projektwurzel = Ordner oberhalb von evaluation/
REPORT_ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = REPORT_ROOT / "log" / "reports"
HTML_DIR = REPORT_ROOT / "HTML"
CONFIG_PATH = REPORT_ROOT / "evaluation" / "sensor_config.json"

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

def generate_reports() -> None:
    """Generiert alle Reports (day/week/month/year), falls nötig."""
    global _last_regen

    # Throttling
    if _last_regen and datetime.now() - _last_regen < _MIN_REGEN_INTERVAL:
        logger.debug("Reports noch frisch genug, keine Neugenerierung.")
        return

    logger.info("🔄 Generiere Reports neu ...")

    cfg = SystemConfig(str(CONFIG_PATH))

    try:
        repo = SensorRepository(cfg, validate_schema=True)
    except DatabaseFileNotFound as e:
        logger.error("DB-Fehler: %s", e)
        return
    except TableNotFound as e:
        logger.error("Tabellen-Fehler: %s", e)
        return
    except ColumnNotFound as e:
        logger.error("Spalten-Fehler: %s", e)
        return
    except ConfigError as e:
        logger.error("Konfig-Fehler: %s", e)
        return

    # Batterie-Status (für Log)
    repo.get_last_battery_status(printnow=True)

    first = repo.get_first_timestamp()
    last = repo.get_latest_timestamp()
    if first is None or last is None:
        logger.error("Keine Einträge in der Datenbank.")
        return

    first_dt = _parse_db_timestamp(first)
    last_dt = _parse_db_timestamp(last)

    logger.info("🕘 First DB entry: %s", first_dt)
    logger.info("🕘 Last  DB entry: %s", last_dt)

    # Zeitbereiche
    last_minus_24h = last_dt - timedelta(hours=24)
    last_minus_1w = last_dt - timedelta(weeks=1)
    last_minus_1Mt = last_dt - timedelta(days=30)
    last_minus_1y = last_dt - timedelta(days=365)

    logger.debug("last_minus_24h: %s", last_minus_24h)
    logger.debug("last_minus_1w : %s", last_minus_1w)
    logger.debug("last_minus_1Mt: %s", last_minus_1Mt)
    logger.debug("last_minus_1y : %s", last_minus_1y)

    # ------------------------------------------------------------------
    # HIER deine "wilde" Liste – nur mit Path statt r"..\..."
    # ------------------------------------------------------------------

    day_dir = REPORT_DIR / "day"
    week_dir = REPORT_DIR / "week"
    month_dir = REPORT_DIR / "month"
    year_dir = REPORT_DIR / "year"

    for d in (day_dir, week_dir, month_dir, year_dir):
        _ensure_dir(d)

    # DAY Plots
    logger.info("Erzeuge DAY-Reports ...")
    repo.multiplot_last_sensor_values(
        ["Outdoor_Temperature", "Indoor_Temperature",
         "Outdoor_Humidity", "Indoor_Humidity", "battery"],
        filename=day_dir / "status.png",
        show=False,
    )

    repo.multiplot_sensor_values_describe(
        ["Outdoor_Temperature", "Indoor_Temperature",
         "Outdoor_Humidity", "Indoor_Humidity", "battery"],
        last_minus_24h,
        last_dt,
        filename=day_dir / "describe.png",
        show=False,
    )

    repo.plot_sensor_values(
        "Outdoor_Temperature",
        last_minus_24h,
        last_dt,
        filename=day_dir / "Outdoor_Temperature_last_minus_24h.png",
        show=False,
    )

    repo.plot_sensor_values(
        "Indoor_Temperature",
        last_minus_24h,
        last_dt,
        filename=day_dir / "Indoor_Temperature_last_minus_24h.png",
        show=False,
    )

    generate_image_json(day_dir, output_json="images.json", status_image="status.png")

    # WEEK Plots
    logger.info("Erzeuge WEEK-Reports ...")
    shutil.copy2(day_dir / "status.png", week_dir / "status.png")

    repo.multiplot_sensor_values_describe(
        ["Outdoor_Temperature", "Indoor_Temperature",
         "Outdoor_Humidity", "Indoor_Humidity", "battery"],
        last_minus_1w,
        last_dt,
        filename=week_dir / "describe.png",
        show=False,
    )

    repo.plot_sensor_values(
        "Outdoor_Temperature",
        last_minus_1w,
        last_dt,
        filename=week_dir / "Outdoor_Temperature_last_minus_1w.png",
        show=False,
    )

    repo.plot_sensor_values(
        "Indoor_Temperature",
        last_minus_1w,
        last_dt,
        filename=week_dir / "Indoor_Temperature_last_minus_1w.png",
        show=False,
    )

    generate_image_json(week_dir, output_json="images.json", status_image="status.png")

    # MONTH Plots
    logger.info("Erzeuge MONTH-Reports ...")
    shutil.copy2(day_dir / "status.png", month_dir / "status.png")

    repo.multiplot_sensor_values_describe(
        ["Outdoor_Temperature", "Indoor_Temperature",
         "Outdoor_Humidity", "Indoor_Humidity", "battery"],
        last_minus_1Mt,
        last_dt,
        filename=month_dir / "describe.png",
        show=False,
    )

    repo.plot_sensor_values(
        "Outdoor_Temperature",
        last_minus_1Mt,
        last_dt,
        filename=month_dir / "Outdoor_Temperature_last_minus_1Mt.png",
        show=False,
    )

    repo.plot_sensor_values(
        "Indoor_Temperature",
        last_minus_1Mt,
        last_dt,
        filename=month_dir / "Indoor_Temperature_last_minus_1Mt.png",
        show=False,
    )

    generate_image_json(month_dir, output_json="images.json", status_image="status.png")

    # YEAR Plots
    logger.info("Erzeuge YEAR-Reports ...")
    shutil.copy2(day_dir / "status.png", year_dir / "status.png")

    repo.multiplot_sensor_values_describe(
        ["Outdoor_Temperature", "Indoor_Temperature",
         "Outdoor_Humidity", "Indoor_Humidity", "battery"],
        last_minus_1y,
        last_dt,
        filename=year_dir / "describe.png",
        show=False,
    )

    repo.plot_sensor_values(
        "Outdoor_Temperature",
        last_minus_1y,
        last_dt,
        filename=year_dir / "Outdoor_Temperature_last_minus_1y.png",
        show=False,
    )

    repo.plot_sensor_values(
        "Indoor_Temperature",
        last_minus_1y,
        last_dt,
        filename=year_dir / "Indoor_Temperature_last_minus_1y.png",
        show=False,
    )

    generate_image_json(year_dir, output_json="images.json", status_image="status.png")

    # ------------------------------------------------------------------
    _last_regen = datetime.now()
    logger.info("✅ Reports aktualisiert.")


# ---------------------------------------------------------------------------
# HTTP-Handler & Server
# ---------------------------------------------------------------------------

class ReportHandler(http.server.SimpleHTTPRequestHandler):
    """Eigener Handler, der bei bestimmten Requests vorher Reports generiert."""

    def do_GET(self):
        # Bei Zugriff auf Reports (HTML oder images.json) zuerst Reports prüfen/generieren
        if self.path.startswith("/log/reports/") and (
            self.path.endswith(".html") or self.path.endswith("images.json")
        ):
            try:
                generate_reports()
            except Exception as e:
                logger.exception("Fehler beim Generieren der Reports: %s", e)

        return super().do_GET()


def start_html_server(server_directory: Path | str,
                      html_file: str | Path,
                      port: int = 8000,
                      open_browser: bool = True) -> None:
    """
    Startet einen lokalen Webserver im angegebenen Verzeichnis
    und blockiert, bis CTRL+C gedrückt wird.
    """
    server_directory_path = Path(server_directory).resolve()
    if not server_directory_path.is_dir():
        raise FileNotFoundError(f"Verzeichnis {server_directory_path} wurde nicht gefunden!")
    logger.info("🌍 Webserver Verzeichnis %s gefunden", server_directory_path)

    html_file_str = str(html_file).lstrip("/\\")
    html_path = (server_directory_path / html_file_str).resolve()
    if not html_path.is_file():
        raise FileNotFoundError(f"HTML-Datei {html_path} wurde nicht gefunden!")
    logger.info("📄 HTML-Datei: %s gefunden", html_path)

    os.chdir(server_directory_path)

    with socketserver.TCPServer(("0.0.0.0", port), ReportHandler) as httpd:
        rel_html = html_path.relative_to(server_directory_path).as_posix()
        url = f"http://localhost:{port}/{rel_html}"
        logger.info("🌐 Webserver läuft auf %s", url)
        logger.info("Zum Beenden CTRL + C drücken.")

        if open_browser:
            webbrowser.open(url)

        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            logger.info("🛑 Server gestoppt.")


if __name__ == "__main__":
    start_html_server(REPORT_ROOT, "HTML/index.html", port=8000, open_browser=True)
