# Expense Tracker — Design & Code Review

**Date:** 2026-08-12
**Scope:** Full repository — backend (`src/mymonee/`), frontend (`web/src/`), tests (`tests/`), tooling (`scripts/`, `pyproject.toml`), and documentation (`ARCHITECTURE.md`, `README.md`, `CLAUDE.md`, `AGENTS.md`, `docs/plans/`).
**Method:** Four independent deep-dive passes (backend/API/DB, ingestion/parsers/classification, frontend, testing/tooling/docs-consistency), each reading every file in scope in full. Several findings were confirmed by actually executing the relevant code against constructed inputs rather than by inspection alone — those are marked accordingly in each report.

This review is descriptive, not prescriptive: it reports what the code and docs currently do, with evidence, so you can decide what to fix and in what order. Nothing has been changed in the codebase as part of this review.

## How to read this

| Doc | Covers |
|---|---|
| [00-prioritized-action-list.md](./00-prioritized-action-list.md) | **Start here.** Every finding across all areas, merged and sorted by severity. |
| [01-architecture-and-documentation.md](./01-architecture-and-documentation.md) | ARCHITECTURE.md vs. actual code, roadmap consistency, the conflicting `docs/plans/` master plan |
| [02-backend-api-and-data.md](./02-backend-api-and-data.md) | FastAPI app, routes, DB models/session, dashboard/transactions/categories services |
| [03-ingestion-parsers-classification.md](./03-ingestion-parsers-classification.md) | Gmail OAuth/sync pipeline, parser plugins (Axis/Scapia/generic/rule-based), classification enrichment |
| [04-frontend.md](./04-frontend.md) | React/TypeScript dashboard — correctness, accessibility, design-system adherence |
| [05-testing-and-tooling.md](./05-testing-and-tooling.md) | Test coverage, actual `pytest`/`ruff` run results, scripts, launchd, packaging |

## Executive summary

The codebase is generally clean, well-typed on both sides, and free of the most common footguns (no SQL injection, no `any` in the frontend, no secrets in logs, sensible SQLite pragmas, real idempotency via a DB-level unique constraint). The team has clearly been disciplined about the domain-specific rules in `CLAUDE.md` in the *common* case.

The findings cluster into three themes:

1. **Edge cases in the domain rules the project cares most about are not fully handled.** The Axis salary-vs-transfer classification, the salary pay-period shift, and the generic/YAML parser's amount extraction all have concrete inputs (verified by running the code) that produce silently wrong financial data — not crashes, wrong numbers. This is the highest-value area to fix given the app's purpose.
2. **A handful of real security gaps**, appropriate to flag even for a single-user localhost app: a reflected-XSS hole in the OAuth callback page, a path-traversal bug in the SPA static-file fallback, and CSRF-exploitable mutating endpoints (including one that reads an arbitrary local file path). None require internet exposure to matter — a malicious webpage open in any browser tab on the same Mac can reach `127.0.0.1:8477`.
3. **Documentation has drifted well ahead of and behind the code simultaneously.** `ARCHITECTURE.md` describes modules (`engine/`, `classification/hierarchy.py`, `scheduler/jobs.py`, `services/stats.py`) that were never built, while omitting most modules that *were* built (every real parser, `categories.py`, `gmail.py` routes, all five CLI scripts). A separate 12-phase master plan in `docs/plans/` uses a different package name (`mymonee`) and claims capabilities (a "learning-oriented classification engine") that don't exist anywhere in the code. There is no single source of truth for "what phase are we actually in."

### Findings by severity

| Area | Critical | High | Medium | Low |
|---|---|---|---|---|
| Backend / API / DB | 1 | 3 | 5 | 5 |
| Ingestion / Parsers / Classification | 2 | 2 | 3 | 3 |
| Frontend | 0 | 2 | 3 | 7 |
| Testing / Tooling | 1 | 1 | 3 | 4 |
| **Total** | **4** | **8** | **14** | **19** |

Full detail, file:line references, and repro scenarios are in the linked docs. The five items worth fixing first:

1. **[Critical]** Reflected XSS in `GET /oauth/callback` — an attacker-controlled `error` query param is rendered into HTML unescaped, giving full read/write access to the app's API. → [02, finding 1](./02-backend-api-and-data.md)
2. **[Critical]** `GenericHeuristicParser` picks the *largest* rupee amount in an email as the transaction amount — for common "available balance" phrasing, this records the account balance instead of the spend. Affects every bank onboarded via YAML-only rules (HDFC, UPI/GPay). → [03, finding 1](./03-ingestion-parsers-classification.md)
3. **[Critical]** A bare `"salary"` keyword anywhere in an Axis email's subject/body/HTML (e.g. marketing boilerplate) is enough to classify a non-salary credit as income, feeding the salary pay-period shift. → [03, finding 2](./03-ingestion-parsers-classification.md)
4. **[Critical]** The test suite hangs indefinitely on a real, live Gmail API call because `is_connected()` reads the developer's actual macOS Keychain entry instead of a test double — and separately, `pytest` currently has one failing test. → [05, Part A](./05-testing-and-tooling.md)
5. **[High]** "Current month" for the Overview and salary pay-period logic is computed from `datetime.now(timezone.utc)`, not the user's local calendar day — for ~5.5 hours every day (00:00–05:29 IST), the dashboard reports the wrong month. → [02, finding 3](./02-backend-api-and-data.md)

See [00-prioritized-action-list.md](./00-prioritized-action-list.md) for the complete, sorted list.
