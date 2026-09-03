# AGENTS.md

Guidance for coding agents working in this repository.

`AGENTS.md` is the short operating contract. For deeper project memory, conventions, commands, and domain-specific details, read `CLAUDE.md`. For architectural decisions and system boundaries, read `ARCHITECTURE.md`.

---

## Mission

Build and maintain **MyMonee**, a **local-first, privacy-first macOS expense tracker**:

**Gmail notification emails → ingestion → durable SQLite ledger → normalization → classification → financial analysis → personal dashboard**

Core principles:

* Local-first.
* SQLite is the durable source of truth.
* No cloud database.
* External AI is **OFF by default**.
* Financial data must not leave the machine unless explicitly enabled by the user.
* Prefer deterministic/local processing before external services or AI.
* Preserve transaction history and auditability.

---

## Operating Rules

### 1. Understand before changing

Before making non-trivial changes:

1. Inspect the relevant existing implementation.
2. Read the applicable sections of `CLAUDE.md`.
3. Read `ARCHITECTURE.md` when the change affects architecture, data flow, persistence, ingestion, classification, or integrations.
4. Follow existing patterns unless there is a concrete reason to change them.
5. Do not invent new abstractions, frameworks, or architectural patterns without justification.

For ambiguous requirements, inspect the codebase first and identify the smallest reasonable interpretation.

---

### 2. Keep changes scoped

* Change only what is necessary for the requested task.
* Do not drive-by refactor unrelated modules.
* Do not rename, move, or rewrite existing components merely for stylistic reasons.
* Preserve existing APIs and behavior unless the task explicitly requires a change.
* Prefer small, reviewable changes over broad rewrites.

---

### 3. Protect financial data

Treat all transaction and financial information as sensitive.

Never:

* Delete transaction history to solve a logic problem.
* Bulk-update or rewrite financial data without understanding the impact.
* Modify production/local ledger data as part of normal development.
* Fabricate transaction records to make tests pass.
* Change transaction amounts, dates, account identifiers, or transaction types merely to satisfy UI expectations.
* Remove historical records without an explicit user request.

If a task requires a data migration, backfill, cleanup, deduplication, or destructive operation:

1. Explain the proposed operation.
2. Identify affected records/data.
3. Prefer a reversible migration.
4. Add tests where practical.
5. Do not execute destructive production-like operations without explicit approval.

---

### 4. Preserve the local-first architecture

Do not introduce cloud infrastructure, hosted databases, or external data services unless explicitly requested.

In particular:

* SQLite remains the durable local ledger.
* Do not introduce MongoDB, Firebase, Supabase, or another cloud database.
* Do not move financial data into an external service.
* Do not enable external AI by default.
* Do not send transaction contents to an external API without explicit configuration and user intent.
* Keep privacy-sensitive processing local whenever practical.

---

### 5. Match existing project patterns

Backend:

```text
src/mymonee/
```

Frontend:

```text
web/src/
```

Use existing utilities, services, models, API patterns, error handling, and configuration mechanisms before introducing alternatives.

Do not introduce a second way of solving an existing problem unless the existing approach is demonstrably unsuitable.

---

## Architecture Pointers

| Area                          | Location                                       |
| ----------------------------- | ---------------------------------------------- |
| HTTP API                      | `src/mymonee/api/routes/`              |
| Sync pipeline                 | `src/mymonee/ingestion/`               |
| Parsers                       | `src/mymonee/parsers/`                 |
| Provider parser configuration | `config/providers/`                            |
| Classification enrichment     | `src/mymonee/classification/`          |
| Dashboard metrics             | `src/mymonee/services/dashboard.py`    |
| Manual classification         | `src/mymonee/services/transactions.py` |
| React UI                      | `web/src/pages/`, `web/src/components/`        |
| Tests                         | `tests/`                                       |
| Maintenance scripts           | `scripts/`                                     |
| Local configuration template  | `config/local.example.yaml`                    |

Full architecture:

```text
ARCHITECTURE.md
```

Project commands and domain-specific gotchas:

```text
CLAUDE.md
```

---

## Financial Domain Rules

