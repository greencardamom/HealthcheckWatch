
# HealthcheckWatch

HealthcheckWatch is a "Dead Man's Switch" designed to monitor cron jobs, daemons running, routers pingable, server ports, etc... 
If your scripts silently hang, crash, or fail to run, HealthcheckWatch ensures you get an email before the silence becomes a 
problem.

It operates similarly to `healthchecks.io` and similar services, but it runs on **your own Cloudflare account** which 
provides numerous advantages.


## Why HealthcheckWatch?

While there are many "Dead Man's Switch" services and applications available, HealthcheckWatch is built specifically for 
users who want **total control**, **zero recurring costs**, and a **Unix-native** workflow.

### 1. Zero Infrastructure Costs

Most health check services charge $5–$20/month for advanced features.

* **The Competition**: Paid tiers for more than 10-20 checks.
* **HealthcheckWatch**: Runs entirely on the **Cloudflare Free Tier**. You can have tens of thousands of monitors and pings per month without ever seeing a bill.

### 2. Privacy & Data Ownership

Commercial services may store your server names, IP addresses, and uptime history on their databases which is a security problem.
* **The Competition**: Your infrastructure metadata is stored on their servers.
* **HealthcheckWatch**: You own the database. It lives in your Cloudflare account, and the alerts are processed on your machine. No third party ever sees your script names or server architecture.

### 3. Deployment

Because it uses a Serverless + SQLite (D1) architecture, there is no ping-receiving server to maintain, patch, or secure. 
The "server" is a 100-line JavaScript file hosted globally on CloudFlare's edge network for maximum reliability and 
performance.

This system is designed to be operated from the CLI so you never need to log into the CloudFlare website, other than setup.

### 4. Flexible & Resilient Alerting

