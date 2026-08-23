<div align="center">

# 💰 MyMonee

**Local-First, Privacy-First Personal Finance Intelligence for macOS**

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18-61DAFB.svg)](https://reactjs.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.0+-3178C6.svg)](https://www.typescriptlang.org/)
[![SQLite](https://img.shields.io/badge/SQLite-Durable%20Ledger-003B57.svg)](https://www.sqlite.org/)
[![Playwright](https://img.shields.io/badge/Playwright-Visual%20Audit-45ba4b.svg)](https://playwright.dev/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

*Turn chaotic financial notification emails and encrypted PDF statements into a clean, normalized, double-entry ledger — with zero cloud lock-in and zero data tracking.*

</div>

---

## 📖 Overview

**MyMonee** is a privacy-first, automated personal expense tracker designed specifically for macOS. It bridges the gap between raw bank notification emails, monthly credit card statements, and actionable personal finance analytics.

```text
Gmail Alerts & PDF Statements
             │
             ▼
 ┌───────────────────────┐
 │   Local Ingestion     │ ──► macOS Keychain (OAuth & Password Encryption)
 └───────────┬───────────┘
             │
             ▼
 ┌───────────────────────┐
 │ Parsing & Extraction  │ ──► Axis Bank, Scapia, PhonePe, Statement Vault
 └───────────┬───────────┘
             │
             ▼
 ┌───────────────────────┐
 │ 12-Digit RRN Matching │ ──► UPI Reconciliation & Duplicate Suppression
 └───────────┬───────────┘
             │
             ▼
 ┌───────────────────────┐
 │ Canonical Ledger      │ ──► Double-Entry Postings & Normal Balance Tracking
 └───────────┬───────────┘
             │
             ▼
 ┌───────────────────────┐
 │  FastAPI + React UI   │ ──► Responsive Dashboard & iOS Safari Gmail Deep Linking
 └───────────────────────┘
```

---

## ✨ Key Features

### 🔒 1. Local-First & Zero Cloud Dependency
* **100% On-Device**: All transaction data, parsed emails, and PDF statements live strictly in a local SQLite ledger (`~/Library/Application Support/ExpenseTracker/expense_tracker.db`).
* **macOS Keychain Security**: Gmail OAuth refresh tokens and statement PDF passwords (AES-256 GCM) are secured in the native macOS Keychain.
* **External AI Off by Default**: External AI suggestions (Google Gemini) are strictly opt-in, disabled by default, and never receive raw email HTML, passwords, or account identifiers.

### 📬 2. Intelligent Notification Email Ingestion
* **Incremental & Idempotent**: Uses Gmail API with read-only scopes (`gmail.readonly`) to stream alerts in real-time.
* **Built-in Parser Registry**:
  * **Axis Bank Alerts**: Parses UPI narrations, 12-digit RRNs, debit/credit swipes, and automated salary credits (`/Sala` pay-period attribution).
  * **Federal Bank / Scapia**: Real-time card swipes, fuel surcharge waivers, and international transactions.
  * **PhonePe Receipt Parser**: Extracts clean merchant names, utility providers (Gas, DTH, Mobile), Fastag tolls, and E-Challans while ignoring non-transactional AutoPay reminders.
  * **Cross-Source Gateway Deduplication**: Prevents double-counting between payment gateway receipts (Razorpay, PhonePe) and bank debit alerts.

### 📄 3. Statement Vault & 12-Digit UPI Reconciliation
* **Encrypted PDF Statement Processing**: Automatically unlocks password-protected PDF statements using locally stored password profiles.
* **Mathematical Balance Validation**: Validates `Opening Balance + Debits - Credits = Total Due`.
* **Deterministic 12-Digit UPI RRN Matching**: Reconciles individual email alerts with monthly bank statement line items with 100% confidence.
* **EMI Auto-Grouping**: Detects principal, interest, and GST components of installment loans.

### 💳 4. Double-Entry Canonical Ledger Engine
* **Formal Accounting Postings**: Enforces double-entry normal balance semantics (Assets: Debit normal; Liabilities: Credit normal).
* **Opening Balance Baselines**: Seamlessly integrates account baselines with transactional inflows and outflows for true net worth calculation.
* **Source Evidence Immutability**: Raw ingestion payloads and audit logs remain tamper-proof while downstream interpretations are updated.

### 📱 5. Responsive React Dashboard & Complete Tooling Suite
* **Overview & Analytics**: MoM Income Trends, Category Breakdown bars, spend distributions, and pay-period salary attribution.
* **Transactions & Needs Review**: Progressive inline category picker, quick-classification modals, and raw source email viewer.
* **Accounts Management**: Comprehensive Asset & Liability registers, compact Add/Edit modal dialogs, and mobile bottom sheet forms.
* **Paginated Merchants Directory**: Configurable page sizes (25, 50, 100, 250), 30-day velocity metrics, and alias management.
* **Recurring Commitments & Bills**: Tracks fixed subscriptions (broadband, loans) and variable recurring bills (maintenance, utilities) with projected commitment KPIs.
* **Data Issues Diagnostics**: Audit false-positive extractions, bulk resolve non-transactions, and refine parser discovery rules.
* **Mobile iOS Deep Linking**: Universal link handler allows you to tap any transaction to open the original message directly in the native **Gmail iOS app**.

---

## 🚀 Quick Start

### Prerequisites
* **macOS** (Apple Silicon or Intel)
* **Python 3.12+**
* **Node.js 20+** (for frontend build)
* **Google Cloud OAuth Client** (for Gmail synchronization)

---

### Installation & Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/gauravssingh/my-monee.git
   cd my-monee
   ```

2. **Set up Python Virtual Environment**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]"
   ```

3. **Build the Frontend**:
   ```bash
   cd web
   npm install
   npm run build
   cd ..
   ```

4. **Run the Application**:
   ```bash
   python -m expense_tracker
   ```
   Open **`http://localhost:8477`** in your browser.

---

## 🔗 Connecting Gmail (Optional)

1. Go to the [Google Cloud Console](https://console.cloud.google.com/) and create a project.
2. Enable the **Gmail API**.
3. Create an **OAuth 2.0 Client ID** (Application type: **Web application**).
   * **Authorized redirect URIs**: `http://localhost:8477/oauth/callback` and `http://127.0.0.1:8477/oauth/callback`
4. Download the client JSON credentials.
5. In **MyMonee UI**, navigate to **Settings** → **Connect Gmail** and upload or paste the credentials.

---

## ⚙️ Running as a macOS Background Service (launchd)

To keep MyMonee continuously running 24/7 on a Mac mini or MacBook:

1. **Create the LaunchAgent plist**:
   ```bash
   mkdir -p ~/Library/LaunchAgents
   cp scripts/launchd/com.personal.expense-tracker.plist.example ~/Library/LaunchAgents/com.personal.expense-tracker.plist
   ```

2. **Edit paths in the plist** to match your local installation directory and user profile.

3. **Load and start the service**:
   ```bash
   launchctl load -w ~/Library/LaunchAgents/com.personal.expense-tracker.plist
   ```

4. **Restart daemon anytime**:
   ```bash
   launchctl kickstart -k "gui/$(id -u)/com.personal.expense-tracker"
   ```

---

## 🧪 Testing & Verification

### Backend Unit & Domain Invariant Tests
Run the full automated test suite (domain invariants, statement parsers, reconciliation engine):
```bash
source .venv/bin/activate
pytest
```

### Playwright Frontend Visual Audit
Execute multi-viewport UI verification tests (desktop & mobile) across all application views:
```bash
source .venv/bin/activate
python .agents/skills/playwright-frontend-testing/scripts/ui_test_runner.py --all
```

---

## 📁 Repository Structure

```text
├── config/                  # Global discovery heuristics & provider rules
├── scripts/                 # Maintenance tools & launchd service definitions
├── src/expense_tracker/
│   ├── api/                 # FastAPI REST API endpoints & routes
│   ├── classification/      # Deterministic taxonomy & merchant rules
│   ├── db/                  # SQLite models, schemas, and migrations
│   ├── domain/              # Enums, invariants, and financial models
│   ├── ingestion/           # Gmail client, OAuth handler, and sync pipeline
│   ├── merchants/           # Merchant normalization & alias registry
│   ├── parsers/             # Bank, card, and PhonePe parser plugins
│   ├── services/            # Ledger postings, balance math, accounts, data issues
│   └── statements/          # PDF OCR, statement vault, and reconciliation
├── tests/                   # Pytest test suite (110+ tests)
└── web/                     # React 18 + Vite + TypeScript dashboard UI
    ├── src/components/      # Modals, badges, segmented controls, email viewer
    ├── src/pages/           # Overview, Transactions, Accounts, Merchants, etc.
    └── src/styles.css       # Unified design system & responsive layout styles
```

---

## 🛡️ Privacy & Security Principles

* **No Telemetry**: Zero analytics, trackers, or phone-home pings.
* **Granular OAuth Scopes**: Only `https://www.googleapis.com/auth/gmail.readonly` is ever requested.
* **Encrypted Secrets**: Sensitive tokens are held strictly in the macOS Keychain (`ExpenseTracker`).
* **Auditability**: Every classified transaction, ledger posting, and duplicate resolution maintains an explicit reasoning trail.

---

## 📄 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.
