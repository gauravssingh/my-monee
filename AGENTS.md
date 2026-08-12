# AGENTS.md

Guidance for coding agents working in this repository. Prefer `CLAUDE.md` for dense project memory; this file is the short operating contract.

## Mission

Build and maintain **MyMonee**, a **local-first** macOS expense tracker: Gmail notification emails → durable SQLite ledger → classification → personal dashboard. Privacy-first; no cloud DB; external AI off by default.

## Working rules

1. Keep changes scoped to the task. Do not drive-by refactor unrelated modules.
2. Match existing patterns in `src/expense_tracker/` and `web/src/`.
3. After Python logic changes that affect money/classification, add or update tests under `tests/`.
4. After UI changes, rebuild `web/` (`npm run build`) so the FastAPI-served UI updates.
5. Never commit secrets (`gmail_credentials.json`, tokens, `.env`, Keychain dumps), SQLite data, local configuration, or the installed launchd plist. Use `config/local.example.yaml` as the safe template.
6. Only commit / push / open PRs when the user asks.
7. Always place ad-hoc exploration, maintenance, or data cleanup scripts in the `scripts/` folder to keep the root directory clean.

## Architecture pointers

| Area | Where |
|------|--------|
| HTTP API | `src/expense_tracker/api/routes/` |
| Sync pipeline | `src/expense_tracker/ingestion/` |
| Parsers | `src/expense_tracker/parsers/` (+ YAML in `config/providers/`) |
| Classification enrichment | `src/expense_tracker/classification/` |
| Dashboard metrics | `src/expense_tracker/services/dashboard.py` |
| Manual classify | `src/expense_tracker/services/transactions.py` |
| React UI | `web/src/pages/`, `web/src/components/` |

Full design: [ARCHITECTURE.md](./ARCHITECTURE.md). Commands and domain gotchas: [CLAUDE.md](./CLAUDE.md).

## Current priorities

1. **Learn from corrections** — persist merchant → category rules from Needs Review.
2. **Phase 3** — stronger dedupe, refund pairing, cross-account transfer matching.
3. Keep Axis `/Sala` salary and pay-period income attribution correct.

## Verification

```bash
source .venv/bin/activate
pytest
cd web && npm run build
```

Restart the local/launchd server after shipping backend or built-UI changes.
