# MyMonee

*.. my finances*

Local-first personal finance intelligence for macOS. Connect Gmail once; continuously discover, normalize, classify, and learn from your spending. The Python package and local data directory retain the `ExpenseTracker` name for compatibility.

See [ARCHITECTURE.md](./ARCHITECTURE.md) for the full design (stack, schema, Gmail, classification, privacy, roadmap).

## Current status

**Phase 2 — Gmail ingestion** is done. Early **Phase 4** groundwork is in place.

- Gmail OAuth (read-only) with tokens in macOS Keychain + PKCE pending state
- Configurable discovery rules (`config/providers/`)
- Incremental, idempotent sync pipeline
- Axis Bank salary rule (`…/Sala`), transfer/refund heuristics, generic parsers
- Income pay-period attribution + MoM / 6-month income chart
- Transactions: search, From/To date range, debit/credit filter, and pagination
- Needs Review: date/direction filters, multi-select, and bulk classify panel
- Settings: Gmail connection/sync, category management, and local storage health

Agent memory: [CLAUDE.md](./CLAUDE.md) · [AGENTS.md](./AGENTS.md) · `.cursor/rules/`

**Next:** learn-from-corrections, then Phase 3 dedupe / refunds / transfers.

## Requirements

- macOS
- Python 3.12+
- Node.js 20+ (for the dashboard build)
- Google Cloud OAuth Desktop client (for live Gmail sync)

## Quick start

```bash
# Backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Frontend
cd web && npm install && npm run build && cd ..

# Run (API + built UI on http://127.0.0.1:8477)
python -m expense_tracker
```

Open http://127.0.0.1:8477 → **Settings** → **Run demo emails** to verify parsing without Gmail.

## Connect Gmail

1. In [Google Cloud Console](https://console.cloud.google.com/), create an OAuth client.
   - Prefer **Web application** if you need to set redirect URIs explicitly.
   - **Desktop app** works if the installed client already allows the loopback callback.
2. Enable the **Gmail API** for the project.
3. Paste the client JSON in the app **Settings** page, or save it to:

```text
~/Library/Application Support/ExpenseTracker/gmail_credentials.json
```

   Or set `gmail.credentials_file` in `config.local.yaml`.

4. Authorized redirect URI (required for Web clients):

```text
http://127.0.0.1:8477/oauth/callback
```

5. Open the app → **Settings** → **Connect Gmail** → approve read-only access.
6. Click **Sync now**.

Tokens are stored in the macOS Keychain (`ExpenseTracker`). Passwords are never stored.
Google access tokens are renewed automatically from the stored refresh token; reconnecting
should only be necessary if Google revokes access or the Keychain entry is removed.

## Configuration

Defaults: `config/default.yaml`

Provider / discovery rules: `config/providers/`

Local overrides:

```text
~/Library/Application Support/ExpenseTracker/config.local.yaml
```

Start from [`config/local.example.yaml`](./config/local.example.yaml), copy it to the
location above, and edit it for this Mac. The local override and all OAuth credentials are
Git-ignored; do not place them in the repository or in a committed `.env` file.

## Git setup

The repository tracks application code, tests, documentation, provider rules, and safe
configuration templates. It intentionally excludes the virtual environment, build outputs,
SQLite data, OAuth client JSON, Keychain tokens, local configuration, and the installed
launchd plist. For launchd, copy
[`scripts/launchd/com.personal.expense-tracker.plist.example`](./scripts/launchd/com.personal.expense-tracker.plist.example)
to `scripts/launchd/com.personal.expense-tracker.plist` and replace the placeholder paths.

## Data locations

| Path | Purpose |
|------|---------|
| `~/Library/Application Support/ExpenseTracker/expense_tracker.db` | SQLite database |
| `~/Library/Application Support/ExpenseTracker/logs/` | Application logs |
| `~/Library/Application Support/ExpenseTracker/gmail_credentials.json` | OAuth client secrets (you provide) |
| macOS Keychain | Gmail refresh/access tokens |

## Privacy

- Transaction processing is local
- Gmail scope is `gmail.readonly` only
- External AI is **off** by default
- Logs redact token-like content

## Tests

```bash
source .venv/bin/activate
pytest
```
