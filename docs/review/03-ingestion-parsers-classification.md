# Ingestion, Parsers & Classification Review

Scope: `ingestion/{pipeline,discovery,fingerprint,demo_data}.py`, `ingestion/gmail/{client,oauth,links,mime}.py`, `parsers/{base,registry,bootstrap,extract,generic,axis,scapia,rule_parser}.py`, `classification/enrichment.py`, `merchants/normalize.py`, `connect_gmail.py`, `sync_gmail.py`, `reclassify_axis.py`, `reclassify_scapia.py`, `repair_dates.py`, `config/default.yaml`, `config/providers/*.yaml`.

Several findings below were confirmed by directly executing the actual project code (`classify_axis_credit`, `GenericHeuristicParser.parse`, `DiscoveryRules.is_financial_candidate`, and the raw `SALARY_REF`/`CHANNEL_REF` regexes) against constructed inputs, not just by reading it.

## Strengths

- **Clean plugin protocol**: `parsers/base.py`'s `ParserPlugin` Protocol (`can_parse`/`parse`) and `parsers/registry.py`'s confidence-based `choose()` are simple and genuinely decoupled from `ingestion/pipeline.py` — the pipeline contains zero bank-specific string literals, matching ARCHITECTURE.md's claim at the pipeline level.
- **Idempotent persistence with a real DB-level guard**: `_persist_parsed` in `pipeline.py:174-230` checks by fingerprint, then by `(source_email_id, reference_number)`, and `db/models.py:185-189` backs it with a genuine `UniqueConstraint("source", "fingerprint")` — re-running sync on already-seen mail does not create duplicate rows.
- **Amount regex correctly handles the documented `INR .52` edge case** (`extract.py:12-21`, alternation branch `\.[0-9]+`), and `UPILITE` is present in both `CHANNEL_REF` (`axis.py:21`) and `REF_PATTERNS` (`extract.py:42`) as required — confirmed via `tests/test_axis_salary.py::test_axis_parser_upilite_leading_decimal`.
- **OAuth scope is correctly minimal**: `config/default.yaml:28` declares only `gmail.readonly`, and no code path requests a broader scope; no secret/token values are ever passed to `logger.*` calls.
- **PKCE plumbing itself is correct**: `start_oauth`/`complete_oauth` (`oauth.py:157-214`) properly persist and restore `code_verifier` across the request/callback split, and state mismatches fail loudly (`GmailAuthError`) rather than silently proceeding.
- **Category/subcategory slugs referenced by `axis.py`'s enrichment dicts** (`income`/`salary`, `transfers`/`credit-card-payment`, `income`/`refund`) all exist in `db/seed.py`'s `DEFAULT_CATEGORIES` — no drift there.
- **MIME/base64 decoding (`gmail/mime.py`) is straightforward and correct** for Gmail API's already-decoded `body.data` fields; no unsafe HTML execution, BeautifulSoup used only for text extraction.

## Findings

**1. [Critical] Generic/YAML-driven extraction can record account balance as the transaction amount — `parsers/generic.py:46`**

```python
amount = max(amounts) if len(amounts) > 1 and max(amounts) >= 1 else amounts[0]
```

This picks the *largest* number-with-currency-symbol in the email. This code path backs not only the pure fallback parser but every `ProviderRuleParser` (`rule_parser.py:45`: `parsed = self._fallback.parse(email)`), which is how HDFC and other YAML-only providers are parsed.

Verified by direct execution: for `"Rs.1,250.00 was spent on your HDFC Bank Card XX1234 ... Avl bal: Rs.45,231.00"`, `GenericHeuristicParser().parse(...)` returns `amount=Decimal('45231.00')` instead of `1250.00`. "Available balance" phrasing is standard in Indian bank alerts, so this silently corrupts spend amounts for any bank onboarded via the documented YAML-only extensibility path.

*Fix:* prefer the amount nearest the debit/credit keyword (or the first amount before any "bal"/"balance" label), not `max()`.

**2. [Critical] Bare "salary" keyword anywhere in the email misclassifies non-salary Axis credits as income — `parsers/axis.py:73`**

`classify_axis_credit` builds `blob = f"{channel_ref or ''} {text}"` (full subject+body+HTML) and checks `re.search(r"\bsalary\b", blob, re.I)` as a fallback. Verified by direct execution: a UPI/P2A transfer of INR 99 to "APPLE MED", with an added footer line "Axis Bank Salary Accounts come with zero balance...", is classified `transaction_type="income"` via rule `axis_neft_sala_salary` instead of `"transfer"`. This directly violates the CLAUDE.md rule "Other Axis credits → transfer/refund/needs_review — not income" and would leak into pay-period income totals whenever such marketing boilerplate is present.

*Fix:* restrict the fallback check to `channel_ref` only, not the whole email blob.

**3. [High] Declined-card alerts are filtered out before they ever reach the parser, making `axis.py`'s dedicated handling dead code in production — `config/providers/discovery.yaml:51` + `ingestion/discovery.py:67-69` + `ingestion/pipeline.py:331-344`**

`discovery.yaml`'s `exclude_subject_patterns` includes `"transaction declined"`. Verified by direct execution: `DiscoveryRules.is_financial_candidate()` on the exact subject used in `tests/test_axis_salary.py::test_axis_declined_card_alert_is_excluded` returns `(False, "excluded_subject")`. In the real pipeline this means `registry.choose()`/`plugin.parse()` is never invoked for declined-transaction emails — `axis.py`'s `DECLINED_ALERT`/`is_axis_declined_alert` logic (confidence 0.98, produces a `not_a_transaction` row with `needs_review=False`) only ever runs inside a unit test that calls the parser directly, bypassing discovery. In production these emails are simply skipped with no transaction created at all.

