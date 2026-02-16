#!/usr/bin/env python3
import os
import sys
import smtplib
import ssl
import json
import re
import urllib.request
import urllib.error
import configparser
from datetime import datetime, timezone
from email.message import EmailMessage

# --- SETUP PATHS ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.ini")
WRANGLER_FILE = os.path.join(BASE_DIR, "wrangler.jsonc")
ARCHIVE_FILE = os.path.join(BASE_DIR, "logs", "email_log")

def get_db_name():
    """Extracts database_name from wrangler.jsonc (supports comments)."""
    default = "healthcheckwatch-db"
    if not os.path.exists(WRANGLER_FILE):
        return default
    try:
        with open(WRANGLER_FILE, 'r') as f:
            content = f.read()
            content = re.sub(r'//.*', '', content)
            content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
            data = json.loads(content)
            return data.get("d1_databases", [{}])[0].get("database_name", default)
    except Exception:
        return default

def load_config():
    """Reads the config.ini file and returns the parser object."""
    if not os.path.exists(CONFIG_FILE):
        sys.stderr.write(f"Error: Configuration file not found at {CONFIG_FILE}\n")
        sys.exit(1)
    config = configparser.ConfigParser(interpolation=None)
    config.read(CONFIG_FILE)
    return config

def check_security():
    """Checks if the config file has secure permissions."""
    # Skip check on Windows where POSIX permissions don't apply
    if not os.path.exists(CONFIG_FILE) or os.name == 'nt':
        return False
        
    mode = os.stat(CONFIG_FILE).st_mode
    # Bitwise check: if ANY group or other permissions are set (0o077)
    if (mode & 0o077) != 0:
        print(f"WARNING: Your config.ini file is insecure (permissions: {oct(mode & 0o777)}).")
        print(f"WARNING: To protect your SMTP credentials, run: chmod 600 {CONFIG_FILE}")
        return True
        
    return False

def format_alert_times(config, alert):
    """Aligns all times in the alert to either UTC or Local based on config."""
    tz_setting = config.get('Settings', 'timezone', fallback='local').lower()
    body_text = alert.get('body', '')
    
    if tz_setting == 'utc':
        # Force the email generation time to UTC
        header_time = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        final_body = body_text
    else:
        # Use local system time for the header
        header_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Helper to convert a matched UTC string to Local time
        def convert_to_local(match):
            # Parse the string as UTC
            utc_dt = datetime.strptime(match.group(0), '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
            # Convert to local system timezone
            return utc_dt.astimezone().strftime('%Y-%m-%d %H:%M:%S')
            
        # Find all timestamps in the Cloudflare body and convert them
        final_body = re.sub(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', convert_to_local, body_text)
        
        # Change the column headers so the user knows it was converted
        final_body = final_body.replace('(UTC)', '(LOCAL)')
        
    return header_time, final_body

def archive_locally(alert, db_name):
    """Appends the alert to the local log file."""
    os.makedirs(os.path.dirname(ARCHIVE_FILE), exist_ok=True)
    try:
        with open(ARCHIVE_FILE, 'a') as f:
            f.write("-" * 64 + "\n")
            f.write(f"TIME:    {alert.get('header_time')}\n")
            f.write(f"DB:      {db_name}\n")
            f.write(f"SUBJECT: {alert.get('subject')}\n")
            f.write("MESSAGE:\n")
            f.write(alert.get('body', '').strip() + "\n")
            f.write("-" * 64 + "\n\n")
        return True
    except Exception as e:
        sys.stderr.write(f"Failed to write to archive: {e}\n")
        return False

def send_email(config, alert, is_insecure):
    """Sends the alert via SMTP using credentials from config.ini."""
    msg = EmailMessage()
    
    warning_block = ""
    if is_insecure:
        warning_block = (
            "🚨 WARNING: The config.ini file on your server is insecure.\n"
            "This exposes your email password to anyone else on the system.\n"
            f"To fix this, log into your server and run: chmod 600 {CONFIG_FILE}\n"
            f"{'=' * 64}\n\n"
        )
    
    content = (
        f"{warning_block}"
        f"Time: {alert.get('header_time')}\n"
        f"{'-' * 64}\n"
        f"{alert.get('body')}"
    )
    msg.set_content(content)
    
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
    db_name = get_db_name()
    is_insecure = check_security()
    
    api_url = config.get('Cloudflare', 'api_url').rstrip('/')
    api_token = config.get('Cloudflare', 'api_token')
    squelched = config.getboolean('Settings', 'squelch', fallback=False)

    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
        "User-Agent": "HealthcheckWatch-emailcheck.py/1.0"
    }

    req = urllib.request.Request(f"{api_url}/outbox", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            response_data = response.read().decode('utf-8')
            alerts = json.loads(response_data)
    except urllib.error.URLError as e:
        sys.stderr.write(f"API Fetch Error: {e}\n")
        sys.exit(1)
    except json.JSONDecodeError as e:
        sys.stderr.write(f"API JSON Parse Error: {e}\n")
        sys.exit(1)

    if not alerts:
        return

    if sys.stdout.isatty():
        mode = "SQUELCHED | Logging only" if squelched else "Sending Emails"
        print(f"Processing {len(alerts)} alerts | {mode}")

    all_processed = True

    for alert in alerts:
        alert['header_time'], alert['body'] = format_alert_times(config, alert)
        archive_locally(alert, db_name)
        
        if not squelched:
            if not send_email(config, alert, is_insecure):
                all_processed = False
                sys.stderr.write(f"Warning: Email failed for '{alert.get('subject')}'.\n")

    if all_processed:
        del_req = urllib.request.Request(f"{api_url}/outbox", headers=headers, method='DELETE')
        try:
            with urllib.request.urlopen(del_req, timeout=10) as response:
                pass
            if sys.stdout.isatty():
                print(f"DONE | Cloudflare outbox cleared ({db_name})")
        except urllib.error.URLError as e:
            sys.stderr.write(f"Failed to clear outbox: {e}\n")

if __name__ == "__main__":
    main()