When a failure occurs, Cloudflare logs the event to your D1 database (CloudFlare's SQL DB). The included `emailcheck.py` program pulls that data on a set period basis and sends the alert to you, just like a POP3 client retrieving a mailbox.

* **The Simple Setup**: For most users, running a single instance of `emailcheck.py` on your home server or desktop is "good enough." It takes seconds to set up and provides robust monitoring for your local applications.
* **The High-Availability Option**: If you are monitoring mission-critical services, you have the option to run `emailcheck.py` on multiple machines in multiple locations remotely from what you are monitoring. This way `emailcheck.py` itself is not impacted by an outage.
* **Smart Queueing**: Because the email polling is destructive ("remove from server on pickup"), multiple pollers naturally act as a failover team. If one copy of `emailcheck.py` fails, another once can still work to send the email. You get the reliability of an enterprise monitoring mesh without any of the configuration headaches.

### 5. Separation of Concerns

By separating the **Database** from the **Emailer**, you aren't reliant on Cloudflare's internal mailing 
limitations. Your system is responsible for the final alert, allowing you to use any SMTP provider or even modify the script 
to failover between multiple relays.

## User Guide

### 1. Simple Heartbeat

The easiest way to use HealthcheckWatch is to add a single curl command to the end of your existing scripts.

```bash
# Alert if not seen within 2 hours
curl -s "https://healthcheckwatch.your-subdomain.workers.dev/ping/my-script?t=2&token=API_TOKEN" > /dev/null

# Alert if not seen within a month (744 hours)
curl -s "https://healthcheckwatch.your-subdomain.workers.dev/ping/monthly-job?t=744&token=API_TOKEN" > /dev/null
```

* **How it works**: If Cloudflare doesn't see a ping within the time period, it triggers an email alert.

### 2. Customized Messages

If you want a custom email subject and message, include a JSON payload.

```bash
# Ping with a 5-hour timeout and custom alert text
curl -s -X POST "https://healthcheckwatch.your-subdomain.workers.dev/ping/network-check" \
     -H "Authorization: Bearer API_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "timeout": 5,
       "subject": "ALERT: Network Failed on Server-01",
       "body": "The server failed to check in. Check logs at /var/log/sync.log."
     }' > /dev/null
```

### 3. Integration in Python

If you are monitoring a Python application, use the `requests` library to send heartbeats.

```python
import requests

def ping_watchdog():
    url = "https://healthcheckwatch.your-subdomain.workers.dev/ping/python-app"
    headers = {
        "Authorization": "Bearer API_TOKEN",
        "Content-Type": "application/json"
    }
    data = {
        "timeout": 24,
        "subject": "Python App Offline",
        "body": "The analytics engine has stopped responding."
    }
    try:
        requests.post(url, json=data, headers=headers)
    except Exception as e:
        print(f"Failed to ping watchdog: {e}")

# Call this at the end of your main execution loop
ping_watchdog()
```

### Monitoring Strategies 

* **Success Pings**: Place the ping at the very end of your script. This proves the script actually finished successfully.
* **Failure Pings**: (Optional) You can also place a ping inside an error handler (trap in Bash or except in Python) with a timeout: 0 or a very short window to trigger an immediate alert if you know for a fact the script just crashed.
* **Unique IDs**: Ensure every script has a unique ID in the URL (e.g., `/ping/machine-name-script-name`) so you know exactly which one died.

## Setup Basics (A)

### Phase 1: Download Program & Prerequisites 

* **Step A1A**: Clone the repo:
  * `git clone https://github.com/greencardamom/HealthcheckWatch.git`
  * `cd HealthcheckWatch`
* **Step A1B**: Install Node.js
  * *Cloudflare's command-line tools require Node.js to run on your local computer.*
  * If you already have Node installed: You can skip this.
  * If you do not: Go to nodejs.org and download the LTS (Long Term Support) installer for your operating system. Run it and accept the default settings.
* **Step A1C**: Install Node dependencies 
  * `npm install` *(This reads the included `package.json` file and automatically installs the required Cloudflare Worker packages)*
* **Step A1D**: Install Python dependencies
  * `pip install requests`

## Setup and Deploy Cloudflare (B)

### Phase 1: Account Setup & Prerequisites

This phase ensures you have the necessary CloudFlare account and local software.

* **Step B1A**: The Cloudflare Account (Branching Path)
  * If you already have an account: You are golden. Ignore the rest of this section and proceed to Phase 2.
* **Step B1B**: The Cloudflare Account
  * **Sign Up**: Go to `dash.cloudflare.com/sign-up`
  * **Verify**: Check your email immediately for a verification link. You must click this or your deployments will fail later.
  * **No Credit Card Needed**: Cloudflare will offer "Paid" tiers ($5/mo). Ignore them. The "Free" tier is all you need for HealthcheckWatch.
  * **No Domain Needed**: If the dashboard asks you to "Add a Site" or "Register a Domain," you can skip it. We are using a free workers.dev address provided by Cloudflare.

* **Step B1C**: The `workers.dev` Subdomain
  * All your scripts will send their pings to this unique name. Keep it short if you want shorter URLs but it needs be unique to CloudFlare globally.
    * **Navigate**: On the left-hand sidebar of your dashboard, click `Workers & Pages`.
    * **Initialize**: If this is a brand new account, you will see a "Create application" button or a prompt to "Set up a subdomain."
    * **Choose Your Name**: Enter a unique name
      * *Note: This name will appear in your ping URLs like: `https://hcw.uniquename.workers.dev`*
    * **Confirm**: Click **Set up** and then **Continue**.

### Phase 2: CLI Tooling & Authentication

Wrangler is Cloudflare's official command line tool. Step A1C installed a local copy for this project. You need to now connect it to your account.

* **Step B2A**: Authenticate Wrangler
  * Open your local terminal, ensure you are still inside the `HealthcheckWatch` directory, and run:
    * bash: `CLOUDFLARE_API_TOKEN="" CLOUDFLARE_API_KEY="" npx wrangler login`
  * This will automatically open your web browser. Click *Allow* to grant Wrangler permission to manage your account. You can close the browser window once the terminal says "Successfully logged in."

### Phase 3: Database Provisioning & Binding

We need to create the D1 SQL database in the cloud and tell your local project how to communicate with it.

* **Step B3A**: Create the D1 Database
  * Verify you are still inside the `HealthcheckWatch` directory in your terminal. Run this command to provision the database on Cloudflare's servers:
    * `npx wrangler d1 create healthcheckwatch-db`
    *(Note: if you use a different database name then `healthcheckwatch-db` also update `wrangler.jsonc`)*
* **Step B3B**: Copy the Binding Configuration
  * After B3A finishes, the terminal will output a block of text containing your `database_id`. Copy paste the `database_id` into the file `wrangler.jsonc` located in your project folder.

### Phase 4: Database Schema Creation

We will now create the actual tables inside your database using a local SQL file.

* **Step B4A**: Create the SQL File
  * Verify your `HealthcheckWatch` project folder contains a file named `schema.sql`.
* **Step B4B**: Execute the SQL File Remotely
  * Push this structure to your live Cloudflare database by running:
    * `npx wrangler d1 execute healthcheckwatch-db --remote --file=./schema.sql`

### Phase 5: Securing API and Deployment

We need to lock down the API so random internet bots cannot write to your database.

* **Step B5A**: Generate a Secret Token
  * Use a password manager to generate a long, random string (e.g., Tr8x$Pq2!vN9mK#jL5wZ@c1XbY). Copy it to your clipboard.
* **Step B5B**: Upload the Secret to Cloudflare
  * Run this command:
    * `npx wrangler secret put API_TOKEN`
  * The terminal will prompt you to enter the secret. Paste the string you generated in **Step B5A** and press Enter. This stores the secret securely with Cloudflare.
* **Step B5C**: Deploy the Worker
  * Finally, push the application to Cloudflare's global network:
    * `npx wrangler deploy`
  * The terminal will output the live URL of your new HealthcheckWatch API!

### Phase 6: Test
  
* **Step B6A**: Simple test
  * Run a test
    * `curl -X POST "https://healthcheckwatch.yourhostname.workers.dev/ping/test-monitor" -H "Authorization: Bearer API_TOKEN"`
    * *`yourhostname` was printed during B5C. `API_TOKEN` was created in B5B.*
  * **If it returns `[DONE] Heartbeat logged for monitor: test-monitor`, you have successfully built a serverless CloudFlare system.**
* **Step B6B**: Fake an alert
  * Inject a fake alert into the CloudFlare database
    * `npx wrangler d1 execute healthcheckwatch-db --remote --command="INSERT INTO outbox (subject, body) VALUES ('Test Watchdog Alert', 'This is a live test of the HealthcheckWatch email delivery system.');"`
  * Pull the alert and send an email:
    * `./emailcheck.py`
  * You should receive an email with the alert. If not double check your `config.ini` SMTP settings are working.

## Final Setup (C)

### Phase 1: config.ini

The `config.ini` is the main configuration file for HealthcheckWatch. It contains "secrets": keep the file permission 600.

* **Step C1A**: Clone the sample file
  * `cp config.ini.example config.ini`
* **Step C1B**: Open the file and fill in details
  * **api_url**: The full URL provided when you run `npx wrangler deploy` (see **B5C**). Do not include a trailing slash.
  * **api_token**: The exact secret string you generated and uploaded to Cloudflare via `npx wrangler secret put API_TOKEN` (see **B5B**).
  * **squelch**: Set to `no` by default. If you change this to `yes`, the script will still fetch and clear alerts from Cloudflare, and write them to your `logs/email_log`, but it will not send emails. This is useful for planned downtime.
  * **SMTP host**: Your email provider's SMTP server (e.g., `smtp.gmail.com`, `mail.yourdomain.net`).
  * **SMTP port**: Usually `465` for SSL or `587` for STARTTLS.
  * **SMTP user**: Your full email address.
  * **SMTP pass**: Your email account password.
  * **SMTP use_ssl**: Set to `yes` if using port 465 (Implicit SSL). Set to no if using port `587` (STARTTLS).

### Phase 2: Automation
To make the system fully automated, you need to tell your server to run `emailcheck.py` on a regular schedule to fetch pending alerts from Cloudflare.

* **Step C2A**: Add the Python shebang
  * Open `emailcheck.py` and ensure the very first line points to the Python binary inside your new virtual environment. 
  * Example: `#!/home/youruser/HealthcheckWatch/healthcheckwatch_env/bin/python`
* **Step C2B**: Open your crontab editor
  * Run `crontab -e` in your terminal.
* **Step C2C**: Add the polling interval
  * Add a line to run the script every 15 minutes.
  * Example every 15 minutes:
    ```cron
    */15 * * * * /path/to/your/HealthcheckWatch/emailcheck.py
    ```
  * *Note: During an outage you will receive **one** alert it won't keep sending emails.*

### Phase 3: manage.py

Use the included `manage.py` to manage your monitors.

* `./manage.py list`: See active monitors and their "Expected Death" times.
* `./manage.py status`: Check if the Cloudflare outbox is healthy or backed up.
* `./manage.py remove <id>`: Retire a monitor.
* `./manage.py pause <id> <hours>`: Temporarily extend a timeout for maintenance.

## License

HealthcheckWatch is open-source software licensed under the [GNU AGPLv3](LICENSE).
