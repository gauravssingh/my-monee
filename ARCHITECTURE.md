# MyMonee — Architecture

*.. my finances*

Local-first personal finance intelligence for macOS. Connect Gmail once; continuously discover, normalize, classify, and learn from your transactions. The implementation package and runtime data directory retain the `ExpenseTracker` identifier for compatibility.

---

## 1. Recommended Architecture

```text
┌─────────────────────────────────────────────────────────────────┐
│                        macOS (local host)                        │
│                                                                  │
│  launchd / app start                                             │
│       │                                                          │
│       ▼                                                          │
│  ┌──────────────┐     ┌─────────────────┐     ┌──────────────┐ │
│  │  Scheduler   │────▶│  Ingestion      │────▶│  SQLite DB   │ │
│  │  (APScheduler│     │  Pipeline       │     │  (~/Library) │ │
│  │   + launchd) │     │                 │     └──────┬───────┘ │
│  └──────────────┘     │  discover →     │            │         │
│                       │  classify email │            │         │
│  ┌──────────────┐     │  detect source  │            ▼         │
│  │ macOS        │     │  parse →        │     ┌──────────────┐ │
│  │ Keychain     │◀───▶│  dedupe →       │     │ Classification│ │
│  │ (OAuth)      │     │  reconcile →    │────▶│ Engine        │ │
│  └──────────────┘     │  classify       │     │ rules → hist  │ │
│                       └────────┬────────┘     │ → ML/AI       │ │
│                                │              └──────────────┘ │
│                                ▼                               │
│                       ┌─────────────────┐                      │
│                       │ Local FastAPI   │◀── localhost:8477    │
│                       │ + static web UI │                      │
│                       └─────────────────┘                      │
│                                                                  │
│  Optional (explicit opt-in): local LLM (Ollama) / cloud LLM     │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼ (only network dependency by default)
    Gmail API (OAuth)
```

**Design principles**

- Mac is both server and client; no cloud app tier.
- Pipeline stages are isolated; parsers are plugins.
- Deterministic rules beat ML when they are accurate.
- Schema is extensible via JSON columns; never break historical rows.
- Failed emails never abort an ingestion run.

---

## 2. Technology Stack (with rationale)

| Layer | Choice | Why |
|-------|--------|-----|
| Language | **Python 3.12+** | Best local ML/NLP ecosystem, Gmail client libraries, rapid parser iteration, maintainable for a solo personal tool |
| API | **FastAPI + Uvicorn** | Typed local HTTP API, easy static UI mount, background tasks |
| DB | **SQLite** | Zero ops, single-file backup, excellent for personal-scale data; WAL mode for concurrent read during sync |
| ORM | **SQLAlchemy 2.0** | Clear models, JSON columns, future Alembic migrations |
| Config | **YAML + pydantic-settings** | Human-editable provider rules without code changes |
| Secrets | **macOS Keychain** via `keyring` | Native secure storage; never store Gmail passwords |
| Scheduler | **APScheduler** in-process + **launchd** plist | Keeps running after login; no Docker |
| Frontend | **React + Vite + TypeScript** | Clean local dashboard; served by FastAPI in production mode |
| Email parsing | **BeautifulSoup + regex + pluggy** | HTML/plain text; plugin entry points per provider |
| Future ML | **scikit-learn / sentence-transformers / Ollama** | Local-first; architecture does not lock to one model |
| Packaging (later) | **pyinstaller** or **briefcase** | Optional native launcher; Phase 1 runs via `python -m` |

**Why not Swift-only?** Faster Gmail/parser/ML iteration in Python; UI is a localhost dashboard, which matches “Mac as server.” Native wrappers can come in Phase 6.

**Why not Docker?** Explicitly avoided; adds nothing for a single-user local Mac app.

---

## 3. Project / Folder Structure

