# Testing, Tooling & Docs-Consistency Audit

Scope: everything under `tests/`, plus `pyproject.toml`, `scripts/`, `.gitignore`, and a cross-check of `ARCHITECTURE.md`/`README.md`/`CLAUDE.md`/`AGENTS.md`/`.cursor/rules/*.mdc`/`docs/plans/` against the real file tree (the roadmap/architecture portion of that cross-check is consolidated into [01-architecture-and-documentation.md](./01-architecture-and-documentation.md); this doc covers the concrete drift findings that fed it).

## Part A — Test coverage audit

**Actual `pytest` run on this machine:**

Full `python -m pytest --tb=short -q` **hangs indefinitely** — confirmed via `lsof` on the running pytest process showing an `ESTABLISHED` TCP connection to a Google IP. With the one hanging test deselected:

```
python -m pytest --tb=short -q --deselect tests/test_phase2.py::test_sync_requires_connection
................................F.......                                 [100%]
FAILED tests/test_phase2.py::test_gmail_status_disconnected - assert True is ...
1 failed, 39 passed, 1 deselected, 1 warning in 0.79s
```

**41 tests total: 39 pass, 1 fails, 1 hangs forever on a live network call.**

**Root cause (verified, not guessed):** `is_connected()` in `ingestion/gmail/oauth.py:95-97` calls `load_credentials(settings)`, which reads from the **real macOS Keychain** (service `ExpenseTracker`) — it is not scoped to the test's `tmp_path` `Settings.app.data_dir`. Because this dev machine already has real Gmail OAuth tokens connected, `is_connected()` returns `True` inside tests too:

- `tests/test_phase2.py:24-31` (`test_gmail_status_disconnected`) asserts `body["connected"] is False` with no keyring/`is_connected` mock → **fails** on this machine.
- `tests/test_phase2.py:86-90` (`test_sync_requires_connection`) expects a 400 from `POST /api/gmail/sync`, but `gmail.py:192-193` only 400s `if not is_connected(settings)`. Since it's `True`, execution falls through to `run_ingestion_pipeline(...)` (`gmail.py:201-208`), which opens a real Gmail API client and **hangs on network I/O**.

Contrast: `tests/test_email_viewer.py:36-39,67-70` correctly `monkeypatch.setattr("mymonee.api.routes.gmail.is_connected", ...)` — the fix pattern already exists elsewhere in the suite but wasn't applied to `test_phase2.py`. **This is a genuine test-isolation bug, not environment flakiness** — it reproduces on any machine that has ever connected Gmail, and CLAUDE.md/AGENTS.md's "Commands"/"Verification" sections tell agents to just run `pytest` with no warning that it can hang or make live calls against production credentials.

**Ruff (`ruff check src tests`):** 146 errors, 106 auto-fixable.

```
42  FURB167  regex-flag-alias      (re.I → re.IGNORECASE, purely stylistic)
38  UP017    datetime-timezone-utc (timezone.utc → datetime.UTC, stylistic)
28  B008     function-call-in-default-argument (Depends(...) in FastAPI signatures — idiomatic FastAPI, not a real bug)
10  I001     unsorted-imports
 7  BLE001   blind-except (except Exception: — real ones worth a look, e.g. ingestion/gmail/mime.py:40,89)
 6  RUF100   unused-noqa
 5  FURB157  verbose-decimal-constructor
 3  F401     unused-import
 1  each: DTZ001, FLY002, RUF022, RUF059, S112, TRY004, UP035
```

`pyproject.toml` has `[tool.ruff]` with only `line-length`/`target-version` — **no `[tool.ruff.lint].select`/`ignore`**, so the rule surface is whatever ruff's resolved defaults are (~414 enabled rules, not classic pyflakes-only). 70 of the 146 errors (FURB167 + UP017 + B008) are stylistic or false-positive-for-FastAPI noise, meaning `ruff check src tests` — a standard command in CLAUDE.md — is **not currently a clean gate**, and the config doesn't pin what "clean" means, so results will drift with the ruff version.

**Module-by-module coverage:**

