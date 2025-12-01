import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import io
import smtplib
import argparse
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.units import inch
from datetime import datetime, timedelta, timezone # <-- HINZUGEFÜGT: timezone

# --- KONFIGURATION START ---
DB_FILE = "log/mobilealerts.db"
REPORT_FILENAME = "log/MobileAlerts_Wochenbericht.pdf"
DAYS_AGO = 7 # Berichtszeitraum: Letzten 7 Tage

# E-MAIL KONFIGURATION (MUSS ANGEPASST WERDEN)
SMTP_SERVER = "mail.gmx.net"  # Beispiel: 'smtp.gmail.com'
SMTP_PORT = 587                       # 587 (TLS) oder 465 (SSL)
SMTP_USER = "roman.willi@gmx.ch"
SMTP_PASSWORD = "P5EXDXX3QSFIPKRTQJ77"  # HINWEIS: Verwende bei Gmail/Outlook App-Passwörter!
RECIPIENT_EMAIL = "roman.willi@gmx.ch"
SENDER_EMAIL = SMTP_USER
# --- KONFIGURATION ENDE ---


def test_email_connection():
    """Testet die Verbindung zum SMTP-Server und sendet eine einfache Test-E-Mail."""
    print("\n--- STARTE E-MAIL VERBINDUNGSTEST ---")
    
    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = RECIPIENT_EMAIL
    msg['Subject'] = "Mobile Alerts Test-E-Mail"

    body = f"Dies ist eine automatische Test-E-Mail vom Mobile Alerts Bericht-Generator ({datetime.now().strftime('%d.%m.%Y %H:%M')}). Ihre SMTP-Konfiguration ist erfolgreich."
    msg.attach(MIMEText(body, 'plain'))
    
    try:
        print(f"Versuche, eine Verbindung zu {SMTP_SERVER}:{SMTP_PORT} herzustellen...")
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        # server.set_debuglevel(1) # Kann zur detaillierten Fehlerbehebung aktiviert werden
        server.starttls()
        print("Versuche, mich anzumelden...")
        server.login(SMTP_USER, SMTP_PASSWORD)
        
        print(f"Sende Test-E-Mail an {RECIPIENT_EMAIL}...")
        server.sendmail(SENDER_EMAIL, RECIPIENT_EMAIL, msg.as_string())
        
        server.quit()
        print("✅ E-Mail-Test erfolgreich! Bitte überprüfen Sie Ihren Posteingang.")
        return True
        
    except smtplib.SMTPAuthenticationError:
        print("❌ SMTP-Authentifizierungsfehler! Überprüfen Sie Benutzername/Passwort oder App-Passwörter.")
    except smtplib.SMTPServerDisconnected:
        print("❌ SMTP-Server-Fehler: Server hat die Verbindung unerwartet getrennt.")
    except Exception as e:
        print(f"❌ Allgemeiner Fehler beim E-Mail-Test (Prüfen Sie Server/Port/TLS): {e}")
    
    return False
    print("--- E-MAIL VERBINDUNGSTEST BEENDET ---")


def fetch_data_and_analyze(db_file, days_ago):
    """Holt die Daten der letzten X Tage aus der SQLite-DB und aggregiert sie."""
    print("Starte Datenabfrage und Analyse...")
    
    # Berechne den Startzeitpunkt (X Tage in der Vergangenheit)
    cutoff_date = datetime.now() - timedelta(days=days_ago)
    cutoff_date_iso = cutoff_date.isoformat()
    
    try:
        conn = sqlite3.connect(db_file)
        
        # Abfrage: Wähle alle Messungen seit dem Stichtag.
        query = f"""
            SELECT * FROM measurements 
            WHERE timestamp_iso >= '{cutoff_date_iso}' 
            ORDER BY timestamp_iso
        """
        df = pd.read_sql_query(query, conn)
        conn.close()

    except Exception as e:
        print(f"❌ Fehler beim Lesen der Datenbank: {e}")
        return None, None

    if df.empty:
        print("ℹ️ Keine Daten für den Berichtszeitraum gefunden.")
        return df, None

    # Datenvorbereitung
    df['timestamp_iso'] = pd.to_datetime(df['timestamp_iso'])
    # Setze den Zeitstempel als Index für die Zeitreihenanalyse
    df.set_index('timestamp_iso', inplace=True)

    # Aggregation: Berechne den Tagesmittelwert und Min/Max für die Gartentemperatur (Temp1)
    # Beachte: Dies aggregiert alle Sensoren zusammen! Idealerweise aggregiert man nach Sensor_Name.
    # Wir nehmen hier nur Temp1 als Beispiel.
    daily_summary = df.groupby(df.index.date)['temp1'].agg(['mean', 'min', 'max']).round(1)
    daily_summary.index = pd.to_datetime(daily_summary.index).strftime('%d.%m.')
    
    return df, daily_summary

