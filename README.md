<div align="center">

# 💰 MyMonee

**Local-First, Privacy-First Personal Finance Intelligence & Double-Entry Ledger**

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18-61DAFB.svg)](https://reactjs.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.0+-3178C6.svg)](https://www.typescriptlang.org/)
[![SQLite](https://img.shields.io/badge/SQLite-WAL%20Durable%20Ledger-003B57.svg)](https://www.sqlite.org/)
[![Docker](https://img.shields.io/badge/Docker-Single%20Container-2496ED.svg)](https://www.docker.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

*Turn chaotic financial notification emails and encrypted PDF statements into a clean, normalized, double-entry ledger — with zero cloud lock-in and zero data tracking.*

</div>

---

## 📖 Overview

**MyMonee** is a privacy-first, automated personal expense tracker and double-entry financial ledger. It runs as **one core engine across multiple deployment shells** — native macOS (launchd background daemon), lightweight Docker container (NAS, Raspberry Pi, home server), or a standalone headless CLI.

```text
                     EXTERNAL FINANCIAL EVIDENCE
                                  │
                  ┌───────────────┴───────────────┐
                  ▼                               ▼
         Gmail Ingestion Engine         PDF/CSV Statement Vault
         (Real-time push alerts)       (Encrypted monthly bills)
                  │                               │
                  └───────────────┬───────────────┘
                                  ▼
                    Discovery & Extraction Layer
               (Axis Bank, Scapia, PhonePe, UPI 12-digit RRNs)
                                  │
                                  ▼
                   Reconciliation & Matching Engine
             (Refund Pairing · Transfer Linking · Deduplication)
                                  │
                                  ▼
                  Canonical Double-Entry SQLite Ledger
                  (WAL Mode · Deterministic Rule Engine)
                                  │
          ┌───────────────────────┼───────────────────────┐
          ▼                       ▼                       ▼
    Web Dashboard            Unified CLI            .MMB Archive
 (FastAPI + React 18)   (mymonee doctor/status)  (Portable Disaster Backup)
```

---

## ✨ Key Features

### 🔒 1. Local-First & Zero Cloud Dependency
* **100% On-Device**: All transaction data, parsed emails, and PDF statements live strictly in your durable local SQLite ledger.
* **Portable Secret Management**: Uses native macOS Keychain when running on Darwin, with automatic secure local fallback (`chmod 0o600`) when running in Docker or Linux.
* **External AI Off by Default**: External AI suggestions (Google Gemini) are strictly opt-in, disabled by default, and never receive raw email HTML, passwords, or account identifiers.

### 📬 2. Intelligent Notification Email Ingestion
* **Incremental & Idempotent**: Uses the Gmail API with read-only scopes (`gmail.readonly`) to stream alerts in real-time.
* **Built-in Parser Registry**:
  * **Axis Bank Alerts**: Parses UPI narrations, 12-digit RRNs, debit/credit swipes, and automated salary credits (`/Sala` pay-period attribution).
  * **Federal Bank / Scapia**: Real-time card swipes, fuel surcharge waivers, and international transactions.
  * **PhonePe Receipt Parser**: Extracts clean merchant names, utility providers (Gas, DTH, Mobile), Fastag tolls, and E-Challans while ignoring non-transactional AutoPay reminders.
  * **Fuzzy Deduplication Engine**: Cross-provider matching detecting when both a Bank debit email and a UPI receipt arrive for the same event ($\pm 120$ seconds).

### 📄 3. Statement Vault & Dual-Source Reconciliation
* **Encrypted PDF Statement Processing**: Automatically unlocks password-protected bank & card PDFs using encrypted password profiles.
* **Mathematical Balance Validation**: Validates `Opening Balance + Debits - Credits = Total Due`.
* **Deterministic 12-Digit UPI RRN Matching**: Reconciles individual email alerts with monthly bank statement line items with 100% confidence.
* **Cross-Account Transfer & Refund Pairing**: Automatically links credit card bill payments and pairs refund credits to original debit transactions without inflating income.

### 🧙 4. 5-Step Financial Calibration & Onboarding Wizard
* **Interactive Setup Flow**:
  1. **Welcome & Sources**: Detects existing data sources and Gmail connectivity.
  2. **Accounts & Cards Calibration**: Detects bank accounts and credit cards from past alerts.
  3. **Income & Pay-Cycle Configuration**: Customizes salary dates and pay-cycle baselines.
  4. **Fixed Obligations & Subscriptions**: Identifies recurring commitments (Rent, EMIs, Utilities, Subscriptions).
  5. **Ledger Intelligence Launch**: Calibrates the starting net worth and transitions to the dashboard.

### 🚨 5. Spending Surge & Anomaly Detection Signals
* **Subscription Price Surges**: Flags when a recurring subscription (e.g. Netflix, AWS) increases above its baseline.
* **Same-Day Repeated Charges**: Detects accidental multiple card charges to the exact same merchant on the same day.
* **Category Spending Spikes**: Statistical outlier detection flagging expenses $> 4\times$ historical category averages.

### 📦 6. Portable `.mmb v1` Archive & Disaster Recovery
* **Complete Recovery Artifact**: Packages SQLite snapshot, raw PDF statements, attachments, checksums, and manifest into a single `.mmb` archive.
* **Transactional Restore**: Before restoring, the engine automatically creates a pre-restore safety snapshot so data is never destroyed on failure.
* **Database Health & Optimization**: One-click `PRAGMA integrity_check`, `foreign_key_check`, WAL checkpointing, and `VACUUM`.

---

## 💻 Unified Command-Line Interface (`mymonee`)

MyMonee includes a full headless CLI that executes directly against the local SQLite database without requiring the HTTP server to be running:

```bash
# 1. Operational State Overview
$ mymonee status
MyMonee v0.8.0

  Database        ✓ Healthy
  Gmail           ✓ Connected
  Last Sync       12 minutes ago
  Transactions    1,485
  Needs Review    14
  Statements      228
  Last Backup     today at 16:42 (Verified ✓)

# 2. Deep System & Storage Diagnostics
$ mymonee doctor
MyMonee Doctor
────────────────────────────────────────────
Application
  ✓ Version: MyMonee v0.8.0 (Schema: 2026_08_ledger_v2, Archive: v1)
Database
  ✓ SQLite Accessible: Found at /data/db/expense_tracker.db
  ✓ WAL Journal Mode: WAL enabled
  ✓ Integrity Check: PRAGMA integrity_check passed
Storage
  ✓ Data Directory Writable: /data
  ✓ Statements Storage: 331 files
Backup
  ✓ Archive Status: 3 archives (Latest: mymonee_20260823_164218.mmb)

Result: HEALTHY

# 3. Create & Verify .mmb Backup Archives
$ mymonee backup create --note "Pre-upgrade snapshot"
$ mymonee backup verify mymonee_20260823_164218.mmb
✓ Archive verification PASSED (1,300 files, 1,485 transactions)

# 4. Safe Disaster Recovery
$ mymonee backup restore mymonee_20260823_164218.mmb

# 5. Database Maintenance & Reconciliation
$ mymonee db integrity
$ mymonee db vacuum
$ mymonee reconcile
$ mymonee data export --output ledger_export.json
```

---

## 🚀 Deployment Options

### Option A: Native macOS Installation (Recommended for Mac Users)

1. **Clone & Set Up Python Environment**:
   ```bash
   git clone https://github.com/gauravssingh/my-monee.git
   cd my-monee
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]"
   ```

2. **Build the Frontend**:
   ```bash
   cd web
   npm install
   npm run build
   cd ..
   ```

3. **Run Application**:
   ```bash
   python -m expense_tracker
   ```
   Open **`http://localhost:8477`** in your browser.

4. **Keep Running 24/7 with macOS `launchd`**:
   ```bash
   cp scripts/launchd/com.personal.expense-tracker.plist.example ~/Library/LaunchAgents/com.personal.expense-tracker.plist
   launchctl load -w ~/Library/LaunchAgents/com.personal.expense-tracker.plist
   ```

---

### Option B: Docker Compose (NAS / Raspberry Pi / Linux Self-Hosting)

Run MyMonee in a lightweight, single-container non-root setup:

```yaml
# docker-compose.yml
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

Launch:
```bash
docker compose up -d
```

---

## 📁 Filesystem Contract

MyMonee organizes user data into a clean, explicit directory hierarchy:

```text
/data
├── db/                # Primary SQLite database (expense_tracker.db)
├── statements/        # Ingested PDF/CSV bank & card statements
├── evidence/          # Audit receipts & statement crops
├── attachments/       # Raw transaction proof attachments
├── backups/           # .mmb archives and point-in-time snapshots
├── exports/           # Exported JSON/CSV datasets
├── tmp/               # Secure temporary staging directories
└── logs/              # Application runtime log files

/config
├── config.yaml        # Main configuration file
└── providers/         # Provider extraction configurations
```

---

## 🧪 Automated Testing & Quality Standards

* **Comprehensive Test Suite**: **136 passing tests** across domain invariants, accounting math, statement parsers, deduplication, `.mmb` roundtrips, and cross-runtime portability:
  ```bash
  source .venv/bin/activate
  pytest
  ```
* **Container Health Probes**:
  - `GET /health` / `GET /health/live`: Fast liveness check.
  - `GET /health/ready`: Readiness probe verifying SQLite connectivity and schema integrity without leaking sensitive information.

---

## 🛡️ Privacy & Security Principles

* **No Telemetry**: Zero analytics, trackers, or phone-home network calls.
* **Granular OAuth Scopes**: Only `https://www.googleapis.com/auth/gmail.readonly` is requested.
* **Zero Credentials in Backups**: `.mmb` archives strictly contain financial truth and evidence, never reusable tokens or API keys.
* **Full Auditability**: Every classified transaction, ledger posting, and duplicate resolution maintains an explicit reasoning trail.

---

## 📄 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.
