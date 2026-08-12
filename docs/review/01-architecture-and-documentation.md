# Architecture & Documentation Review

Scope: `ARCHITECTURE.md`, `README.md`, `CLAUDE.md`, `AGENTS.md`, `.cursor/rules/*.mdc`, `docs/plans/MyMonee_Personal_Finance_Master_Plan.md`, compared against the actual file tree and behavior established by the other three reviews.

## Summary

`CLAUDE.md` and `AGENTS.md` are accurate, current, and appropriately scoped — they describe directories rather than exhaustive file lists and don't claim things the code doesn't do. `ARCHITECTURE.md`, by contrast, has drifted significantly in both directions: it documents modules that were never built, and omits most of the modules that actually exist. A separate long-form plan under `docs/plans/` describes a different, more ambitious rewrite under a different package name, with its own roadmap that disagrees with the other two.

The `.cursor/rules/*.mdc` files (gmail-oauth, services, frontend, parsers, project) are short, scoped, and consistent with `CLAUDE.md`'s domain rules — no contradictions found there.

## Findings

### `ARCHITECTURE.md` §3's folder tree vs. the real tree

**Documented but does not exist:**
- `src/expense_tracker/engine/{dedupe.py,refunds.py,transfers.py}` — no such folder. Whatever dedupe/refund/transfer logic exists lives ad hoc inside `parsers/axis.py`'s `classify_axis_credit`, not in a dedicated engine layer, which also means it's bank-specific rather than the source-independent design the doc implies.
- `src/expense_tracker/classification/{hierarchy.py,rules.py,historical.py,ai.py}` — the real `classification/` package contains only `enrichment.py`, which the doc never mentions. There is no rules engine, no historical-match layer, and no AI/ML hook — Phase 5's "Personal model" premise has no scaffolding yet.
- `src/expense_tracker/services/stats.py` — doesn't exist.
- `src/expense_tracker/scheduler/jobs.py` — doesn't exist. Consistent with this: `pyproject.toml` doesn't depend on `apscheduler`, and no code imports it, even though ARCHITECTURE.md §2's stack table lists APScheduler as chosen technology. The `SchedulerConfig` in `config.py` (`enabled`, `interval_minutes`) is a config surface with nothing behind it.

**Exists but undocumented in the §3 tree:**
- `api/routes/categories.py`, `api/routes/gmail.py` (doc lists only health/overview/transactions/system).
- `ingestion/fingerprint.py`, `ingestion/demo_data.py`.
- Every real parser plugin — `parsers/bootstrap.py`, `extract.py`, `generic.py`, `rule_parser.py`, `axis.py`, `scapia.py` (doc's tree shows only `base.py`/`registry.py`).
- `services/categories.py`, `date_repair.py`, `transactions.py` (doc lists only `dashboard.py` and the nonexistent `stats.py`).
- Five operational CLI entry points that `CLAUDE.md`'s own "Gotchas" section tells agents to run manually: `connect_gmail.py`, `sync_gmail.py`, `reclassify_axis.py`, `reclassify_scapia.py`, `repair_dates.py`.
- `config/providers/` is shown holding only `.gitkeep`; it actually holds five real rule files (`axis_alerts.yaml`, `discovery.yaml`, `hdfc_alerts.yaml`, `scapia_federal.yaml`, `upi_gpay.yaml`).

### Stale status claims

- **ARCHITECTURE.md §13** ("Dashboard Information Architecture"), closing line: *"Phase 1 ships Overview shell + empty Transactions + System health."* Transactions is no longer empty — it's a searchable, filterable table with a Needs Review queue and bulk-classify panel. Stale.
- **Phase 6** ("launchd, Keychain hardening, backup/restore, performance") is marked "Later"/blank in both roadmap tables, but the launchd plist and `run_server.sh` already exist and are the documented way to run the app long-term — `CLAUDE.md`'s own Commands section references `launchctl kickstart -k "gui/$(id -u)/com.personal.expense-tracker"`. The launchd portion of Phase 6 is already built and in active use; its "Later" status is wrong.
- The stack table's APScheduler entry (§2) is aspirational, not implemented — see above.

### `CLAUDE.md` vs. `ARCHITECTURE.md` §16 roadmap tables

These two **agree** with each other: same phase count, ordering, and status wording (Phase 1/2 Done, Phase 3 "Next (partial Axis transfer/refund)", Phase 4 "In progress", Phases 5–6 not started). No contradiction between them.

### `docs/plans/MyMonee_Personal_Finance_Master_Plan.md` — a third, conflicting roadmap

This is a long (2,696-line) planning document describing an entirely different **12-phase** plan (Phase 1 "Foundation" through Phase 12 "Native macOS Experience" — net worth tracking, budgeting, loans/investments, an AI assistant), under a **renamed package** `src/mymonee/` with its own module layout (`reconciliation/`, `finance/`, `intelligence/`) that matches neither the real code nor `ARCHITECTURE.md`'s proposed layout.

Its own framing overstates the current state more than either of the other two docs: it lists as **"Current foundation"** *"transaction normalization, classification, deduplication, refunds/transfers, and a learning-oriented classification engine"* — but:
- there is no `engine/dedupe.py`/`refunds.py`/`transfers.py` (see above),
- there is no "learning-oriented classification engine" module — classification today is a single rule-based function (`classify_axis_credit`) plus manual/bulk user classification,
- `CLAUDE.md` itself says learn-from-corrections (the actual "learning" piece) is **not yet built** ("Next product work: learn-from-corrections").

A reader who opened all three documents cold would get three different, mutually irreconcilable answers to "what phase is this project in and what's already built."

## Recommendation

You don't need three roadmap documents. Suggested resolution, roughly in order of effort:

1. Decide whether `docs/plans/MyMonee_Personal_Finance_Master_Plan.md` is an active target or a superseded exploration. If active, it needs to either replace or explicitly subordinate `ARCHITECTURE.md`'s roadmap and package layout; if superseded, move it somewhere clearly marked as historical (e.g. `docs/plans/archive/`) so it stops reading as current intent.
2. Regenerate `ARCHITECTURE.md` §3's folder tree from the actual `src/expense_tracker` tree (it's short enough to hand-verify) and delete the aspirational `engine/`/`classification/hierarchy.py` etc. entries, or explicitly label them "planned, not yet started" instead of presenting them as existing structure.
3. Fix the two stale status lines called out above.
4. `CLAUDE.md` is the accurate, current source of truth today — keep new agent-facing changes there first, and treat `ARCHITECTURE.md` updates as a periodic sync rather than the primary place changes land.