Be especially careful with calculations involving:

* Income
* Expenses
* Transfers
* Credit cards
* Credit-card payments
* Refunds
* EMIs
* Duplicates
* Cross-account transfers
* Salary/pay-period attribution
* Transaction categorization

Never assume that every financial transaction represents an economic expense.

For example:

```text
Credit card purchase
        ↓
Expense

Credit card bill payment
        ↓
Transfer / settlement
        ↓
NOT another expense
```

Similarly, transfers between the user's own accounts should not inflate income or expenses.

When changing financial calculations:

* Identify whether the value represents an economic event or an account movement.
* Check for double-counting.
* Check refunds and reversals.
* Check cross-account transfers.
* Add or update regression tests.

---

## Classification

Classification is expected to improve over time from user corrections.

Current priority:

**Persist merchant → category rules from Needs Review.**

When implementing classification changes:

* Preserve user corrections.
* Prefer deterministic merchant/category rules before probabilistic classification.
* Do not overwrite an explicit user classification without a defined rule.
* Make classification behavior deterministic and testable where possible.
* Add regression tests for previously corrected transactions.

---

## Data Integrity

For changes involving ingestion, deduplication, refunds, transfers, or transaction updates:

* Prefer idempotent operations.
* Preserve source identifiers and provenance.
* Do not silently discard ambiguous records.
* Make duplicate detection explainable.
* Preserve enough information to investigate why a transaction was classified or matched in a particular way.

Current Phase 3 priorities:

1. Stronger deduplication.
2. Refund pairing.
3. Cross-account transfer matching.

---

## API Rules

When modifying APIs:

* Preserve backwards compatibility unless explicitly requested otherwise.
* Follow existing route and response patterns.
* Validate input at the API boundary.
* Return predictable error responses.
* Do not expose secrets or sensitive configuration.
* Do not introduce a new API pattern when an existing one already handles the requirement.

If an API change affects the React UI, update both sides and verify the complete flow.

---

## UI Rules

The UI is a React application under:

```text
web/
```

Follow existing component, page, state-management, styling, and API-client patterns.

Do not introduce another frontend framework.

After UI changes:

```bash
cd web
npm run build
```

The FastAPI application serves the built UI, so a source-only UI change is incomplete until the production build has been regenerated.

---

## Tests

After Python logic changes:

```bash
source .venv/bin/activate
pytest
```

Money, classification, ingestion, deduplication, refund, transfer, and dashboard changes should have appropriate tests under:

```text
tests/
```

When fixing a bug:

1. Reproduce it with a test where practical.
2. Implement the fix.
3. Run the relevant test.
4. Run the broader test suite.

Do not modify tests merely to make an incorrect implementation pass.

---

## Build Verification

For frontend changes:

```bash
cd web
npm run build
```

For backend changes:

```bash
source .venv/bin/activate
pytest
```

For changes spanning frontend and backend, run both.

After shipping backend or built-UI changes, restart the local/launchd server or restart the backend server manually. To run the backend server locally for verification:

```bash
source .venv/bin/activate
python -m mymonee
```

---

## Scripts

All ad-hoc scripts must live under:

```text
scripts/
```

Do not create temporary Python, SQL, shell, or data-cleanup scripts in the repository root.

Before creating a new script, check whether an existing script already solves the problem.

Scripts that modify financial data should:

* Clearly state what they modify.
* Prefer dry-run support.
* Provide useful logging.
* Avoid irreversible operations by default.

---

## Security and Secrets

Never commit:

```text
gmail_credentials.json
.env
tokens
API keys
OAuth credentials
Keychain dumps
SQLite databases
local configuration
launchd plist files
```

Use:

```text
config/local.example.yaml
```

as the safe configuration template.

Never print credentials, OAuth tokens, access tokens, or sensitive transaction contents into logs or test output.

---

## Git & Branching Workflow

* Always work on short-lived feature or fix branches branched from `main`:
  ```bash
  git checkout -b feat/<topic>   # or fix/<topic>
  ```
