# Dieses Skript muss als "sudo" ausgeführt werden!
# sudo bash start_systemd_mobilealerts.sh

# 1. Kopiere Dateien in das Systemd-Verzeichnis.
sudo cp ./mobilealerts.service /etc/systemd/system/mobilealerts.service

# 2. Systemd neu laden, um die neuen Unit-Dateien zu erkennen.
echo "Lade Systemd Daemon neu..."
sudo systemctl daemon-reload

# --- LOGGER DIENST ---
# 3. Den Logger Service aktivieren und sofort starten (sollte dauerhaft laufen).
echo "Aktiviere und starte den Service..."
sudo systemctl enable mobilealerts.service
sudo systemctl start mobilealerts.service

# 4. Logger Status prüfen.
echo "Prüfe den Status des Loggers (sollte 'running' anzeigen):"
sudo systemctl status mobilealerts.service

# 5. Live-Logs des Services anzeigen.
echo "Zeige Live-Logs (Strg+C zum Beenden):"
sudo journalctl -u mobilealerts.service -n 100 -f