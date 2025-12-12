#!/bin/bash

sudo cp index.html /var/www/index.html
sudo cp pages.json /var/www/pages.json

sudo cp day.html /var/www/weather/day.html
sudo cp week.html /var/www/weather/week.html
sudo cp month.html /var/www/weather/month.html
sudo cp year.html /var/www/weather/year.html

# Eigentümer setzen
sudo chown -R raspiroman:www-data /var/www/weather

# Rechte setzen
sudo chmod -R 755 /var/www/weather

sudo systemctl reload nginx