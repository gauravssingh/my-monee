<div align="center">

# 💰 MyMonee

**Local-First, Portable & Self-Hosted Personal Finance Intelligence**

*One unified financial engine. Multiple deployment shells: Native macOS daemon · Headless Docker on NAS / Home Server / Raspberry Pi · Standalone CLI.*

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/Docker-Multi--Platform%20Ready-2496ED.svg)](https://www.docker.com/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18-61DAFB.svg)](https://reactjs.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.0+-3178C6.svg)](https://www.typescriptlang.org/)
[![SQLite](https://img.shields.io/badge/SQLite-WAL%20Durable%20Ledger-003B57.svg)](https://www.sqlite.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

*Turn chaotic financial notification emails and encrypted PDF statements into a clean, normalized, double-entry ledger — with zero cloud lock-in, zero telemetry, and 100% data ownership.*

</div>

---

## 🌐 The Self-Hosted & Portable Vision

Most modern personal finance tools force you into proprietary cloud databases, sell your transaction data to advertisers, or lock you into closed platforms.

**MyMonee is architected differently.** It is built around a single foundational philosophy:

> **"One core application/runtime, multiple deployment shells."**  
> Your financial data belongs exclusively to you in a standard SQLite file and portable `.mmb` disaster recovery archives that you can run on a Mac, migrate to a Home Server / NAS, or host headlessly on a Raspberry Pi without changing code.

```text
                               MyMonee Core Engine
                                        │
             ┌──────────────────────────┼──────────────────────────┐
             ▼                          ▼                          ▼
       macOS Desktop              Linux / Docker              Headless CLI
   (Native launchd Daemon)     (Home Server / NAS / RPi)   (Automated Maintenance)
             │                          │                          │
             └──────────────────────────┼──────────────────────────┘
                                        │
                         Unified Application Services
                                        │
             ┌──────────────────────────┼──────────────────────────┐
             ▼                          ▼                          ▼
      SQLite WAL Ledger        Statement & Evidence Vault      .MMB Archive
    (Canonical Accounting)      (Encrypted PDF/CSV Bills)   (Disaster Portability)
```

---

## 🏛️ Self-Hosted Architecture & Contracts

### 1. 📂 Explicit Filesystem Contract
Whether running on native macOS or inside a Docker volume mount, MyMonee enforces an organized, predictable storage hierarchy:

```text
/data
├── db/                # Durable SQLite database (mymonee.db)
├── statements/        # Ingested & decrypted PDF/CSV bank/card statements
├── evidence/          # Audit receipts, transaction crops, and parsed proof
├── attachments/       # Raw transaction proof attachments
├── backups/           # Point-in-time snapshots and versioned .mmb archives
├── exports/           # Exported JSON/CSV datasets
├── tmp/               # Secure temporary staging directories
└── logs/              # Application runtime log files

/config
├── config.yaml        # Application settings and user preferences
└── providers/         # Provider extraction rules and heuristics
```

### 2. 📦 The `.mmb v1` Portable Recovery Contract
The primary backup format of MyMonee is **not just a database dump or a JSON export**. It is a versioned, verifiable, and cryptographic `.mmb` (tar.gz) archive containing the complete financial truth:

* **`manifest.json`**: Archive metadata, app version (`0.8.0`), schema version (`2026_08_ledger_v2`), and ledger metrics.
* **`database.sqlite`**: Online consistent snapshot taken via SQLite's native backup API.
* **`statements/`**: All raw PDF/CSV statement documents.
* **`checksums.sha256`**: Per-file cryptographic hash manifest.

**Zero Credential Exposure**: `.mmb` archives strictly exclude OAuth refresh tokens, API keys, and passwords. You can safely store `.mmb` files in external cold storage, Synology NAS, Google Drive, or S3.

### 3. 🛡️ Architectural Boundaries (Who Owns What)
* **MyMonee Owns**: Application runtime, double-entry accounting math, SQLite schemas & migrations, parsing heuristics, `.mmb` archive format, and CLI diagnostics.
* **User Owns**: Infrastructure (Mac/NAS/Server), reverse proxy (Caddy/Traefik/Nginx), TLS certificates, secrets/tokens, and backup storage destination.

---

## ✨ Key Features

### 🔒 1. Local-First & Privacy by Design
* **Zero Telemetry**: No tracking, phone-home analytics, or external database calls.
* **Platform-Agnostic Secret Storage**: Uses native macOS Keychain when running on Darwin, with automatic secure owner-restricted file token fallback (`chmod 0o600`) when running on Linux / Docker.
* **External AI Off by Default**: External AI parsing (Google Gemini) is strictly opt-in, disabled by default, and never receives raw email HTML or account numbers.

### 📬 2. Multi-Source Ingestion & Intelligent Parsing
* **Incremental Gmail Stream**: Incremental push synchronization via read-only Gmail API scopes (`gmail.readonly`).
* **Deterministic Parsers**: Specialized parser plugins for Axis Bank, Scapia, Federal Bank, PhonePe, and utility billers.
* **Fuzzy Cross-Provider Deduplication**: Detects near-duplicate transactions when both a payment gateway receipt (e.g. PhonePe) and a bank debit SMS arrive for the same purchase within $\pm 120$ seconds.

### 📄 3. Statement Vault & 12-Digit UPI Reconciliation
* **Encrypted Statement Vault**: Automated decryption of password-protected PDF bank and card statements using local encrypted profile templates.
* **12-Digit UPI RRN Matching**: Reconciles notification alerts against statement billing lines using exact Retrieval Reference Numbers (RRN) with 100% confidence.
* **Transfer & Refund Linking**: Automatically pairs credit card payments and refund credits to original purchases without inflating income.

### 🧙 4. 5-Step Financial Calibration Wizard
* **Interactive Setup Flow**:
  1. **Welcome & Sources**: Detects existing data sources and Gmail connectivity.
  2. **Accounts & Cards Calibration**: Detects bank accounts and credit cards from past alerts.
  3. **Income & Pay-Cycle Configuration**: Customizes salary dates and pay-cycle baselines.
  4. **Fixed Obligations & Subscriptions**: Identifies recurring commitments (Rent, EMIs, Utilities, Subscriptions).
  5. **Ledger Intelligence Launch**: Calibrates the starting net worth and transitions to the dashboard.

### 🚨 5. Spending Signals & Anomaly Detection
* **Subscription Price Surges**: Detects unexpected price hikes on recurring commitments (e.g. Netflix, AWS price increases).
* **Same-Day Double Charges**: Flags accidental multiple card swipes to the same merchant on the same calendar day.
* **Outlier Spikes**: Flags discretionary expenses $> 4\times$ the historical category average.

---

## 💻 Headless Management via CLI (`mymonee`)

The unified `mymonee` CLI executes directly against the local SQLite database without requiring the Web UI or HTTP server to be running:

```bash
# 1. Operational State
$ mymonee status
MyMonee v0.8.0

  Database        ✓ Healthy
  Gmail           ✓ Connected
  Last Sync       12 minutes ago
  Transactions    1,485
  Needs Review    14
  Statements      228
  Last Backup     today at 16:42 (Verified ✓)

# 2. Deep Health Diagnostics (Doctor)
$ mymonee doctor
MyMonee Doctor
────────────────────────────────────────────
Application
  ✓ Version: MyMonee v0.8.0 (Schema: 2026_08_ledger_v2, Archive: v1)
Database
  ✓ SQLite Accessible: Found at /data/db/mymonee.db
  ✓ WAL Journal Mode: WAL enabled
  ✓ Integrity Check: PRAGMA integrity_check passed
Storage
  ✓ Data Directory Writable: /data
  ✓ Statements Storage: 331 files
Backup
  ✓ Archive Status: 3 archives (Latest: mymonee_20260823_164218.mmb)

Result: HEALTHY

# 3. Create & Verify Portable .mmb Archives
$ mymonee backup create --note "Pre-migration snapshot"
$ mymonee backup verify mymonee_20260823_164218.mmb
✓ Archive verification PASSED (1,300 files, 1,485 transactions)

# 4. Safe Disaster Recovery (with pre-restore safety snapshot)
$ mymonee backup restore mymonee_20260823_164218.mmb

# 5. Database Maintenance & Reconciliation
$ mymonee db integrity
$ mymonee db vacuum
$ mymonee reconcile
$ mymonee data export --output ledger_export.json
```

---

## 🚀 Deployment Guides

### Option 1: Docker Compose (Recommended for Self-Hosting & NAS)

Ideal for Synology, TrueNAS, Raspberry Pi, or local Linux home servers:

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

```bash
docker compose up -d
```
Access the dashboard at **`http://<your-server-ip>:8477`**.

---

### Option 2: Native macOS Installation (Daemon via `launchd`)

Ideal for running 24/7 on a Mac mini or MacBook:

1. **Set Up Python Environment**:
   ```bash
   git clone https://github.com/gauravssingh/my-monee.git
   cd my-monee
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]"
   ```

2. **Build Web Frontend**:
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

4. **Background Service (`launchd`)**:
   ```bash
   cp scripts/launchd/com.personal.mymonee.plist.example ~/Library/LaunchAgents/com.personal.mymonee.plist
   launchctl load -w ~/Library/LaunchAgents/com.personal.mymonee.plist
   ```

---

## 🧪 Portability & Quality Verification

* **Cross-Runtime Test Matrix**: Verified roundtrip compatibility across macOS and Linux/Docker environments.
* **136 Automated Tests**:
  ```bash
  source .venv/bin/activate
  pytest
  ```
* **Container Health Probes**:
  - `GET /health` / `GET /health/live`: Fast liveness check.
  - `GET /health/ready`: Readiness probe verifying SQLite connectivity and schema readiness without exposing sensitive user information.

---

## 🛡️ Security Baseline

* **Non-Root Execution**: Container runs strictly under non-root user `mymonee` (UID 1000).
* **Minimal Attack Surface**: Single-container architecture with zero external database dependencies (no Redis, Postgres, or RabbitMQ).
* **Granular OAuth Scopes**: Only `https://www.googleapis.com/auth/gmail.readonly` is ever requested.
* **Audit Trail**: Every classified transaction, ledger posting, and duplicate resolution maintains an explicit reasoning trail.

---

## 📄 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.