```text
expense-tracker/
├── ARCHITECTURE.md
├── README.md
├── pyproject.toml
├── config/
│   ├── default.yaml              # App defaults
│   ├── local.example.yaml        # Safe per-Mac override template
│   └── providers/                # Email discovery + parser rules (Phase 2+)
│       └── .gitkeep
├── src/expense_tracker/
│   ├── __init__.py
│   ├── __main__.py               # python -m expense_tracker
│   ├── app.py                    # FastAPI factory
│   ├── config.py
│   ├── logging_setup.py
│   ├── db/
│   │   ├── models.py             # Canonical schema
│   │   ├── session.py
│   │   └── seed.py               # Default categories
│   ├── api/
│   │   ├── deps.py
│   │   └── routes/
│   │       ├── health.py
│   │       ├── overview.py
│   │       ├── transactions.py
│   │       ├── categories.py
│   │       ├── gmail.py
│   │       └── system.py
│   ├── domain/                  # Pure domain types / enums
│   │   └── enums.py
│   ├── ingestion/
│   │   ├── pipeline.py
│   │   ├── gmail/
│   │   └── discovery.py
│   ├── parsers/                  # Provider-specific and generic parsers
│   │   ├── axis.py
│   │   ├── scapia.py
│   │   ├── rule_parser.py
│   │   └── registry.py
│   ├── classification/
│   │   └── enrichment.py
│   ├── merchants/                # Normalization layer
│   │   └── normalize.py
│   ├── services/
│   │   ├── categories.py
│   │   ├── dashboard.py
│   │   ├── date_repair.py
│   │   └── transactions.py
│   ├── connect_gmail.py
│   ├── reclassify_axis.py
│   └── sync_gmail.py
├── web/                          # React dashboard
│   ├── package.json
│   ├── vite.config.ts
│   └── src/
├── scripts/
│   ├── run_dev.sh
│   ├── run_server.sh
│   └── launchd/
│       └── com.personal.expense-tracker.plist.example
├── tests/
└── data/                         # Dev-only local data (gitignored)
```

Application data at runtime lives under:

```text
~/Library/Application Support/ExpenseTracker/
  ├── expense_tracker.db
  ├── config.local.yaml
  ├── logs/
  └── raw_emails/                 # Optional debug archive (opt-in)
```

---

## 4. Database Schema

Core tables (SQLite). Extra attributes go in `extra_json` / `metadata_json` so historical rows stay valid.

### `transactions`

Canonical finance record (source-independent).

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | UUID |
| source | TEXT | e.g. `gmail:hdfc`, `csv`, `manual` |
| source_email_id | TEXT | Gmail message id |
| source_thread_id | TEXT | |
| transaction_date | TEXT (ISO) | |
| posted_date | TEXT | nullable |
| amount | NUMERIC | always positive; direction separate |
| currency | TEXT | default INR |
| direction | TEXT | `debit` \| `credit` |
| transaction_type | TEXT | purchase, refund, … |
| merchant_raw | TEXT | |
| merchant_normalized | TEXT | |
| merchant_entity_id | TEXT FK | nullable |
| merchant_category | TEXT | provider hint |
| payment_method | TEXT | |
| account | TEXT | masked |
| card | TEXT | last4 / masked |
| upi_id | TEXT | |
| reference_number | TEXT | |
| bank_reference | TEXT | |
| description | TEXT | |
| location | TEXT | |
| category_id | TEXT FK | nullable |
| subcategory_id | TEXT FK | nullable |
| classification_confidence | REAL | 0–1 |
| classification_source | TEXT | rule / historical / ai / user / unknown |
| classification_signals | JSON | why |
| user_verified | INTEGER | bool |
| parent_transaction_id | TEXT FK | refunds / EMI parts |
| is_duplicate | INTEGER | |
| is_refund | INTEGER | |
| is_transfer | INTEGER | own-account movement |
| excludes_from_spending | INTEGER | transfers, CC payments, etc. |
| raw_email_reference | TEXT | path or message id |
| extra_json | JSON | forward-compatible fields |
| created_at / updated_at | TEXT | |

Unique indexes for idempotency: `(source, source_email_id, reference_number)` and fallback hash of amount+date+merchant+email.

### Supporting tables

- `emails` — discovered Gmail messages (id, thread, sender, subject, snippet, received_at, labels, parse_status, raw_headers_json)
- `ingestion_runs` / `ingestion_events` — observability
- `sync_state` — last historyId / query watermark per mailbox
- `categories` / `subcategories` — hierarchy
- `merchants` / `merchant_aliases` — entity + raw forms
- `classification_rules` — deterministic / learned rules
- `transaction_links` — refund, reversal, EMI, transfer relationships
- `classification_corrections` — audit trail of every user category correction: prior category/subcategory/source/confidence/signals vs. the corrected value, so mispredictions survive as supervised training pairs instead of being overwritten in place (see §12)
- `data_issue_flags` — user-flagged data-extraction problems (wrong amount, wrong date, wrong merchant, wrong direction, not-a-transaction, duplicate, other); denormalizes `source` and `merchant_normalized` at flag time for bulk aggregation by likely root cause (see §17)
- `settings` — non-secret key/value

---

## 5. Gmail OAuth Architecture