def create_plot(df):
    """Erstellt ein Liniendiagramm der Temperatur über die Zeit."""
    print("Erstelle Diagramm...")
    
    # Nutze nur die letzten 7 Tage
    # FIX: Nutze timezone.utc, um den Vergleich UTC-aware zu machen.
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    df_plot = df[df.index >= seven_days_ago].copy()

    # Erstelle das Diagramm (z.B. Temperaturverlauf von Temp1)
    fig, ax = plt.subplots(figsize=(8, 4))
    
    # Filtere NaN-Werte für eine saubere Darstellung
    temp_data = df_plot['temp1'].dropna()
    
    ax.plot(temp_data.index, temp_data.values, label='Temperatur (Temp1) [°C]', color='tab:red', linewidth=1)
    
    ax.set_title(f"Temperaturverlauf der letzten {DAYS_AGO} Tage", fontsize=12)
    ax.set_xlabel("Datum und Uhrzeit")
    ax.set_ylabel("Temperatur [°C]")
    ax.legend()
    ax.grid(True, linestyle='--', alpha=0.6)
    
    # Formatiere die x-Achse, um die Lesbarkeit zu verbessern
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    
    # Speichere das Diagramm in einem BytesIO-Objekt (im Speicher)
    img_data = io.BytesIO()
    plt.savefig(img_data, format='png')
    plt.close(fig) # Schließe die Matplotlib-Figur
    
    print("✅ Diagramm erstellt.")
    img_data.seek(0)
    return img_data

def create_pdf(daily_summary, plot_img_data):
    """Erstellt das PDF-Dokument mit ReportLab."""
    print("Generiere PDF-Bericht...")
    
    doc = SimpleDocTemplate(REPORT_FILENAME, pagesize=A4,
                            rightMargin=72, leftMargin=72,
                            topMargin=72, bottomMargin=72)
    styles = getSampleStyleSheet()
    story = []

    # --- 1. TITEL ---
    titel = f"Mobile Alerts – Wochenbericht ({DAYS_AGO} Tage)"
    story.append(Paragraph(titel, styles['Title']))
    story.append(Spacer(1, 0.5 * inch))

    # --- 2. ZUSAMMENFASSUNG ---
    summary_text = f"Dieser Bericht enthält eine Zusammenfassung der Messdaten vom {daily_summary.index.min()} bis zum {daily_summary.index.max()}."
    story.append(Paragraph(summary_text, styles['Normal']))
    story.append(Spacer(1, 0.25 * inch))

    # --- 3. DIAGRAMM (Visualisierung) ---
    story.append(Paragraph("Verlauf der Temperatur (Temp1)", styles['Heading2']))
    
    # Füge das Bild aus dem BytesIO-Stream ein
    if plot_img_data:
        img = RLImage(plot_img_data)
        img.drawHeight = 3.5 * inch
        img.drawWidth = 6 * inch
        story.append(img)
        story.append(Spacer(1, 0.25 * inch))
    else:
        story.append(Paragraph("ℹ️ Diagramm konnte nicht erstellt werden.", styles['Normal']))
        story.append(Spacer(1, 0.25 * inch))


    # --- 4. DATENTABELLE ---
    story.append(Paragraph("Tägliche Übersicht (Temp1)", styles['Heading2']))
    
    # Bereite die Daten für die ReportLab Tabelle vor
    table_data = [['Datum', 'Minimum (°C)', 'Maximum (°C)', 'Mittelwert (°C)']]
    for date, row in daily_summary.iterrows():
        table_data.append([
            str(date),
            str(row['min']),
            str(row['max']),
            str(row['mean'])
        ])

    # Erstelle die Tabelle und wende Styles an
    table = Table(table_data, colWidths=[1.5*inch]*4)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    
    story.append(table)
    story.append(Spacer(1, 0.5 * inch))

    # --- 5. FUSSZEILE ---
    story.append(Paragraph(f"Bericht generiert am: {datetime.now().strftime('%d.%m.%Y %H:%M')}", styles['Italic']))

    # PDF generieren
    doc.build(story)
    print(f"✅ PDF '{REPORT_FILENAME}' erfolgreich generiert.")

