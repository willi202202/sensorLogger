sudo journalctl --vacuum-time=30d
sudo journalctl --vacuum-size=1G
sudo nano /etc/systemd/journald.conf

sudo systemctl restart systemd-journald




Journal-Einträge anzeigen und filtern
sudo journalctl							Zeigt das gesamte Journal von Anfang an an.
sudo journalctl -n 50					Zeigt nur die letzten 50 Journal-Einträge an.
sudo journalctl -f						Zeigt das Journal in Echtzeit an (ähnlich wie tail -f).
sudo journalctl -r						Zeigt das Journal in umgekehrter Reihenfolge an (die neuesten Einträge zuerst).
sudo journalctl --since "1 hour ago"	Zeigt Einträge nur innerhalb des letzten Stunde an. (Sie können auch Zeitstempel wie "2025-12-04 10:00:00" verwenden).
sudo journalctl --since "1 minute ago"

Filtern nach Quelle und Dienst:
sudo journalctl -u ssh.service			Zeigt alle Einträge für eine spezifische Systemd-Einheit (z.B. den SSH-Dienst) an.
sudo journalctl _COMM=sshd				Filtert nach dem ausführenden Programm (sshd ist der SSH-Daemon).
sudo journalctl -k						Zeigt nur die Kernel-Meldungen an (wichtig für Hardware-Fehler oder UFW BLOCKs).
sudo journalctl -p err					Zeigt nur Meldungen mit der Priorität "Fehler" (err) und höher (crit, alert, emerg) an.
sudo journalctl _PID=<PID>				Zeigt alle Logs für eine spezifische Prozess-ID an.

Journal-Größe und Verwaltung
journalctl --disk-usage	Zeigt, wie viel Speicherplatz das Journal aktuell belegt.
sudo journalctl --vacuum-size=500M	Reduziert die Gesamtgröße des Journals auf 500 Megabyte (löscht die ältesten Einträge).
sudo journalctl --vacuum-time=30d	Löscht alle Einträge, die älter als 30 Tage sind.
sudo journalctl --rotate	Erzwingt eine sofortige Rotation (Archivierung) der Log-Dateien.