```text
User clicks Connect Gmail
        │
        ▼
Local FastAPI starts OAuth (loopback http://127.0.0.1:<port>/oauth/callback)
        │
        ▼
Google consent (gmail.readonly scope only)
        │
        ▼
Authorization code → token exchange
        │
        ▼
Access + refresh tokens stored in macOS Keychain
  service: "ExpenseTracker"
  account: "gmail-oauth"
        │
        ▼
Runtime: keyring.get_password → google-auth refresh as needed
```

- Client secrets file path configured locally; never committed.
- Scope: `https://www.googleapis.com/auth/gmail.readonly` (minimum).
- No Gmail passwords stored.
- Token revocation supported from Settings.

---

## 6. Gmail Ingestion Strategy

```text
Scheduler tick
  → load sync_state (historyId or newer_than watermark)
  → list messages matching discovery rules (NOT sender-only)
  → for each message id (skip if emails.id exists and parse_status=ok):
        fetch metadata + body
        store email row
        classify as financial? → else mark skipped
        detect provider plugin
        parse → zero or more canonical transactions
        dedupe → persist or mark duplicate
        reconcile refunds/transfers
        classify
  → update sync_state
  → write ingestion_run stats
```

**Idempotency**

1. Primary key: Gmail `message_id` in `emails`.
2. Transaction natural key: `(source_email_id, reference_number)` when present.
3. Else fingerprint: `sha256(email_id|amount|date|direction|merchant_raw|ref)`.
4. Re-runs update `updated_at` / reparse flags; they do not insert duplicates.

**Discovery rules** (configurable YAML): subject/body regex, label, category headers, amount-like patterns, exclusion rules — sender is one signal among many.

---

## 7. Canonical Transaction Schema

See §4 and `src/expense_tracker/db/models.py`. Domain enums live in `domain/enums.py` (`Direction`, `TransactionType`, `ClassificationSource`).

The API and UI always speak this model; parsers map provider-specific fields into it.

---

## 8. Parser / Plugin Architecture

```text
ParserPlugin (protocol)
  name: str
  priority: int
  can_parse(email_ctx) -> float   # confidence 0–1
  parse(email_ctx) -> list[ParsedTransaction]
```

Registry loads plugins from `parsers/` and optional entry points. Ingestion never embeds bank-specific logic.

Each plugin may declare accompanying discovery hints in `config/providers/<name>.yaml`.

---

## 9. Deduplication Strategy

Layers:

1. **Email bodies:** Downloaded and stored locally in the database (`body_text` and `body_html`) for ML training and offline debugging. successfully → skip (unless `force_reparse`).
2. **Reference-level** — same bank/UPI reference → same transaction.
3. **Fingerprint-level** — amount + date ±1 day + normalized merchant + direction.
4. **Near-duplicate review** — high similarity but not exact → `Needs Review` (potential duplicate).

Duplicates set `is_duplicate=1` and link to the survivor via `parent_transaction_id` / `transaction_links`.

---

## 10. Refund / Reversal Matching

```text
Credit / refund-type event
  → candidates: debits with same merchant entity (or normalized),
    amount ≥ refund (full or partial),
    date window (e.g. 90 days),
    same card/account when available
  → score: amount exactness, date proximity, reference overlap, merchant match
  → high score: auto-link (transaction_links.kind = refund)
  → low score: Needs Review (unmatched refund)
```

Net effect on spending: original remains; refunds reduce net spend for the merchant/period; dashboard “spending” uses `excludes_from_spending=0` and nets linked refunds.

Supports full, partial, multi-part refunds, reversals, failures, chargebacks.

---

## 11. Personal Classification Architecture

Hierarchical decision flow:

```text
normalize merchant
  → exact deterministic rule? → classify (source=rule)
  → strong historical match (same merchant entity / UPI / alias)? → classify (source=historical)
  → similar transactions (features)? → classify if confidence ≥ threshold
  → optional local/cloud AI (opt-in) → classify if confidence ≥ threshold (source=ai)
  → else unknown → Needs Review
```

Signals stored in `classification_signals` for explainability.

User corrections write/upgrade `classification_rules` and mark `user_verified=1`.

---

## 12. Learning / Correction Workflow

```text
Needs Review / Transaction detail
  → user sets category + subcategory (keyboard-friendly)
  → persist correction
  → upsert learned rule (merchant_entity / alias / upi / fingerprint scope)
  → optionally reclassify open similar unverified rows (same entity)
  → confidence for future matches increases
```

Every "persist correction" step also inserts a `classification_corrections` row capturing the
label as it stood *before* the overwrite (previous category/subcategory/source/confidence/signals)
alongside the corrected value. This is what makes the loop trainable: a mispredicted
`rule`/`historical`/`ai` label that a user overturns is a hard negative example, not just a
discarded value — replaying `(previous_label, corrected_label)` pairs is the supervised signal for
Phase 5. The "upsert learned rule" step above is not yet implemented: corrections are captured, but
nothing yet writes to `classification_rules` automatically.