def send_email(file_path):
    """Sendet die erstellte PDF-Datei als Anhang per E-Mail."""
    print("Starte E-Mail-Versand...")
    
    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = RECIPIENT_EMAIL
    msg['Subject'] = f"Mobile Alerts: Wochenbericht ({DAYS_AGO} Tage)"

    body = "Im Anhang finden Sie den automatisierten Wochenbericht mit den Messdaten der Mobile Alerts Sensoren."
    msg.attach(MIMEText(body, 'plain'))

    # Füge die PDF-Datei als Anhang hinzu
    try:
        with open(file_path, "rb") as attachment:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(attachment.read())
        
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', 
                        f"attachment; filename= {REPORT_FILENAME}")
        msg.attach(part)
    except FileNotFoundError:
        print(f"❌ Dateifehler: {file_path} nicht gefunden.")
        return

    # Verbindung zum SMTP-Server herstellen und E-Mail senden
    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()  # Startet TLS-Verschlüsselung (wichtig!)
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SENDER_EMAIL, RECIPIENT_EMAIL, msg.as_string())
        server.quit()
        print("✅ E-Mail erfolgreich versendet!")
    except smtplib.SMTPAuthenticationError:
        print("❌ SMTP-Authentifizierungsfehler! Überprüfe Benutzername/Passwort oder App-Passwörter.")
    except Exception as e:
        print(f"❌ Fehler beim E-Mail-Versand: {e}")


def main():
    """Hauptfunktion zur Koordination des Berichts."""
    
    parser = argparse.ArgumentParser(description="Mobile Alerts Wochenbericht Generator.")
    parser.add_argument('--test-email', action='store_true', help="Führt nur einen Test der E-Mail-Konfiguration durch.")
    args = parser.parse_args()

    if args.test_email:
        test_email_connection()
        return

    # 1. Daten holen und analysieren
    df, daily_summary = fetch_data_and_analyze(DB_FILE, DAYS_AGO)
    
    if df.empty:
        # Versuch, eine E-Mail ohne Anhang zu senden, falls keine Daten da sind
        send_empty_report()
        return

    # 2. Plot erstellen
    plot_img_data = create_plot(df)

    # 3. PDF generieren
    create_pdf(daily_summary, plot_img_data)

    # 4. E-Mail senden
    send_email(REPORT_FILENAME)

def send_empty_report():
    """Sendet eine Benachrichtigung, wenn keine Daten verfügbar sind."""
    print("Starte Benachrichtigung über leeren Bericht...")
    
    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = RECIPIENT_EMAIL
    msg['Subject'] = "Mobile Alerts: Wochenbericht - KEINE DATEN"

    body = f"Achtung: Der automatisierte Wochenbericht konnte keine Messdaten für die letzten {DAYS_AGO} Tage finden. Bitte prüfen Sie den Logger-Dienst."
    msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SENDER_EMAIL, RECIPIENT_EMAIL, msg.as_string())
        server.quit()
        print("✅ E-Mail-Benachrichtigung gesendet.")
    except Exception as e:
        print(f"❌ Fehler beim Senden der Benachrichtigung: {e}")


if __name__ == "__main__":
    main()