*Fix:* remove or narrow the `"transaction declined"` exclude pattern (e.g., don't exclude when the sender matches a known bank provider hint).

**4. [High] `SALARY_REF` is too strict for realistic multi-segment narrations and breaks entirely on stray whitespace around slashes — `parsers/axis.py:24` (`SALARY_REF`) and `:21` (`CHANNEL_REF`)**

Verified by direct regex execution:
- `"NEFT/N123/ACME CORP/Sala"` (a plausible employer-name-in-narration format) does **not** match `SALARY_REF` — it requires exactly `(NEFT|IMPS|RTGS)/<alnum>/Sala` with no room for an intervening segment — so a genuine salary credit falls through to the non-salary transfer branch (`needs_review=True`, category `transfers`).
- `"NEFT / CHASH00053023262 / Sala"` (spaces around slashes, plausible after HTML→text conversion) matches **neither** `SALARY_REF` nor `CHANNEL_REF`, so `channel_ref` is `None` and the bare-word fallback also fails (text says "Sala", not "salary").

*Fix:* allow an optional intervening segment in `SALARY_REF`, and normalize whitespace around `/` (e.g. `re.sub(r"\s*/\s*", "/", blob)`) before matching.

**5. [Medium] Axis-parser precedence is a same-score tie-break, not an enforced guarantee — `parsers/registry.py:16-26`**

`choose()` picks whichever plugin returns the strictly-highest `can_parse()` score; `priority` only controls registration/iteration order, which matters only because of the strict `>` comparison. Today `AxisBankParser` (priority 90) and the YAML-driven `ProviderRuleParser` for `axis_alerts` (priority 85) both score `0.95` on a typical Axis alert, and `AxisBankParser` wins purely because it's iterated first. If an Axis subject variant doesn't match `AxisBankParser`'s own keyword regex (`axis.py:154-160`, falling back to score `0.6`), while `axis_alerts.yaml`'s sender/body patterns still hit (`ProviderRuleParser` scoring up to `0.95`), the generic-extraction parser wins outright — silently losing all salary/transfer/refund intelligence for that email (and inheriting Finding 1's amount bug).

*Fix:* have `registry.choose()` break ties by `priority` explicitly, or cap `ProviderRuleParser`'s score below any bank-specific plugin registered for the same provider.

**6. [Medium] Provider YAML's "salary" pattern is decorative — unused by the actual classifier — `config/providers/axis_alerts.yaml:16`**

`body_patterns: - "neft/[a-z0-9]+/sala"` looks like the salary-detection rule but is only consumed by `discovery.py`'s `ProviderHint.score` for provider *detection*, never by `classify_axis_credit`, which uses its own separate, stricter, hardcoded `SALARY_REF` in `axis.py`. Editing the YAML to fix Finding 4 would have zero effect on real classification — a maintainer trap, and a concrete contradiction of ARCHITECTURE.md's "ingestion never embeds bank-specific logic" / config-driven framing for the classification layer.

**7. [Medium] Second concurrent "Connect Gmail" click silently destroys the first OAuth flow's PKCE verifier — `ingestion/gmail/oauth.py:127-134`**

`_save_oauth_pending` unconditionally overwrites the single Keychain slot (`STATE_ACCOUNT`) holding `state`/`code_verifier`/`redirect_uri`. If `start_oauth()` is called twice before the first callback lands (double-click, second tab), the first flow's `code_verifier` is gone; that tab's eventual `complete_oauth()` call fails with "OAuth state mismatch" — a safe but confusing failure with no explanation of the actual cause.

*Fix:* detect an existing pending flow and either reject the new `start_oauth()` or key pending state by `state` value so multiple in-flight flows can coexist.

**8. [Low-Medium] Declared privacy config flags are never enforced anywhere — `config/default.yaml:36-38` (`store_raw_email_bodies`, `mask_identifiers`)**

Unlike `allow_external_ai`, these two settings are never read/consumed by any reviewed code — no raw-body archival gating, no identifier masking. The config implies a privacy guarantee that the code doesn't actually implement either way.

**9. [Low] `reclassify_axis.py` / `reclassify_scapia.py` hardcode bank queries instead of deriving from provider YAML — `reclassify_axis.py:19-23`, `reclassify_scapia.py:19-23`**

`AXIS_CREDIT_QUERY`/`SCAPIA_QUERY` are Python string constants duplicating sender/subject info already in `config/providers/axis_alerts.yaml` / `scapia_federal.yaml`. Unlike the main sync path (`discovery.py`), these CLI backfill tools won't pick up YAML changes (e.g. a renamed alert subject), silently under-fetching on future backfills.

**10. [Low] No advisory lock around concurrent sync runs; `SyncState` upsert is check-then-act — `ingestion/pipeline.py:43-51`**

`_set_sync` does `session.get()` then insert-or-update with no locking. Transaction-row duplication is protected by the DB-level `UniqueConstraint("source","fingerprint")` and SQLite's single-writer lock, but a second overlapping sync run (manual trigger while the launchd job is running) can hit an unhandled `IntegrityError`/"database is locked", which propagates through `sync_gmail.py`'s bare `except: rollback(); raise`, aborting the whole run with a raw DB error instead of a clear "sync already in progress" message.
