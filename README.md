
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
  * `pip install ...` *(TBD)*

## Setup and Deploy Cloudflare (B)

### Phase 1: Account Setup & Prerequisites

This phase ensures you have the necessary CloudFlare account and local software.

* **Step B1A**: The Cloudflare Account (Branching Path)
  * If you already have an account: You are golden. Log into dash.cloudflare.com. You do not need to create a new account.
  * If you do NOT have an account: Go to dash.cloudflare.com/sign-up. Enter your email, create a password, and verify your email address via the link sent to your inbox. The developer tier is free, has 10GB disk space and unlimited network - more than an enough for this application.
* **Step B1B**: The workers.dev Subdomain (Branching Path)
  * If you already have an account: You will simply reuse this! Your new project will live at `healthcheckwatch.your-subdomain.workers.dev`. *(If you forgot your subdomain, log into the Cloudflare dashboard, click Workers & Pages on the left, and look at the right side of the screen where it says "Your subdomain is...").*
  * If you are a new user: Click **Workers & Pages** on the left sidebar. Cloudflare will force you to choose a free, permanent subdomain. Choose carefully, click **Set up**, and move on.
* **Note**: You do not actually need to memorize your subdomain for this setup. When you deploy the code in Phase 5, the terminal will print your exact, final URL for you.

### Phase 2: CLI Tooling & Authentication

Wrangler is Cloudflare's official command line tool. Step A1C installed a local copy for this project. You need to connect it to your account.

* **Step B2A**: Authenticate Wrangler
  * Open your local terminal, ensure you are still inside the `HealthcheckWatch` directory, and run (bash):
    * `CLOUDFLARE_API_TOKEN="" CLOUDFLARE_API_KEY="" npx wrangler login`
  * This will automatically open your web browser. Click *Allow* to grant Wrangler permission to manage your account. You can close the browser window once the terminal says "Successfully logged in."

### Phase 3: Database Provisioning & Binding

We need to create the D1 SQL database in the cloud and tell your local project how to communicate with it.

* **Step B3A**: Create the D1 Database
  * Verify you are still inside the `HealthcheckWatch` directory in your terminal. Run this command to provision the database on Cloudflare's servers:
    * `npx wrangler d1 create healthcheckwatch-db`
* **Step B3B**: Copy the Binding Configuration
  * After B3A finishes, the terminal will output a block of text containing your `database_id`. Copy pase that into the file `wrangler.jsonc` located in your project folder.

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
* **Step B5D**: Test
  * Run a test
    * `curl -X POST "https://healthcheckwatch.yourhostname.workers.dev/ping/test-monitor" -H "Authorization: Bearer YOUR_TOKEN_HERE"`
    * *(`yourhostname` was printed during B5C)*
  * **If it returns `[DONE] Heartbeat logged for monitor: test-monitor`, you have successfully built a global serverless monitoring system.**
    
## License
HealthcheckWatch is open-source software licensed under the [GNU AGPLv3](LICENSE).
