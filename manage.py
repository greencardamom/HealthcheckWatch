#!/usr/bin/env python3
import os
import re
import sys
import json
import time
import argparse
import subprocess
import configparser
from datetime import datetime, timezone

def get_db_name():
    """Single Source of Truth: Extracts database_name from wrangler.jsonc."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wrangler.jsonc")
    default = "healthcheckwatch-db"
    if not os.path.exists(path):
        return default
    try:
        with open(path, 'r') as f:
            content = f.read()
            content = re.sub(r'//.*', '', content)
            content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
            data = json.loads(content)
            return data.get("d1_databases", [{}])[0].get("database_name", default)
    except Exception:
        return default

# --- CONFIGURATION ---
DB_NAME = get_db_name()
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "email_log")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.ini")

def get_tz_setting():
    """Reads the timezone setting from config.ini."""
    if not os.path.exists(CONFIG_FILE):
        return 'local'
    # Fixed: Added inline_comment_prefixes so "UTC # comment" parses as "UTC"
    config = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=('#', ';'))
    config.read(CONFIG_FILE)
    try:
        return config.get('Settings', 'timezone', fallback='local').lower()
    except (configparser.NoSectionError, configparser.NoOptionError):
        return 'local'

TZ_SETTING = get_tz_setting()

def cmd_deploy(args):
    """Pushes the local index.js and wrangler.jsonc to Cloudflare."""
    print(" Preparing to deploy HealthcheckWatch to Cloudflare...")
    
    # Optional: Check if we are in the right directory by looking for wrangler.jsonc
    if not os.path.exists("wrangler.jsonc"):
        print("Error: wrangler.jsonc not found. Are you in the project root?")
        sys.exit(1)

    cmd = ["npx", "wrangler", "deploy"]
    
    try:
        # We don't use capture_output=True here because we want the user 
        # to see the real-time progress bar and the final URL from Wrangler.
        subprocess.run(cmd, check=True)
        print("\n Deployment successful!")
    except subprocess.CalledProcessError:
        print("\n Deployment failed. Check the error messages above.")
        sys.exit(1)

def run_wrangler(sql):
    """Executes a D1 SQL command via Wrangler and returns the JSON results."""
    cmd = ["npx", "wrangler", "d1", "execute", DB_NAME, "--remote", "--json", "--command", sql]
    try:
        # Run wrangler, hiding stderr unless it completely fails
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        return data[0].get('results', [])
    except subprocess.CalledProcessError as e:
        sys.stderr.write(f"Wrangler Error:\n{e.stderr}\n")
        sys.exit(1)
    except Exception as e:
        sys.stderr.write(f"Execution Error: {e}\n")
        sys.exit(1)

def format_time(epoch):
    """Converts a Unix epoch to a formatted string based on config.ini timezone."""
    if not epoch:
        return "N/A"
    
    if TZ_SETTING == 'utc':
        return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    else:
        # Defaults to the server's local system timezone
        return datetime.fromtimestamp(epoch).strftime('%Y-%m-%d %H:%M:%S')

def cmd_list(args):
    results = run_wrangler("SELECT id, last_ping, timeout_hours FROM monitors ORDER BY id ASC")
    if not results:
        print("No active monitors found.")
        return

    tz_label = "(UTC)" if TZ_SETTING == 'utc' else "(LOCAL)"

    print(f"{'MONITOR ID':<30} | {'LAST PING ' + tz_label:<20} | {'DEATH DATE ' + tz_label}")
    print("-" * 75)

    # Define 'now' as the current Unix epoch time
    now = int(time.time())

    for row in results:
        id_name = row['id']
        last = row['last_ping']
        timeout = row['timeout_hours']
        
        death_time = last + (timeout * 3600)
        
        # Format the expected death time
        status = format_time(death_time)
        
        # Add the [DEAD] indicator if the current time has passed the death time
        if now > death_time:
            status += " [DEAD]"
            
        print(f"{id_name:<30} | {format_time(last):<20} | {status}")

def cmd_status(args):
    results = run_wrangler("SELECT COUNT(*) as count FROM outbox")
    count = results[0]['count'] if results else 0
    
    if count == 0:
        print("Status: HEALTHY. The Cloudflare outbox is empty.")
    else:
        print(f"Status: BACKED UP. There are {count} pending alerts in the outbox.")

def cmd_remove(args):
    safe_id = args.id.replace("'", "") # Basic sanitization
    run_wrangler(f"DELETE FROM monitors WHERE id = '{safe_id}'")
    print(f"Monitor '{safe_id}' has been permanently removed.")

def cmd_pause(args):
    safe_id = args.id.replace("'", "")
    hours = args.hours
    
    # We "pause" by artificially moving the last_ping into the future.
    sql = f"UPDATE monitors SET last_ping = CAST(strftime('%s', 'now') AS INTEGER) + ({hours} * 3600) WHERE id = '{safe_id}'"
    run_wrangler(sql)
    print(f"Monitor '{safe_id}' has been paused. Its expected death has been pushed out by {hours} hours.")

def get_cron_minutes_until():
    """Parses wrangler.jsonc to find the next cron execution time."""
    current_minute = datetime.now().minute
    path = os.path.join(BASE_DIR, "wrangler.jsonc")
    
    # Fallback default if things go wrong
    default_until = 60 - current_minute
    
    if not os.path.exists(path):
        return default_until
        
    try:
        with open(path, 'r') as f:
            content = f.read()
            content = re.sub(r'//.*', '', content)
            content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
            data = json.loads(content)
            
        crons = data.get("triggers", {}).get("crons", [])
        if not crons:
            return default_until
            
        # Grab the minute field from the cron string (e.g. "10 * * * *")
        minute_field = crons[0].split()[0]
        
        if minute_field.isdigit():
            target = int(minute_field)
            if current_minute < target:
                return target - current_minute
            else:
                return (60 - current_minute) + target
        elif minute_field.startswith('*/') and minute_field[2:].isdigit():
            interval = int(minute_field[2:])
            next_target = ((current_minute // interval) + 1) * interval
            return next_target - current_minute
        elif minute_field == '*':
            return 1  # Runs every minute
        else:
            return default_until
            
    except Exception:
        return default_until

def cmd_test_alert(args):
    """Injects a test-alert monitor with a 0-hour timeout directly into the database."""
    print("Injecting 'test-alert' monitor into Cloudflare D1 database...")
    sql = """
    INSERT INTO monitors (id, last_ping, timeout_hours, alert_subject, alert_body) 
    VALUES ('test-alert', CAST(strftime('%s', 'now') AS INTEGER), 0, 'TEST ALERT (HCW): manage.py', 'This is a forced test alert to verify the watchdog pipeline.') 
    ON CONFLICT(id) DO UPDATE SET 
    last_ping = excluded.last_ping, 
    timeout_hours = excluded.timeout_hours,
    alert_subject = excluded.alert_subject,
    alert_body = excluded.alert_body;
    """
    run_wrangler(sql)
    
    # Dynamically calculate minutes until the next sweep
    minutes_until = get_cron_minutes_until()
    
    print("\n[DONE] Test monitor successfully created and flagged as dead on arrival.")
    print(f"The Cloudflare watchdog will drop the alert in the outbox in ~{minutes_until} minutes.")
    print("Run emailcheck.py after then.")

def cmd_log(args):
    if not os.path.exists(LOG_FILE):
        print("Log file not found. No alerts have been processed locally yet.")
        return
        
    with open(LOG_FILE, 'r') as f:
        content = f.read()
        
    # Split by the divider line you defined in emailcheck.py
    blocks = [b.strip() for b in content.split("----------------------------------------------------------------\n\n") if b.strip()]
    
    if not blocks:
        print("Log file is empty.")
        return

    print(f"--- Showing last {min(10, len(blocks))} entries ---")
    for block in blocks[-10:]:
        print("----------------------------------------------------------------")
        print(block)
        print("----------------------------------------------------------------\n")

def main():
    parser = argparse.ArgumentParser(
        description="HealthcheckWatch Management Utility",
        formatter_class=argparse.RawTextHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", title="Available commands")

    # Command: list
    parser_list = subparsers.add_parser("list", help='Shows all active monitors, their last ping time, and when they are expected to "die."')
    parser_list.set_defaults(func=cmd_list)

    # Command: status
    parser_status = subparsers.add_parser("status", help='A quick health check of the Cloudflare outbox (is it empty or backed up?).')
    parser_status.set_defaults(func=cmd_status)

    # Command: remove
    parser_remove = subparsers.add_parser("remove", help="Easily delete a monitor if you've retired a script and don't want it to trigger an alert.")
    parser_remove.add_argument("id", help="The unique ID of the monitor")
    parser_remove.set_defaults(func=cmd_remove)

    # Command: pause
    parser_pause = subparsers.add_parser("pause", help="Temporarily extend a timeout if you know a specific server will be down for maintenance.")
    parser_pause.add_argument("id", help="The unique ID of the monitor")
    parser_pause.add_argument("hours", type=int, help="Hours to pause")
    parser_pause.set_defaults(func=cmd_pause)

    # Command: test-alert
    parser_test = subparsers.add_parser("test-alert", help="Injects a test monitor that will instantly trigger an alert at the top of the hour.")
    parser_test.set_defaults(func=cmd_test_alert)

    # Command: log
    parser_log = subparsers.add_parser("log", help="Tail the last 10 entries of your local email_log.")
    parser_log.set_defaults(func=cmd_log)

    # Command: deploy
    parser_deploy = subparsers.add_parser("deploy", help='Pushes code updates to Cloudflare. Use this after editing src/index.js.')
    parser_deploy.set_defaults(func=cmd_deploy)

    # If no arguments are provided, show the help screen
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(1)

    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
