#!/bin/bash

sudo cp index.html /var/www/index.html
sudo cp pages.json /var/www/pages.json
sudo cp api.js /var/www/api.js
sudo cp alarm_settings.html /var/www/weather/alarm_settings.html
sudo cp day_th.html /var/www/weather/day_th.html
sudo cp week_th.html /var/www/weather/week_th.html
sudo cp month_th.html /var/www/weather/month_th.html
sudo cp year_th.html /var/www/weather/year_th.html
sudo cp day_w.html /var/www/weather/day_w.html
sudo cp week_w.html /var/www/weather/week_w.html
sudo cp month_w.html /var/www/weather/month_w.html
sudo cp year_w.html /var/www/weather/year_w.html

# Eigentümer setzen
sudo chown -R raspiroman:www-data /var/www/weather

# Rechte setzen
sudo chmod -R 755 /var/www/weather

sudo systemctl reload nginx