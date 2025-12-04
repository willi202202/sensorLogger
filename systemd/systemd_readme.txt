erstelle Datei mobilealerts.service im Systemd-Verzeichnis.
cd /etc/systemd/system/

Dienst aktivieren und starten:
Systemd-Konfiguration neu laden:
sudo systemctl daemon-reload
Dienst beim Systemstart aktivieren (Auto-Start):
sudo systemctl enable mobilealerts.service
Dienst jetzt starten:
sudo systemctl start mobilealerts.service

Status prüfen:
sudo systemctl status mobilealerts.service
Logs (Ausgabe deines Skripts) ansehen:
sudo journalctl -u mobilealerts.service -f



erstelle Datei mobilealerts.service im Systemd-Verzeichnis.
cd /etc/systemd/system/

# Systemd neu laden
sudo systemctl daemon-reload

# Timer aktivieren und starten (der Timer startet dann den Service)
sudo systemctl enable mqtt-report.timer
sudo systemctl start mqtt-report.timer

# Status prüfen
sudo systemctl status mqtt-report.timer