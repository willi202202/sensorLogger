# Dieses Skript muss als "sudo" ausgeführt werden!

# 1. Restart
echo "Restart des API Server"
sudo systemctl restart api_server.service

# 2. Logger Status prüfen.
echo "Prüfe den Status des API Server (sollte 'running' anzeigen):"
sudo systemctl status api_server.service

# 3. Live-Logs des Services anzeigen.
echo "Zeige Live-Logs (Strg+C zum Beenden):"
sudo journalctl -u api_server.service -n 100 -f