Distinction retained:

| Source | Meaning |
|--------|---------|
| `rule` | Explicit or strongly learned deterministic rule |
| `historical` | Inferred from past verified txs |
| `ai` | Model suggestion |
| `user` | Direct manual set on this row |
| `unknown` | No confident label |

---

## 13. Dashboard Information Architecture

| View | Purpose |
|------|---------|
| **Overview** | Month spend, prior month, income, net cash flow, tx count, largest tx |
| **By Category** | Hierarchy bars / list |
| **By Merchant** | Top merchants + trend |
| **Timeline** | Day/month exploration |
| **Transactions** | Sortable, searchable/filterable table |
| **Needs Review** | Prioritized correction queue |
| **Data Issues** | Flagged extraction problems (wrong amount/date/merchant/direction, not-a-transaction, duplicate), grouped by issue type and source for bulk triage (§17) |
| **Analytics** | Trends, recurring, anomalies (Phase 5) |
| **Settings** | Gmail sync, category management, local storage and runtime health |

Current UI ships the Overview, sortable/searchable Transactions with inclusive From/To and debit/credit filters, Needs Review bulk classification, Data Issues flag triage, and Settings.

---

## 14. macOS Background Execution Strategy

**Phase 1:** Foreground `python -m expense_tracker` (API + UI).

**Current:** `launchd` LaunchAgent (`RunAtLoad`, `KeepAlive`) can start the app at login using the committed plist template. The installed per-Mac plist is intentionally Git-ignored.

**Later:** in-process scheduling if periodic automatic sync is enabled.
3. Optional menu-bar / notifications via `osascript` or a thin Swift helper (Phase 6).
4. Logs under `~/Library/Logs/ExpenseTracker/` or Application Support `logs/`.

No Docker. No remote workers.

---

## 15. Security / Privacy Model

| Concern | Approach |
|---------|----------|
| OAuth tokens | macOS Keychain only |
| Transaction data | Local SQLite; never uploaded by default |
| External AI | Off by default; config flag; UI banner when data would leave machine |
| Logs | No tokens, no full card numbers, no full email bodies by default |
| UI | Mask account/card/UPI beyond last 4 / local-part policy |
| Backups | User copies DB file; optional encrypted export later |
| Network | Gmail API + optional AI endpoint only |

---

## 16. Development Roadmap

| Phase | Focus | Status |
|-------|--------|--------|
| **1** | Skeleton, SQLite, config, logging, basic dashboard, canonical model | Done |
| **2** | Gmail OAuth, discovery, message store, first parser plugin | Done |
| **3** | Normalization, dedupe, refunds, transfers | Next (partial Axis transfer/refund flags) |
| **4** | Categories, merchant layer, rules, historical match, corrections | In progress (manual/bulk classify UI) |
| **5** | Personal model, recurring, anomalies, insights | |
| **6** | launchd, Keychain hardening, backup/restore, performance | |

Backward-compatible schema evolution at every phase (`extra_json`, additive columns).

---

## 17. Data Quality Flags

Distinct from category corrections (§12): this loop is about **extraction accuracy** — did the
parser get the right amount, date, merchant, or even recognize a real transaction at all — not
categorization accuracy.

```text
Transaction row (ledger or Needs Review)
  → user flags a problem (wrong amount / date / merchant / direction,
    not-a-transaction, duplicate, other)
  → flag captures: issue_type, optional field_name + a reported_value
    snapshot taken from the row, optional suggested_value, note,
    denormalized source + merchant_normalized
  → flag is purely additive — the transaction row is left untouched
  → Data Issues view groups open flags by (issue_type, source)
  → once the shared root cause (usually one bank's parser rule) is fixed,
    resolve or dismiss the whole group in bulk instead of visiting each email
```

`not_a_transaction` here is deliberately separate from the immediate "Exclude" action already
available while classifying (§12): Exclude fixes one row right now; a flag defers a suspected
extraction bug into a queue meant to be triaged many-at-once after the underlying parser is fixed.

API: `POST /api/transactions/{id}/flag-issue`, `GET /api/data-issues`, `GET /api/data-issues/summary`
(grouped counts), `POST /api/data-issues/resolve-bulk`. UI: **Data Issues** page (§13).

---

## Accuracy Principle

Prefer:

```text
unknown → ai → user verified → learned rule → high-confidence auto
```

Optimize for **classification accuracy**, not AI usage volume.
