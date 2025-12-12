
from models import SystemConfig
from repository import SensorRepository, ConfigError, DatabaseFileNotFound, TableNotFound, ColumnNotFound
from utils import generate_image_json, start_html_server
from pathlib import Path
from datetime import datetime, timedelta
import sys
import shutil

cfg = SystemConfig("sensor_config.json")

try:
    repo = SensorRepository(cfg, validate_schema=True)
except DatabaseFileNotFound as e:
    print("❌ DB-Fehler:", e)
except TableNotFound as e:
    print("❌ Tabellen-Fehler:", e)
except ColumnNotFound as e:
    print("❌ Spalten-Fehler:", e)
except ConfigError as e:
    print("❌ Konfig-Fehler:", e)
else:
    repo.get_last_battery_status(printnow=True)

    first = repo.get_first_timestamp()
    last = repo.get_latest_timestamp()
    if first is None:
        print("❌ No entries in database!")
    else:
        first = datetime.fromisoformat(first.rstrip("Z"))
        print(f"🕘 First DB entry: {first}")
        last = datetime.fromisoformat(last.rstrip("Z"))
        print(f"🕘 Last DB entry : {last}")
        last_minus_24h = last - timedelta(hours=24)
        print(f"🕘 last_minus_24h : {last_minus_24h}")
        midnight = last.replace(hour=0, minute=0, second=0, microsecond=0)
        print(f"🕘 midnight : {midnight}")
        last7days = [(midnight - timedelta(days=i)) for i in range(7)]
        for i, d in enumerate(last7days):
            print(f"🕘 Day -{i}: {d} ({d:%A})")
        last_minus_1w = last - timedelta(weeks=1)
        print(f"🕘 last_minus_1w : {last_minus_1w}")
        last5weeks = [(midnight - timedelta(weeks=i)) for i in range(5)]
        for i, d in enumerate(last5weeks):
            print(f"🕘 Week -{i}: {d} (KW {d.isocalendar().week})")
        
        last_minus_1Mt = last -  timedelta(days=30)
        print(f"🕘 last_minus_1Mt : {last_minus_1Mt}")
        last12months = [(midnight.replace(day=1) - timedelta(days=30*i)).replace(day=1) for i in range(12)]
        for i, d in enumerate(last12months):
            print(f"🕘 Month -{i}: {d} ({d:%B %Y})")
        
        last_minus_1y = last - timedelta(days=365)
        print(f"🕘 last_minus_1y : {last_minus_1y}")
        last5years = [(midnight.replace(month=1, day=1) - timedelta(days=365*i)).replace(month=1, day=1) for i in range(5)]
        for i, d in enumerate(last5years):
            print(f"🕘 Year -{i}: {d} ({d:%Y})")

        # DAY Plots
        repo.multiplot_last_sensor_values(["Outdoor_Temperature", "Indoor_Temperature", "Outdoor_Humidity", "Indoor_Humidity", "battery"], filename=r"..\log\reports\day\status.png", show=False)
        repo.multiplot_sensor_values_describe(["Outdoor_Temperature", "Indoor_Temperature", "Outdoor_Humidity", "Indoor_Humidity", "battery"], last_minus_24h, last, filename=r"..\log\reports\day\describe.png", show=False)
        repo.plot_sensor_values("Outdoor_Temperature", last_minus_24h, last, filename=r"..\log\reports\day\Outdoor_Temperature_last_minus_24h.png", show=False)
        repo.plot_sensor_values("Indoor_Temperature", last_minus_24h, last, filename=r"..\log\reports\day\Indoor_Temperature_last_minus_24h.png", show=False)
        generate_image_json(Path(r"..\log\reports\day"), output_json="images.json", status_image="status.png")
        
        # WEEK Plots
        shutil.copy2(r"..\log\reports\day\status.png", r"..\log\reports\week\status.png")
        repo.multiplot_sensor_values_describe(["Outdoor_Temperature", "Indoor_Temperature", "Outdoor_Humidity", "Indoor_Humidity", "battery"], last_minus_1w, last, filename=r"..\log\reports\week\describe.png", show=False)
        repo.plot_sensor_values("Outdoor_Temperature", last_minus_1w, last, filename=r"..\log\reports\week\Outdoor_Temperature_last_minus_1w.png", show=False)
        repo.plot_sensor_values("Indoor_Temperature", last_minus_1w, last, filename=r"..\log\reports\week\Indoor_Temperature_last_minus_1w.png", show=False)
        generate_image_json(Path(r"..\log\reports\week"), output_json="images.json", status_image="status.png")
        
        # MONTH Plots
        shutil.copy2(r"..\log\reports\day\status.png", r"..\log\reports\month\status.png")
        repo.multiplot_sensor_values_describe(["Outdoor_Temperature", "Indoor_Temperature", "Outdoor_Humidity", "Indoor_Humidity", "battery"], last_minus_1Mt, last, filename=r"..\log\reports\month\describe.png", show=False)
        repo.plot_sensor_values("Outdoor_Temperature", last_minus_1Mt, last, filename=r"..\log\reports\month\Outdoor_Temperature_last_minus_1Mt.png", show=False)
        repo.plot_sensor_values("Indoor_Temperature", last_minus_1Mt, last, filename=r"..\log\reports\month\Indoor_Temperature_last_minus_1Mt.png", show=False)
        generate_image_json(Path(r"..\log\reports\month"), output_json="images.json", status_image="status.png")
        
        # YEAR Plots
        shutil.copy2(r"..\log\reports\day\status.png", r"..\log\reports\year\status.png")
        repo.multiplot_sensor_values_describe(["Outdoor_Temperature", "Indoor_Temperature", "Outdoor_Humidity", "Indoor_Humidity", "battery"], last_minus_1y, last, filename=r"..\log\reports\year\describe.png", show=False)
        repo.plot_sensor_values("Outdoor_Temperature", last_minus_1y, last, filename=r"..\log\reports\year\Outdoor_Temperature_last_minus_1y.png", show=False)
        repo.plot_sensor_values("Indoor_Temperature", last_minus_1y, last, filename=r"..\log\reports\year\Indoor_Temperature_last_minus_1y.png", show=False)
        generate_image_json(Path(r"..\log\reports\year"), output_json="images.json", status_image="status.png")
        
        # Start dashboard server
        start_html_server(Path(r".."), r"HTML/index.html", port=8000, open_browser=True)

        print("Stoppe hier…")
        sys.exit()

        repo.get_sensor_values_describe("Outdoor_Temperature", "2025-12-05T18:00:00.000Z", "2025-12-05 23:50:00", printnow=False)

        repo.plot_sensor_values("Outdoor_Temperature", "2025-12-05T18:00:00.000Z", "2025-12-08 23:50:00", filename=r"..\log\images\Outdoor_Temperature.png", show=False)
        repo.plot_sensor_values("temp_in", "2025-12-05T18:00:00.000Z", "2025-12-08 23:50:00", filename=r"..\log\images\temp_in.png", show=False)

        # mehrere Temperaturen im gleichen Plot
        repo.multiplot_sensor_values(["temperatureIN", "temp2", "temp3"],
                                    start_time="2025-12-05 18:00:00",
                                    stop_time="2025-12-08 23:00:00",
                                    filename=r"../log/images/testplot1.png",
                                    show=False)
        
        repo.multiplot_sensor_values_describe(["temperatureIN", "temp2", "Outdoor_Humidity", "battery"],
                                    start_time="2025-12-05 18:00:00",
                                    stop_time="2025-12-08 23:00:00",
                                    filename=r"../log/images/testplot2.png",
                                    show=False)

        # Temperatur + Luftfeuchte -> zwei Subplots (°C und %RH)
        repo.multiplot_sensor_values(["Outdoor_Temperature", "temp2", "Outdoor_Humidity"],
                                    start_time="2025-12-05 18:00:00",
                                    stop_time="2025-12-08 23:00:00",
                                    filename=r"../log/images/testplot3.png",
                                    show=False)
        
        repo.multiplot_last_sensor_values(["temperatureIN", "temp2", "Outdoor_Humidity", "battery"], filename=r"../log/images/status.png", show=False)

        repo.get_last_sensor_value(["temperatureIN", "temp2", "Outdoor_Humidity", "battery"], printnow=False)

        generate_image_json(Path(r"../log/images"), output_json="images.json", status_image="status.png")

        start_html_server(Path(r"../HTML/images"), "index.html", port=8000, open_browser=True)