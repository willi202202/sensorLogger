# README: Secure Raspberry Pi Report Page with HTTPS, Password Protection & fail2ban

Dieses README beschreibt, wie du deine Reporting‑Webseite auf deinem Raspberry Pi komplett abgesichert betreibst – **nur HTTPS**, **Passwortschutz (Basic Auth)** und **fail2ban‑Schutz**.

---

## 1. Ordner vorbereiten
```bash
sudo mkdir -p /var/www
sudo chown $(whoami):$(whoami) /var/www
```

Eine index.html erstellen:
```bash
nano /var/www/index.html
```

Einfacher Inhalt:
```html
<h1>Raspberry Report</h1>
<p>Willkommen auf der gesicherten Seite!</p>
```

---

## 2. Nginx installieren
```bash
sudo apt update
sudo apt install -y nginx
systemctl status nginx
```

---

## 3. HTTPS erstellen (Self‑Signed Certificate)

### Ordner
```bash
sudo mkdir -p /etc/nginx/certs
```

### Zertifikat erzeugen
```bash
sudo openssl req -x509 -nodes -days 365   -newkey rsa:2048   -keyout /etc/nginx/certs/raspi.key   -out /etc/nginx/certs/raspi.crt
```

Bei Fragen kannst du alles leer lassen oder sinnvoll befüllen.

---

## 4. Passwortschutz erstellen

```bash
sudo apt install apache2-utils
sudo htpasswd -c /etc/nginx/.htpasswd admin
```

> Benutzername frei wählbar (hier `admin`)

---

## 5. Nginx konfigurieren

### Datei anlegen
```bash
sudo nano /etc/nginx/sites-available/raspi_report.conf
```

### Konfiguration einfügen
```
server {
    listen 443 ssl;
    server_name _;

    ssl_certificate     /etc/nginx/certs/raspi.crt;
    ssl_certificate_key /etc/nginx/certs/raspi.key;

    root /var/www;

    location / {
        auth_basic           "Restricted";
        auth_basic_user_file /etc/nginx/.htpasswd;
        try_files $uri $uri/ =404;
    }
}

# HTTP → Redirect to HTTPS
server {
    listen 80;
    return 301 https://$host$request_uri;
}
```

---

## 6. Site aktivieren
```bash
sudo ln -s /etc/nginx/sites-available/raspi_report.conf /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default
sudo systemctl reload nginx
```

---

## 7. Testen im Browser

👉 https://IP‑ADRESSE/

Beispiel:
```
https://192.168.1.203/
```

Zertifikat bestätigen (wegen Self‑Signed).
Login‑Popup erscheint.

---

## 8. fail2ban installieren & konfigurieren

### Installation
```bash
sudo apt install fail2ban
```

### Konfiguration
```bash
sudo nano /etc/fail2ban/jail.local
```

Folgendes einfügen:
```
[nginx-http-auth]
enabled = true
filter = nginx-http-auth
port = http,https
logpath = /var/log/nginx/error.log
maxretry = 3
```

Restart:
```bash
sudo systemctl restart fail2ban
```

Status prüfen:
```bash
sudo fail2ban-client status nginx-http-auth
```

---


