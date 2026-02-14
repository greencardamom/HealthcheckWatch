#!/home/greenc/toolforge/healthcheckwatch/healthcheckwatch_env/bin/python
import os
import sys
import smtplib
import ssl
import requests
import configparser
from datetime import datetime
from email.message import EmailMessage

# --- SETUP PATHS ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.ini")
ARCHIVE_FILE = os.path.join(BASE_DIR, "logs", "email_log")

def load_config():
    """Reads the config.ini file and returns the parser object."""
    if not os.path.exists(CONFIG_FILE):
        sys.stderr.write(f"Error: Configuration file not found at {CONFIG_FILE}\n")
        sys.exit(1)

    config = configparser.ConfigParser(interpolation=None)
    config.read(CONFIG_FILE)
    return config

def archive_locally(alert):
    """Appends the alert to the local log file."""
    os.makedirs(os.path.dirname(ARCHIVE_FILE), exist_ok=True)
    try:
        with open(ARCHIVE_FILE, 'a') as f:
            f.write("----------------------------------------------------------------\n")
            f.write(f"TIME:    {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"SUBJECT: {alert.get('subject')}\n")
            f.write("MESSAGE:\n")
            f.write(alert.get('body', '').strip() + "\n")
            f.write("----------------------------------------------------------------\n\n")
        return True
    except Exception as e:
        sys.stderr.write(f"Failed to write to archive: {e}\n")
        return False

def send_email(config, alert):
    """Sends the alert via SMTP using credentials from config.ini."""
    msg = EmailMessage()
    msg.set_content(
        f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"{alert.get('body')}"
    )
    msg['Subject'] = alert.get('subject', 'HealthcheckWatch Alert')
    msg['From'] = config.get('SMTP', 'user')
    msg['To'] = config.get('SMTP', 'user')

    host = config.get('SMTP', 'host')
    port = config.getint('SMTP', 'port')
    user = config.get('SMTP', 'user')
    password = config.get('SMTP', 'pass')
    use_ssl = config.getboolean('SMTP', 'use_ssl')

    context = ssl.create_default_context()
    try:
        if use_ssl:
            with smtplib.SMTP_SSL(host, port, context=context) as s:
                s.login(user, password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port) as s:
                s.starttls(context=context)
                s.login(user, password)
                s.send_message(msg)
        return True
    except Exception as e:
        sys.stderr.write(f"Email Failed: {e}\n")
        return False

def main():
    config = load_config()
    
    api_url = config.get('Cloudflare', 'api_url').rstrip('/')
    api_token = config.get('Cloudflare', 'api_token')
    squelched = config.getboolean('Settings', 'squelch', fallback=False)

    headers = {"Authorization": f"Bearer {api_token}"}

    # 1. Fetch pending alerts from Cloudflare
    try:
        response = requests.get(f"{api_url}/outbox", headers=headers, timeout=10)
        response.raise_for_status()
        alerts = response.json()
    except Exception as e:
        sys.stderr.write(f"API Fetch Error: {e}\n")
        sys.exit(1)

    if not alerts:
        return

    if sys.stdout.isatty():
        status = "SQUELCHED (Logging only)" if squelched else "Sending Emails"
        print(f"Processing {len(alerts)} alerts... [{status}]")

    all_processed = True

    # 2. Process each alert
    for alert in alerts:
        archive_locally(alert)
        
        # If squelched, we skip sending the email, but mark as processed to clear the outbox
        if not squelched:
            if not send_email(config, alert):
                all_processed = False
                sys.stderr.write(f"Warning: Email failed for '{alert.get('subject')}'.\n")

    # 3. Clear the outbox ONLY if everything was handled successfully
    if all_processed:
        try:
            del_res = requests.delete(f"{api_url}/outbox", headers=headers, timeout=10)
            del_res.raise_for_status()
            if sys.stdout.isatty():
                print("Cloudflare outbox cleared.")
        except Exception as e:
            sys.stderr.write(f"Failed to clear outbox: {e}\n")

if __name__ == "__main__":
    main()
