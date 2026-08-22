# MyMonee — Agent Memory

Local-first personal finance app for macOS. Gmail alerts → parse → classify → dashboard. The UI brand is **MyMonee** (*.. my finances*); package identifiers and the local data directory remain `ExpenseTracker`.

## Stack

- **Backend:** Python 3.12+, FastAPI, SQLAlchemy, SQLite
- **Frontend:** React + Vite + TypeScript (`web/`), served by FastAPI from `web/dist`
- **Auth:** Gmail OAuth (`gmail.readonly`); tokens in macOS Keychain (`ExpenseTracker`)
- **Runtime:** `http://127.0.0.1:8477`; optional `launchd` via `scripts/launchd/`

## Commands

```bash
source .venv/bin/activate
pip install -e ".[dev]"
cd web && npm install && npm run build && cd ..
python -m expense_tracker          # API + UI
pytest                             # tests
python .agents/skills/playwright-frontend-testing/scripts/ui_test_runner.py --all  # Playwright UI & visual tests
ruff check src tests               # lint
launchctl kickstart -k "gui/$(id -u)/com.personal.expense-tracker"  # restart launchd service
```

Dev frontend (HMR): `scripts/run_dev.sh` or Vite against the API.
**Note:** Always place ad-hoc exploration, maintenance, or data cleanup scripts in the `scripts/` folder to keep the root directory clean.

## Layout

```
config/                 # default.yaml + providers/*.yaml discovery rules
src/expense_tracker/
  api/routes/           # FastAPI routes
  ingestion/            # Gmail client, OAuth, sync pipeline
  parsers/              # AxisBankParser, generic, provider rule parsers
  classification/       # apply_parsed_enrichment
  services/             # dashboard, transactions, categories
  db/                   # models, seed, session
web/src/                # React dashboard
scripts/                # run_server, launchd plist
tests/
```

Data lives under `~/Library/Application Support/ExpenseTracker/` (DB, logs, credentials).

## Roadmap status

| Phase | Focus | Status |
|-------|--------|--------|
| 1 | Skeleton, SQLite, dashboard shell | Done |
| 2 | Gmail OAuth, discovery, parsers, sync | Done |
| 3 | Normalization, dedupe, refunds, transfers | Next (partial: Axis transfer/refund flags) |
| 4 | Categories, merchant rules, corrections learning | In progress (Needs Review classify UI done) |
| 5 | Personal model, recurring, anomalies | Later |
| 6 | Packaging, backup, performance | Later |

**Next product work:** a rule-learning consumer of `classification_corrections` (the table exists and every user correction is captured — see Domain rules below — but nothing yet upserts a `classification_rules` row from it), then Phase 3 dedupe/refund/transfer matching.

## Domain rules (do not break)

### Axis salary = income only when `/Sala`
- Subject patterns: `Credit transaction alert for Axis Bank A/c`, credited-to-A/c variants
- Salary signal: `NEFT|IMPS|RTGS/.../Sala` (or `/Salary`)
- Other Axis credits → transfer/refund/needs_review — **not** income
- Parser: `parsers/axis.py` → `classify_axis_credit`; registered before generic in `parsers/bootstrap.py`

### Income pay period
- Salary credited **after day 2** of month M counts for **month M+1**
- Credits on **1st–2nd** count for the **current** month
- Logic: `services/dashboard.py` → `salary_pay_period` / `income_for_pay_period`
- Overview income card = this pay-period month only; MoM + 6-month chart in modal

### Classification
- Income = `transaction_type == "income"` only (not all credits)
- Transfers/income set `excludes_from_spending`
- Manual classify: `PATCH /api/transactions/{id}/classify`, `POST /api/transactions/classify-bulk`
- User classify → `user_verified=True`, `needs_review=False`, `classification_source="user"`

### Classification corrections
- Every `classify_transaction` / `exclude_as_non_transaction` call snapshots the pre-correction label into `classification_corrections` (previous vs. new category/subcategory/source/confidence/signals) before mutating the row — this is the training-pair source for the learning loop, not just an audit log
- Skipped when the label isn't actually changing (same category/subcategory and already `classification_source="user"`), so re-saving the same category doesn't spam history

### Data issue flags
- Purely additive — flagging a transaction (`POST /api/transactions/{id}/flag-issue`) never mutates it; it only ever writes a `data_issue_flags` row
- Denormalizes `source` and `merchant_normalized` onto the flag at flag time so `GET /api/data-issues/summary` can group by (issue_type, source) with no joins — that grouping is the "bulk fix instead of one email at a time" path
- Distinct from the existing "Exclude — not a valid transaction email" action in `ClassifyPanel`: Exclude fixes one row right now; a `not_a_transaction` flag defers a suspected extraction bug into the Data Issues queue for grouped review
- `field_name` is restricted to `FLAGGABLE_FIELDS` in `services/data_issues.py`; `reported_value` is always a live snapshot read off the transaction at flag time, never user-typed

### Gmail OAuth
- Prefer **Web application** client if redirect URIs must be configured; Desktop clients often hide URI fields
- Required redirect: `http://127.0.0.1:8477/oauth/callback`
- PKCE `code_verifier` must persist between `start_oauth` and `complete_oauth` (Keychain pending blob)
- Install/replace credentials from Settings UI or `gmail_credentials.json` in data dir

## Design preferences

- No “AI-generated” dashboard chrome: avoid purple gradients, cream+terracotta, card color rainbows, glow/pills spam
- Prefer the existing restrained CSS in `web/src/styles.css`
- Debit amounts red / credit green in transaction rows is intentional

## Gotchas

- After frontend changes: `cd web && npm run build` then restart the server/launchd job (API serves `web/dist`)
- Re-parse Axis credits: `python -m expense_tracker.reclassify_axis` (force_reparse)
- Amounts like `INR .52` are valid — parsers must allow leading decimal
- `UPILITE` is a real Axis channel token (include in patterns)
- Do not commit credentials, Keychain material, `config.local.yaml`, SQLite data, or `scripts/launchd/com.personal.expense-tracker.plist`; use `config/local.example.yaml` and the launchd `.example` as templates
- Sandbox may hit `readonly database` on the real SQLite path — use full permissions for DB writes

## Key files

- `ARCHITECTURE.md` — full design
- `README.md` — setup / Gmail connect
- `src/expense_tracker/ingestion/pipeline.py` — sync + persist
- `src/expense_tracker/services/dashboard.py` — overview / income trend
- `src/expense_tracker/parsers/axis.py` — Axis salary/transfer rules
- `web/src/pages/TransactionsPage.tsx` — ledger/review tables, sortable columns, date and direction filters, bulk classify, per-row flag action
- `web/src/pages/SettingsPage.tsx` — Gmail connection/sync, category and local storage settings
- `src/expense_tracker/services/data_issues.py` — data-issue flags + classification-correction history
- `web/src/pages/DataIssuesPage.tsx` — flagged-issue aggregation and bulk resolve/dismiss
