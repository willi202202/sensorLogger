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