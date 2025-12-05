erstelle Datei mobilealerts.service im Systemd-Verzeichnis.
cd /etc/systemd/system/

Dienst aktivieren und starten:
Systemd-Konfiguration neu laden:
sudo systemctl daemon-reload
Dienst beim Systemstart aktivieren (Auto-Start):
sudo systemctl enable mobilealerts.service
sudo systemctl enable mqtt-logger.service
Dienst jetzt starten:
sudo systemctl start mobilealerts.service
sudo systemctl start mqtt-logger.service

Status prüfen:
sudo systemctl status mobilealerts.service
sudo systemctl status mqtt-logger.service

Logs (Ausgabe deines Skripts) ansehen:
sudo journalctl -u mobilealerts.service -f
sudo journalctl -u mqtt-logger.service -f



erstelle Datei mobilealerts.service im Systemd-Verzeichnis.
cd /etc/systemd/system/

# Dienst stoppen:
sudo systemctl stop mobilealerts.service
sudo systemctl stop mqtt-logger.service

# Systemd neu laden
sudo systemctl daemon-reload

# Timer aktivieren und starten (der Timer startet dann den Service)
sudo systemctl enable mqtt-report.timer
sudo systemctl start mqtt-report.timer

# Status prüfen
sudo systemctl status mqtt-report.timer