* Do not commit directly to `main`. `main` represents the stable code running in your local daemon.
* Use **Conventional Commits**:
  - `feat(...)`: new capability, tool, or endpoint
  - `fix(...)`: bug or calculation fix
  - `test(...)`: new tests or benchmark cases
  - `refactor(...)`: structural change without behavior modification
  - `docs(...)`: documentation or developer memory updates
* Inspect `git status` and review diffs before staging.
* Do not commit or push automatically; only when the user explicitly requests or approves.
* Open Pull Requests using `gh pr create` and merge to `main` via squash merge (`gh pr merge --squash --delete-branch`).
* Deploy to live daemon using explicit release script: `./scripts/deploy_local.sh`.

---

## Quality Gates & Validation Tiers

### Level 1 — Automatic Pre-Push (~4 seconds)
Before pushing, the pre-push Git hook (`scripts/git-pre-push.sh`) automatically runs:
- `ruff check` on modified Python files
- `ruff format --check` on modified Python files
- `pytest -q -m "not hermes"` (fast unit & invariant tests)

Never bypass the pre-push hook (`--no-verify`) unless explicitly instructed by the user.

**Legacy Formatting Rule**: Do not reformat legacy code merely to satisfy the workflow. Legacy files become compliant naturally when they are modified.

### Level 2 — Feature-Level Validation
Run:
```bash
./scripts/qa_mcp_hermes.sh
```
when changes affect:
- MCP tools or server architecture
- Hermes Agent integration or skills
- Transaction classification or corrections learning
- Ledger logic or database schema
- Financial calculations (income, spending, transfers, refunds, salary)
- Security or privacy boundaries (sanitizer, canaries, read-only pragma)

### Level 3 — Release & Local Daemon Deployment
Run:
```bash
./scripts/deploy_local.sh
```
Only after merging to `main`. This script verifies working tree cleanliness, synchronization with remote, compiles the frontend bundle, kickstarts the local macOS `launchd` daemon, and verifies the API health check.

**Automated Continuous Deployment (CD)**:
Pull requests merged into `main` automatically trigger local deployment via Hermes Webhook calling `./scripts/trigger_deploy.sh` (enforcing strict tree cleanliness and branch guardrails).

### Frontend Changes
When `web/` is modified, always rebuild the bundle:
```bash
cd web && npm run build
```

### Completion Standard
Do not declare a task complete while applicable quality checks are failing.

---

## Execution & Tool Permissions

The agent has full user authorization in this workspace to run:
* **Python Runtime & Tests**: `.venv/bin/python`, `source .venv/bin/activate`, `pytest`.
* **SQLite Operations**: `sqlite3`, `./scripts/db.sh`, `scripts/*.py`.
* **Frontend Builds**: `npm run build`, `npm test` in `web/`.
* **Daemon Management**: `launchctl kickstart -k "gui/$(id -u)/com.personal.my-monee"`.
* **Git Operations**: `git status`, `git diff`, `git log`, and explicitly requested commits.

---

## Current Priorities

These are current project priorities, not permanent architectural rules.

### P1 — Learn from corrections

Persist merchant → category rules from **Needs Review**.

### P2 — Phase 3

Improve:

* Deduplication
* Refund pairing
* Cross-account transfer matching

### P3 — Income attribution

Keep **Axis `/Sala` salary** and pay-period income attribution correct.

When working on unrelated tasks, do not modify these areas unless necessary.

---

## Completion Standard

A task is not complete merely because the code was changed.

Before reporting completion:

1. Verify the implementation against the requested behavior.
2. Run relevant tests.
3. Rebuild the frontend when UI code changed.
4. Inspect the resulting diff.
5. Check for accidental files, debug code, secrets, or unrelated changes.
6. Report any tests or verification steps that could not be run.

When there is uncertainty, state it explicitly rather than claiming the task is verified.

---

## Agent Behavior

Prefer this sequence:

```text
Understand
    ↓
Inspect existing implementation
    ↓
Identify affected components
    ↓
Plan smallest change
    ↓
Implement
    ↓
Test
    ↓
Build
    ↓
Review diff
    ↓
Report
```

Do not:

```text
Guess → Rewrite → Refactor → Hope it works
```
