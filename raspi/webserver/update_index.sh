#!/usr/bin/env bash
set -euo pipefail

SRC="./index.conf"
DST="/etc/nginx/sites-available/index.conf"
DEST_LNK="/etc/nginx/sites-enabled/"

echo "==> Backup + Install"
sudo install -m 0644 -b -S ".bak.$(date +%F_%H%M%S)" "$SRC" "$DST"

sudo ln -s "$DST" "$DEST_LNK"
sudo rm /etc/nginx/sites-enabled/default

echo "==> Test + Reload NGINX"
sudo nginx -t
sudo systemctl reload nginx