#!/usr/bin/env bash
set -euo pipefail

SRC="./jail.local"
DST="/etc/fail2ban/jail.local"

echo "==> Backup + Install"
sudo install -m 0644 -b -S ".bak.$(date +%F_%H%M%S)" "$SRC" "$DST"

echo "==> Fail2Ban Config-Test" 
# Prüft Syntax & Referenzen
sudo fail2ban-server -t

echo "==> Restart"
sudo systemctl restart fail2ban

echo "==> Fail2Ban Status"
sudo systemctl --no-pager -l status fail2ban || true
sudo fail2ban-client status
sudo fail2ban-client status sshd

echo "==> sshd Jail Parameter"
sudo fail2ban-client get sshd bantime
sudo fail2ban-client get sshd maxretry
sudo fail2ban-client get sshd findtime

echo "==> UFW Status (Bans sichtbar?)"
sudo ufw status numbered || true

echo "==> Logs 24h"
sudo journalctl -u fail2ban --since "24 hours ago" --no-pager
sudo journalctl -u ssh --since "24 hours ago" --no-pager || true