| Source module | Coverage |
|---|---|
| `parsers/axis.py` | Strong — `tests/test_axis_salary.py` (7 tests, all outcome-asserting) |
| `parsers/scapia.py` | Strong — `tests/test_scapia.py` (4 tests, guards a specific regression called out in `.cursor/rules/parsers.mdc`) |
| `parsers/extract.py` | Good — `test_date_parsing.py`, exercised further by `test_phase2.py`/`test_scapia.py` |
| `parsers/generic.py`, `bootstrap.py`, `registry.py` | Covered via integration paths in `test_phase2.py`/`test_axis_salary.py` |
| `parsers/base.py` | Data container only, fine indirectly |
| `parsers/rule_parser.py` | **No test at all.** No test file imports it. This is the YAML-hint-driven parser presumably backing `hdfc_alerts.yaml`/`upi_gpay.yaml` — `test_discovery.py` only checks an HDFC email is *detected*, never that it actually *parses* via this module. |
| `ingestion/discovery.py` | Thin — 1 test covering OTP-rejection + one HDFC match; no coverage of `axis_alerts.yaml`/`scapia_federal.yaml`/`upi_gpay.yaml` discovery paths specifically. |
| `ingestion/pipeline.py`, `demo_data.py` | Covered at integration level via `test_phase2.py::test_demo_ingestion_idempotent` (real assertions on dedupe counts) |
| `ingestion/fingerprint.py` | No direct/unit test; only indirectly exercised through the idempotency assertions above |
| `ingestion/gmail/client.py` (`GmailApiSource`) | Never exercised for real — always monkeypatched away. No test of pagination/error handling even against a fake transport. |
| `ingestion/gmail/links.py` | Covered — `test_gmail_links.py` (3 small pure-function tests) |
| `ingestion/gmail/mime.py` | **No test at all.** Contains an untested `except Exception: continue` (ruff `BLE001` at line 40). |
| `ingestion/gmail/oauth.py` | **No direct test of the module itself** — only observed indirectly via `is_connected()`'s return value, which is exactly what's broken above. The PKCE `code_verifier`-persistence logic CLAUDE.md explicitly flags as a "must preserve" gotcha has zero test coverage. |
| `merchants/normalize.py` | **Tautologically thin.** 1 test, 1 assertion (`RAZ*` prefix only). The function also strips `PYU*`, `PAYTM*`, `GPAY*` and has `None`-input / empty-after-strip branches — none of those 5 branches are tested. |
| `classification/enrichment.py` | No test imports this module by name; only reachable indirectly through API/pipeline tests. |
| `services/dashboard.py` | Strong — `tests/test_income_trend.py` (4 tests) directly asserts the sensitive pay-period rules (day 1/2/end-of-month boundaries), plus MoM% and 6-month trend. |
| `services/transactions.py` | Strong — `tests/test_classify.py` (5 tests): classify, transfer flags, bulk, exclude-as-not-a-transaction, direction filter |
| `services/categories.py` | Partial — one test covers `GET`, `POST /`, `POST /{id}/subcategories`, `DELETE /{id}`. `PATCH /{category_id}` (rename) and `DELETE /subcategories/{subcategory_id}` are **not exercised by any test.** |
| `services/date_repair.py` | **No test at all.** Only the lower-level detector it depends on (`dates_look_day_month_swapped`) is tested. |
| `api/routes/{health,overview,system}.py` | Covered by `test_phase1.py` |
| `overview.py`'s `/income-trend` route | Route itself untested — `test_income_trend.py` calls the service function directly, never `GET /api/overview/income-trend`, so route-level param parsing/serialization is unverified. |
| `api/routes/gmail.py` | Only `GET /status`, `GET /messages/{id}`, and the (broken) `POST /sync` are tested. **Zero coverage** of `POST /credentials`, `/credentials/from-path`, `/auth/start`, `GET /oauth/callback`, `/disconnect` — the entire OAuth handshake, the most fragile area per CLAUDE.md's own "Gotchas," has no route-level test. |
| `config.py` (`load_settings`, `_deep_merge`, `_load_yaml`, `reload_settings`) | **No test at all.** Every test builds `Settings(...)` directly in Python; the real YAML-load + `config.local.yaml` deep-merge path is never exercised. |
| `db/{models,session,seed}.py` | Indirectly exercised throughout; no dedicated schema/constraint tests, but reasonably covered via integration tests hitting the DB through the API. |
| `domain/enums.py` | No dedicated test — low risk, pure enum definitions. |
| Top-level CLI scripts: `connect_gmail.py`, `sync_gmail.py`, `reclassify_axis.py`, `reclassify_scapia.py`, `repair_dates.py`, `logging_setup.py`, `__main__.py` | **No tests for any of them.** These wrap operationally important logic CLAUDE.md tells agents to run manually. |

**Tautological / trivial / duplicate findings:**

