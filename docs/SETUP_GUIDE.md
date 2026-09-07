# MyMonee — New User Installation & Setup Guide

This guide walks you step-by-step through setting up **MyMonee** on your local machine, configuring Google Cloud OAuth for Gmail financial alert ingestion, and running the application 24/7.

---

## 📋 Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Quick Start (Local macOS / Linux)](#2-quick-start-local-macos--linux)
3. [Google Cloud OAuth Configuration](#3-google-cloud-oauth-configuration)
4. [First Launch & Onboarding Calibration](#4-first-launch--onboarding-calibration)
5. [Testing Without Gmail (Demo Mode)](#5-testing-without-gmail-demo-mode)
6. [macOS 24/7 Background Service (launchd)](#6-macos-247-background-service-launchd)
7. [Docker Deployment (NAS / Linux / Raspberry Pi)](#7-docker-deployment-nas--linux--raspberry-pi)
8. [CLI Diagnostics & Maintenance](#8-cli-diagnostics--maintenance)
9. [Troubleshooting & FAQs](#9-troubleshooting--faqs)

---

## 1. Prerequisites

Before installing, ensure your system has the following tools installed:

| Tool | Required Version | Verification Command |
| :--- | :--- | :--- |
| **Python** | 3.12 or newer | `python3 --version` |
| **Node.js** | 20.x or newer | `node --version` |
| **npm** | 9.x or newer | `npm --version` |
| **Git** | Any modern version | `git --version` |
| **Operating System** | macOS 13+ (Ventura+) or Linux | `uname -s` |

> [!NOTE]
> For macOS, we recommend installing Python and Node via [Homebrew](https://brew.sh):
> ```bash
> brew install python@3.12 node
> ```

---

## 2. Quick Start (Local macOS / Linux)

### Step 1: Clone the Repository

```bash
git clone https://github.com/gauravssingh/my-monee.git
cd my-monee
```

### Step 2: Set Up Python Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
```

### Step 3: Build the Web Dashboard

The frontend is a React + TypeScript SPA built with Vite. FastAPI serves the compiled bundle directly from `web/dist`:

```bash
cd web
npm install
npm run build
cd ..
```

### Step 4: Run the Application

```bash
# Ensure virtualenv is active
source .venv/bin/activate

# Start the server (API + Web UI)
python -m mymonee
```

The application is now running at **`http://127.0.0.1:8477`**.

---

## 3. Google Cloud OAuth Configuration

To automatically ingest financial notification emails (bank debit/credit alerts, UPI notifications, bill payments), MyMonee uses the **read-only** Gmail API (`gmail.readonly`).

Follow these steps in Google Cloud Console:

### 3.1. Create a Google Cloud Project
1. Navigate to the [Google Cloud Console](https://console.cloud.google.com/).
2. Click the project dropdown in the top-left corner and click **New Project**.
3. Name your project (e.g. `MyMonee-Local`) and click **Create**.

### 3.2. Enable the Gmail API
1. In the search bar at the top, search for **Gmail API**.
2. Select **Gmail API** from the results and click **Enable**.

### 3.3. Configure the OAuth Consent Screen
1. In the left navigation sidebar, go to **APIs & Services** → **OAuth consent screen**.
2. Choose **User Type**: **External**, then click **Create**.
3. Fill in the required fields:
   * **App name**: `MyMonee`
   * **User support email**: Your Gmail address
   * **Developer contact email**: Your Gmail address
4. Click **Save and Continue**.
5. **Scopes**:
   * Click **Add or Remove Scopes**.
   * Search for or add `https://www.googleapis.com/auth/gmail.readonly`.
   * Click **Update** and **Save and Continue**.
6. **Test Users**:
   * Click **Add Users**.
   * Enter the exact Gmail address you want MyMonee to sync financial alerts from.
   * Click **Save and Continue**.

### 3.4. Create OAuth 2.0 Client Credentials
1. In the left navigation sidebar, go to **APIs & Services** → **Credentials**.
2. Click **+ Create Credentials** at the top → select **OAuth client ID**.
3. Choose **Application type**:
   * **Web application** (Recommended)
4. Name: `MyMonee Desktop Client`
5. Under **Authorized redirect URIs**, click **+ Add URI** and add:
   ```text
   http://127.0.0.1:8477/oauth/callback
   ```
6. Click **Create**.
7. In the confirmation dialog, click **Download JSON**.

### 3.5. Install the Credentials in MyMonee

You have two easy ways to install your credentials:

* **Method A (Via Web UI - Recommended)**:
  1. Open `http://127.0.0.1:8477` in your browser.
  2. Navigate to **Settings** → **Gmail Connection**.
  3. Click **Import Credentials** and select your downloaded JSON file.
* **Method B (File Placement)**:
  Rename the downloaded file to `gmail_credentials.json` and save it to the default directory:
  * **macOS**: `~/Library/Application Support/ExpenseTracker/gmail_credentials.json` (or `~/Library/Application Support/MyMonee/gmail_credentials.json`)
  * **Linux / Docker**: `<data_dir>/gmail_credentials.json`

---

## 4. First Launch & Onboarding Calibration

When you open `http://127.0.0.1:8477` for the first time, MyMonee guides you through a 5-step calibration wizard:

1. **Protection & Privacy**: Configure an optional local dashboard PIN/passcode or keep local access open.
2. **Region & Currency**: Select your primary operating currency (e.g. `INR (₹)`, `USD ($)`, `EUR (€)`) and number formatting (e.g. Lakhs/Crores vs Millions).
3. **Connect Gmail**: 
   * Click **Connect Gmail**.
   * A Google authorization window will open. If you see *"Google hasn’t verified this app"*, click **Advanced** → **Go to MyMonee (unsafe)** (this warning is normal for personal Developer projects).
   * Grant read-only access.
   * Google redirects back to `http://127.0.0.1:8477/oauth/callback`. Refresh tokens are securely stored in your **macOS Keychain** (or encrypted token storage on Linux).
4. **Discover Financial Sources**:
   * MyMonee scans your recent emails to detect bank accounts, credit cards, and UPI apps (e.g. Axis Bank, HDFC, Scapia, Federal Bank, PhonePe).
   * Confirm which accounts and cards belong to you and set optional opening balances.
5. **Income & Obligations Calibration**:
   * Calibrate your monthly salary attribution rules (e.g. Axis `/Sala` salary alerts post-day 2 belong to the upcoming month's pay period).
   * Confirm fixed monthly obligations (Rent, EMIs, Utilities, Subscriptions).

Once finished, you land on the live **Dashboard**!

---

## 5. Testing Without Gmail (Demo Mode)

If you prefer to test all features, visualizations, and parsers before linking Google Cloud:

1. Open `http://127.0.0.1:8477`.
2. Go to **Settings** → **Diagnostics & Demo Data**.
3. Click **"Run demo emails"**.
4. MyMonee seeds representative mock financial notifications (bank debits, credits, transfers, refunds, subscriptions) directly into the SQLite ledger.

---

## 6. macOS 24/7 Background Service (launchd)

To keep MyMonee running continuously in the background and start automatically on system boot:

### Step 1: Prepare the launchd Plist

The repository includes a ready-to-use template in `scripts/launchd/com.personal.my-monee.plist.example`:

```bash
# Copy the example plist to your user LaunchAgents directory
cp scripts/launchd/com.personal.my-monee.plist.example ~/Library/LaunchAgents/com.personal.my-monee.plist
```

### Step 2: Edit Paths in the Plist

Open `~/Library/LaunchAgents/com.personal.my-monee.plist` in your text editor and replace `/Users/YOU` with your actual home directory path (e.g. `/Users/yourusername`):

```xml
<key>ProgramArguments</key>
<array>
  <string>/Users/yourusername/projects/my-monee/scripts/run_server.sh</string>
</array>
<key>WorkingDirectory</key>
<string>/Users/yourusername/projects/my-monee</string>
<key>StandardOutPath</key>
<string>/Users/yourusername/Library/Logs/my-monee/stdout.log</string>
<key>StandardErrorPath</key>
<string>/Users/yourusername/Library/Logs/my-monee/stderr.log</string>
```

### Step 3: Load and Start the Daemon

```bash
# Ensure the run script is executable
chmod +x scripts/run_server.sh

# Create the log directory
mkdir -p ~/Library/Logs/my-monee

# Load and launch the agent
launchctl load -w ~/Library/LaunchAgents/com.personal.my-monee.plist
```

### Service Management Commands

```bash
# Restart the daemon
launchctl kickstart -k "gui/$(id -u)/com.personal.my-monee"

# Stop the daemon
launchctl unload ~/Library/LaunchAgents/com.personal.my-monee.plist

# Check logs in real time
tail -f ~/Library/Logs/my-monee/stdout.log ~/Library/Logs/my-monee/stderr.log
```

---

## 7. Docker Deployment (NAS / Linux / Raspberry Pi)

MyMonee is container-ready for non-macOS headless environments (Synology NAS, TrueNAS, Raspberry Pi, Ubuntu Server):

### Step 1: Create Directories and docker-compose.yml

```bash
mkdir -p mymonee/{data,config}
cd mymonee
```

Create `docker-compose.yml`:

```yaml
version: "3.8"

services:
  mymonee:
    image: mymonee:latest
    build: .
    container_name: mymonee
    restart: unless-stopped
    ports:
      - "8477:8477"
    environment:
      MYMONEE_DATA_DIR: /data
      MYMONEE_CONFIG_DIR: /config
      MYMONEE_APP_HOST: "0.0.0.0"
      MYMONEE_APP_PORT: 8477
      MYMONEE_SCHEDULER_ENABLED: "true"
    volumes:
      - ./data:/data
      - ./config:/config:ro
    stop_grace_period: 30s
```

### Step 2: Add Gmail Credentials & Launch

1. Place your `gmail_credentials.json` inside `./data/gmail_credentials.json`.
2. Start the container:
   ```bash
   docker compose up -d
   ```
3. Open `http://<your-nas-or-server-ip>:8477` to complete the initial setup.

---

## 8. CLI Diagnostics & Maintenance

MyMonee includes a built-in CLI that runs directly against your SQLite ledger without needing the web UI:

```bash
source .venv/bin/activate

# 1. Check system and ledger health
mymonee status

# 2. Run deep diagnostics (storage, database integrity, schema)
mymonee doctor

# 3. Create a cryptographic .mmb disaster recovery backup
mymonee backup create --note "Routine snapshot"

# 4. Verify an archive's integrity and checksums
mymonee backup verify /path/to/backup.mmb

# 5. Optimize SQLite database (vacuum & index analyze)
mymonee db vacuum
mymonee db integrity
```

---

## 9. Troubleshooting & FAQs

### Q: Google OAuth displays `redirect_uri_mismatch` (Error 400)
* **Cause**: The redirect URI in Google Cloud Console does not match `http://127.0.0.1:8477/oauth/callback`.
* **Fix**: Go to Google Cloud Console → **APIs & Services** → **Credentials** → click your OAuth 2.0 Client ID. Under **Authorized redirect URIs**, ensure `http://127.0.0.1:8477/oauth/callback` is listed. Note that `localhost` and `127.0.0.1` are treated as different URIs by Google; MyMonee uses `127.0.0.1`.

### Q: "Google hasn't verified this app" screen during OAuth
* **Cause**: Your OAuth app is in "Testing" mode in Google Cloud Console.
* **Fix**: This is expected for personal projects. Click **Advanced** at the bottom left, then click **Go to MyMonee (unsafe)** to grant permissions.

### Q: "Access blocked: This app has not been verified" (Cannot proceed)
* **Cause**: Your Gmail address was not added to the "Test Users" list on the OAuth Consent Screen.
* **Fix**: Go to Google Cloud Console → **OAuth consent screen** → **Test users** → click **+ Add Users** → enter your Gmail address → click **Save**.

### Q: Port 8477 is already in use
* **Fix**: You can change the port by setting an environment variable or editing `config.yaml`:
  ```bash
  export MYMONEE_APP_PORT=8488
  python -m mymonee
  ```
  *(Remember to update the authorized redirect URI in Google Cloud Console to match the new port).*

### Q: Where is my data stored?
* **Database**: `~/Library/Application Support/MyMonee/mymonee.db` (or legacy `ExpenseTracker/expense_tracker.db`)
* **Tokens**: Encrypted in the macOS Keychain (`ExpenseTracker` service)
* **Statements & Evidence**: `~/Library/Application Support/MyMonee/statements/`
