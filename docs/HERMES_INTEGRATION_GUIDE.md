# MyMonee ↔ Hermes Agent: Secure MCP Integration Guide

This guide describes how to connect [Nous Research Hermes Agent](https://hermes-agent.nousresearch.com) to your local MyMonee personal finance ledger using the Model Context Protocol (MCP) over `stdio`.

---

## 1. Architecture & Security Model

The integration is built on one inviolable principle:

> **Hermes gets financial facts and capabilities — not financial storage.**
> **Hermes is an untrusted reasoning client. MyMonee is the authoritative financial system.**

```text
┌──────────────────────────────┐
│        Hermes Agent          │
│                              │
│  Natural-language reasoning  │
│  Tool selection              │
│  Answer composition          │
└──────────────┬───────────────┘
               │
               │ MCP / stdio (JSON-RPC 2.0)
               ▼
┌──────────────────────────────┐
│       MyMonee MCP Server     │
│   (mymonee.mcp.server)       │
│ Protocol                     │
│ Tool registration            │
│ Input validation             │
│ Error boundary               │
│ Concurrency control          │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│     MyMonee Agent Service    │
│   (mymonee.mcp.service)      │
│ Principal / scope            │
│ Authorization                │
│ Resource limits              │
│ Domain orchestration         │
│ Audit logging                │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│       Agent DTO Layer        │
│   (mymonee.mcp.models)       │
│ Explicit allowlisted fields  │
│ Public identifiers (opaque)  │
│ Decimal Money (amount: str)  │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│    Privacy Validation        │
│   (mymonee.mcp.sanitizer)    │
│ Pattern detection            │
│ Canary detection             │
│ Fail-closed enforcement      │
└──────────────┬───────────────┘
               │
               │ Response Path (Safe DTO)
               ▼
        MCP Structured Result

               ▲
               │ Query Path (Read-Only)
┌──────────────┴───────────────┐
│ Existing MyMonee Services    │
│ dashboard, analytics, txs,   │
│ recurring, salary/income     │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│       SQLite Ledger          │
│   (mymonee.mcp.readonly_db)  │
│ file:...db?mode=ro           │
│ PRAGMA query_only = ON       │
└──────────────────────────────┘
```

### Security Guarantees:
- **Runtime Read-Only**: The MCP process connects to SQLite using `mode=ro` and `PRAGMA query_only = ON;`. Write queries (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`) are rejected at the database engine level.
- **No Arbitrary Execution**: Zero database consoles, SQL query builders, shell tools, or Python execution.
- **Fail-Closed Privacy Validator**: Every DTO emitted is recursively inspected for emails, JWTs, Bearer tokens, Luhn-valid card numbers, and filesystem paths. If any forbidden pattern is detected, the operation aborts with an internal error without returning the leaked data.
- **Decimal Money**: Financial values are represented as string decimals (`{"amount": "420.00", "currency": "INR"}`), eliminating floating-point ambiguity.
- **Opaque Public Identifiers**: Internal database UUIDs and row IDs are never exposed (`txn_9cbd76aefba52871`, `merch_1ab6c947a9c58c81`).
- **Masked Accounts**: Bank account and card identifiers are masked to the last 4 characters (`•••• 1234`).
- **Canonical Spending Truth**: Spending aggregates automatically exclude transfers, credit card bill payments, duplicates, and refunds.

---

## 2. Hermes Agent Configuration

Hermes connects to local MCP servers via standard input/output (`stdio`).

Edit your Hermes configuration file at `~/.hermes/config.yaml`:

```yaml
mcp_servers:
  mymonee:
    command: "/Users/gauravsingh/projects/my-monee/.venv/bin/mymonee"
    args: ["mcp"]
    enabled: true

    timeout: 60
    connect_timeout: 10

    # Sequential execution recommended initially
    supports_parallel_tool_calls: false

    # Safe untrusted mode; read-only tools run without prompting
    trust: untrusted

    tools:
      include:
        - get_financial_summary
        - get_category_spending
        - get_merchant_history
        - search_transactions
        - get_recurring_expenses
        - get_income_and_salary
        - get_cash_flow_trends
        - list_budget_categories
        - get_agent_capabilities

      resources: false
      prompts: false
```

> [!NOTE]
> In Hermes Agent, MCP tools are prefixed as `mcp__mymonee__<tool_name>` (e.g. `mcp__mymonee__get_financial_summary`).

---

## 3. Verification & Live Reload

### 3.1 Verify Connectivity from CLI
Run Hermes' built-in MCP diagnostic:
```bash
hermes mcp test mymonee
```

### 3.2 Live Reload in an Active Hermes Session
If Hermes is already running in your terminal or web session, reload active MCP tools without restarting:
```text
/reload-mcp
```

### 3.3 CLI Terminal Testing (Human & Script Mode)
You can test the exact same Agent Service queries from your terminal using the built-in CLI adapter:
```bash
source .venv/bin/activate

# Monthly summary
mymonee agent summary

# Spending breakdown or category deep-dive
mymonee agent spending --category Food --range 3m

# Merchant history
mymonee agent merchant --name Zepto

# Filter transactions safely
mymonee agent transactions --limit 5

# Subscriptions and bills
mymonee agent recurring

# Pay-period salary attribution
mymonee agent income

# Multi-month cash flow trends
mymonee agent trends

# Budget category taxonomy
mymonee agent categories
```

---

## 4. MCP Tool Catalog

| MCP Tool Name | Description | Hermes Tool Name |
| :--- | :--- | :--- |
| `get_financial_summary` | Authoritative monthly financial overview (total spent, living spend, commitments, income, cash flow, top categories/merchants). | `mcp__mymonee__get_financial_summary` |
| `get_category_spending` | Breakdown across all categories, or deep-dive into a single category with median ticket size, subcategories, top merchants, and insights. | `mcp__mymonee__get_category_spending` |
| `get_merchant_history` | Total spent, transaction count, average ticket size, first/last seen dates, and recent purchases for a specific merchant. | `mcp__mymonee__get_merchant_history` |
| `search_transactions` | Search recent transactions with filters (query, category, direction, date range, amount) and pagination. Masked accounts (`•••• 1234`). Max 50 items. | `mcp__mymonee__search_transactions` |
| `get_recurring_expenses` | Active recurring subscriptions (Netflix, Spotify, iCloud) and scheduled bills with frequencies, next dates, and annual cost. | `mcp__mymonee__get_recurring_expenses` |
| `get_income_and_salary` | Salary and income by pay-period over the last N months. Accurately maps salary credits to the month they pay for using Axis `/Sala` rules. | `mcp__mymonee__get_income_and_salary` |
| `get_cash_flow_trends` | Multi-month cash flow trajectory comparing total qualifying spent, income, and net savings/deficit. | `mcp__mymonee__get_cash_flow_trends` |
| `list_budget_categories` | The authoritative category and subcategory taxonomy configured in MyMonee. | `mcp__mymonee__list_budget_categories` |
| `get_agent_capabilities` | Contract versioning metadata and supported capability names. | `mcp__mymonee__get_agent_capabilities` |
| `get_unclassified_spends` | Review pending/unclassified transactions requiring category assignment. Emits Fernet-authenticated reversible public transaction IDs (`txn_...`). | `mcp__mymonee__get_unclassified_spends` |
| `classify_transaction` | Update a transaction's category/subcategory using its opaque public token (`txn_...`) and human-readable slugs. Write-capable tool (`readOnlyHint=False`). | `mcp__mymonee__classify_transaction` |

---

## 5. Recommended Hermes System Guidance

Include the following guidance in your Hermes Agent prompt (or persona configuration):

```text
Use MyMonee MCP tools for questions about personal financial data.

Treat MyMonee aggregate financial results as authoritative. Do not reconstruct
totals from individual transactions when an authoritative aggregate is available.

Use MyMonee's category taxonomy when discussing categories (query list_budget_categories
if unsure of category names).

Respect pagination and has_more when searching transactions.

Never attempt to access SQLite, database files, source code, credentials,
email data, environment variables, SQL, shell commands, or arbitrary Python.

MyMonee MCP responses are intentionally privacy-filtered.
```

---

## 6. Sample Conversational Queries

- **"How much did I spend this month?"**
  → Hermes invokes `mcp__mymonee__get_financial_summary(month="current")`.
- **"What were my top expense categories in August 2026?"**
  → Hermes invokes `mcp__mymonee__get_financial_summary(month="2026-08")`.
- **"Break down my food expenses over the last 3 months."**
  → Hermes invokes `mcp__mymonee__get_category_spending(category="Food", range="3m")`.
- **"How much have I spent on Zepto recently?"**
  → Hermes invokes `mcp__mymonee__get_merchant_history(merchant_name="Zepto", months=6)`.
- **"What subscriptions am I currently paying for?"**
  → Hermes invokes `mcp__mymonee__get_recurring_expenses()`.
- **"What was my salary for July and August?"**
  → Hermes invokes `mcp__mymonee__get_income_and_salary(months=3)`.
- **"Show me my net savings trend over the past six months."**
  → Hermes invokes `mcp__mymonee__get_cash_flow_trends(months=6)`.
- **"Review my unclassified transactions and classify them."**
  → Hermes invokes `mcp__mymonee__get_unclassified_spends()`, queries `mcp__mymonee__list_budget_categories()`, and classifies via `mcp__mymonee__classify_transaction(transaction_id="txn_...", category_slug="...", subcategory_slug="...")`.

---

## 7. Automated Continuous Deployment via Hermes Webhooks

Hermes serves as the external automation and control plane for MyMonee. When a pull request is merged into `main` on GitHub, Hermes automatically pulls the latest changes, builds the production frontend, restarts the local macOS daemon, and verifies system health.

```text
GitHub (PR Merged into main)
          │
          │ POST /webhooks/mymonee-deploy (Signed HMAC-SHA256)
          ▼
Tailscale Funnel (Port 443 HTTPS Proxy)
          │
          ▼
Hermes Webhook Gateway (Port 8644)
          ├── 1. HMAC-SHA256 signature verification (X-Hub-Signature-256)
          ├── 2. Declarative filter evaluation:
          │      action == "closed"
          │      pull_request.merged == true
          │      pull_request.base.ref == "main"
          │
          ▼ (HTTP 202 Accepted)
Hermes Agent (Autonomous Session)
          │
          │ Toolset: ["terminal"] (Restricted per-route permissions)
          │
          ▼
scripts/trigger_deploy.sh
          ├── 1. Guardrail: Working tree must be clean (git status --porcelain, aborts otherwise)
          ├── 2. Branch check: Safely switches to 'main' if clean feature branch
          ├── 3. git fetch origin main && git pull --ff-only origin main
          ├── 4. scripts/deploy_local.sh (npm run build in web/)
          ├── 5. launchctl kickstart -k gui/501/com.personal.my-monee
          └── 6. Health check verification (http://127.0.0.1:8477/api/health)
          │
          ▼
Telegram Status Delivery (Chat ID: 1117425083)
```

### Architectural Principles:
1. **No Intermediate Webhook Receivers**: GitHub talks directly to Hermes's native webhook platform via Tailscale Funnel. No custom microservice or HTTP listener needed.
2. **Hard Security Boundary**: HMAC verification and declarative filtering occur at the gateway layer before any model turns or shell processes are spawned. Unsigned or non-qualifying requests are stopped at the edge.
3. **Strict Deterministic Contract**: The agent is restricted to `terminal` toolset and given an explicit, un-improvised instruction to run `scripts/trigger_deploy.sh` and capture the exit code.
4. **Development Checkout Safety**: The deployment script enforces branch purity and clean working trees; it will never stash or manipulate active development changes unexpectedly.