- `tests/test_normalize.py` — 1 assertion covering 1 of 5 real branches (see above).
- `tests/test_categories_api.py:33-35` — comment says "delete category removes subs" but the test only asserts `status_code == 200`; it never re-fetches to confirm the subcategory is actually gone. The assertion doesn't verify the behavior the comment claims.
- Duplicate assertion across two files: `infer_direction("Refund of INR 100 credited to your account") == "credit"` appears verbatim in both `test_phase2.py:83` and `test_scapia.py:32` — no new signal in the second copy.
- No skipped/xfail/disabled tests found anywhere in the suite.

## Part B — Tooling / scripts audit

**Shebangs/permissions:** all three scripts (`run_server.sh`, `run_dev.sh`, `watch_gmail_credentials.sh`) have `#!/usr/bin/env bash` and are executable. Fine.

**Hardcoded paths:**

- `scripts/run_server.sh:3` hardcodes `ROOT="/Users/gauravsingh/projects/expense-tracker"`, inconsistent with `scripts/run_dev.sh:3`, which correctly computes `ROOT="$(cd "$(dirname "$0")/.." && pwd)"`. Since `run_server.sh` is the one launchd actually invokes, this is arguably intentional for a personal single-user machine, but it means the script cannot be copied/reused and isn't self-relocating like its sibling.
- The real `scripts/launchd/com.personal.expense-tracker.plist` hardcodes `/Users/gauravsingh/...` throughout, but it's internally consistent with `run_server.sh` (same `ROOT`, same log dir matching `run_server.sh`'s `mkdir -p "$LOG_DIR"`).
- `scripts/launchd/com.personal.expense-tracker.plist.example` uses `/Users/YOU/...` placeholders but invokes `.venv/bin/python -m mymonee` **directly**, not via `run_server.sh`. A new user following the example verbatim would get a launchd job with no `mkdir -p` for the log dir first — if `~/Library/Logs/ExpenseTracker/` doesn't already exist, launchd's `StandardOutPath`/`StandardErrorPath` file creation can fail silently. The example has drifted from the wrapper-script pattern the real plist now uses.

**Error handling:**

- `run_server.sh`/`run_dev.sh` both use `set -euo pipefail` — good.
- `watch_gmail_credentials.sh:25` does `curl -s -X POST "http://127.0.0.1:8477/api/gmail/credentials/from-path?..."` with **no `-f`/`--fail` flag and no status check**. `curl -s` only errors on connection failure, not HTTP 4xx/5xx — so if the server returns an error (bad path, malformed credentials JSON), the script still prints "Installed. Run: ..." as if it succeeded.

**`.gitignore` vs. the "never commit credentials" rule:** covers `.env`, `.env.*`, `credentials.json`, `client_secret*.json`, `token.json`, `**/config.local.yaml`, `data/`, `*.db*`. It does **not** match the literal filename referenced everywhere in README/CLAUDE.md/AGENTS.md — `gmail_credentials.json`. This file defaults to living outside the repo (`~/Library/Application Support/ExpenseTracker/`), so it's not a live risk under default config, but a user who ever points `gmail.credentials_file` at a path inside the repo (which the README explicitly offers via `config.local.yaml`) wouldn't have it caught by `credentials.json` or `client_secret*.json`.

**`pyproject.toml` deps vs. actual imports (spot check):** no mismatches found — every third-party import in `src/` maps to a declared dependency. One notable **absence**: `config.py`'s `SchedulerConfig` and ARCHITECTURE.md's stack table advertise **APScheduler**, but `apscheduler` is not in `pyproject.toml` and is not imported anywhere. There is no `scheduler/` package. The config flag exists; the implementation it configures does not (see [01-architecture-and-documentation.md](./01-architecture-and-documentation.md)).

## Part C — Docs-vs-code consistency

Consolidated into [01-architecture-and-documentation.md](./01-architecture-and-documentation.md). In short: `ARCHITECTURE.md`'s folder tree documents several modules that don't exist (`engine/`, `classification/hierarchy.py` et al., `services/stats.py`, `scheduler/jobs.py`) and omits most modules that do; a stale "Phase 1 ships ... empty Transactions" line remains; Phase 6 (launchd) is marked "Later" despite already being built and in use; and `docs/plans/MyMonee_Personal_Finance_Master_Plan.md` describes a conflicting 12-phase roadmap under a different package name that overstates the current state relative to both `ARCHITECTURE.md` and `CLAUDE.md`.
