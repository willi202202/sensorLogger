# Dieses Skript muss als "sudo" ausgeführt werden!
# sudo bash start_systemd_api_server.sh

# 1. Kopiere Dateien in das Systemd-Verzeichnis.
sudo cp ./api_server.service /etc/systemd/system/api_server.service

# 2. Systemd neu laden, um die neuen Unit-Dateien zu erkennen.
echo "Lade Systemd Daemon neu..."
sudo systemctl daemon-reload

# --- LOGGER DIENST ---
# 3. Den Logger Service aktivieren und sofort starten (sollte dauerhaft laufen).
echo "Aktiviere und starte den Service..."
sudo systemctl enable api_server.service
sudo systemctl start api_server.service

# 4. Logger Status prüfen.
echo "Prüfe den Status des Loggers (sollte 'running' anzeigen):"
sudo systemctl status api_server.service

# 5. Live-Logs des Services anzeigen.
echo "Zeige Live-Logs (Strg+C zum Beenden):"
sudo journalctl -u api_server.service -n 100 -f