# Dieses Skript muss als "sudo" ausgeführt werden!
# sudo bash mqtt-report_start_systemd.sh

# 1. Kopiere alle notwendigen Dateien in das Systemd-Verzeichnis.
sudo cp ./mqtt-report.service /etc/systemd/system/mqtt-report.service
sudo cp ./mqtt-report.timer /etc/systemd/system/mqtt-report.timer
sudo cp ./mqtt-logger.service /etc/systemd/system/mqtt-logger.service

# 2. Systemd neu laden, um die neuen Unit-Dateien zu erkennen.
echo "Lade Systemd Daemon neu..."
sudo systemctl daemon-reload

# --- LOGGER DIENST ---
# 3. Den Logger Service aktivieren und sofort starten (sollte dauerhaft laufen).
echo "Aktiviere und starte den dauerhaften MQTT-Logger Service..."
sudo systemctl enable mqtt-logger.service
sudo systemctl start mqtt-logger.service

# 4. Logger Status prüfen.
echo "Prüfe den Status des Loggers (sollte 'running' anzeigen):"
sudo systemctl status mqtt-logger.service

# --- REPORT TIMER DIENST ---
# 5. Den Timer aktivieren (er startet den Dienst später zur definierten Zeit).
echo "Aktiviere und starte den wöchentlichen Report-Timer..."
sudo systemctl enable mqtt-report.timer
sudo systemctl start mqtt-report.timer

# 6. Timer Status prüfen.
echo "Prüfe den Status des Timers (sollte 'waiting' anzeigen):"
sudo systemctl status mqtt-report.timer

# 7. Prüfe den Status des Report Services (sollte 'inactive' sein, bis der Timer auslöst).
echo "Prüfe den Status des Report Services (sollte 'inactive' sein):"
sudo systemctl status mqtt-report.service