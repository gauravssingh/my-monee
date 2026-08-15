# MyMonee

*.. my finances*

Local-first personal finance intelligence for macOS. Connect Gmail once; continuously discover, normalize, classify, and learn from your spending. The Python package and local data directory retain the `ExpenseTracker` name for compatibility.

See [ARCHITECTURE.md](./ARCHITECTURE.md) for the full design (stack, schema, Gmail, classification, privacy, roadmap).

## Gemini AI Smart Suggestions (Optional)

MyMonee includes an optional, human-in-the-loop AI suggestion assistant powered by the official `google-genai` SDK and Gemini Flash models.

### Privacy-First Hard Gate
- **External AI is disabled (`allow_external_ai: false`) by default.** No transaction data leaves your Mac unless you explicitly opt in.
- The API key is **never stored** in the database, configuration files, or logs. It is read strictly from the `GEMINI_API_KEY` environment variable (or `.env`).

### Enabling AI Suggestions
1. Install dependencies:
   ```bash
   pip install google-genai>=2.3.0
   ```
2. Set your API key in `.env`:
   ```bash
   GEMINI_API_KEY=your_gemini_api_key
   ```
3. Enable in `~/Library/Application Support/ExpenseTracker/config.local.yaml`:
   ```yaml
   privacy:
     allow_external_ai: true

   ai:
     enabled: true
     provider: gemini
     model: gemini-2.5-flash
   ```

### What is Sent / Withheld
- **Sanitized Data Sent:** Transaction amount, currency, direction (debit/credit), merchant raw/normalized name, brief description, and payment method, alongside MyMonee's category taxonomy.
- **Deliberately Withheld:** Gmail bodies/HTML, OAuth credentials, tokens, full account/card numbers, passwords, and PII.

### How it Works
- When reviewing transactions in **Needs Review**, Gemini provides structured suggestions constrained strictly to your existing database category IDs.
- Clicking **Accept Suggestion** pre-fills the standard category controls. Saving routes through MyMonee's authoritative verification and correction audit trail.
- All AI operations are recorded in the `ai_operations` audit table for transparency and offline supervised evaluation.

## License

Personal use.

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
