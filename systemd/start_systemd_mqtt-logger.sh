# Dieses Skript muss als "sudo" ausgeführt werden!
# sudo bash start_systemd_mqtt-logger.sh

# 1. Kopiere Dateien in das Systemd-Verzeichnis.
sudo cp ./mqtt-logger.service /etc/systemd/system/mqtt-logger.service

# 2. Systemd neu laden, um die neuen Unit-Dateien zu erkennen.
echo "Lade Systemd Daemon neu..."
sudo systemctl daemon-reload

# --- LOGGER DIENST ---
# 3. Den Logger Service aktivieren und sofort starten (sollte dauerhaft laufen).
echo "Aktiviere und starte den Service..."
sudo systemctl enable mqtt-logger.service
sudo systemctl start mqtt-logger.service

# 4. Logger Status prüfen.
echo "Prüfe den Status des Loggers (sollte 'running' anzeigen):"
sudo systemctl status mqtt-logger.service