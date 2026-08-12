# Frontend Review

Scope: `web/src/{api,App,format,main}.ts(x)`, `web/src/hooks/useModalChrome.ts`, `web/src/components/{ClassifyPanel,EmailViewerModal,IncomeTrendModal}.tsx`, `web/src/pages/{OverviewPage,SettingsPage,TransactionsPage}.tsx`, `web/src/styles.css`, `web/package.json`.

## Strengths

- **Type safety is genuinely clean**: zero `any`, zero `@ts-ignore`/`@ts-expect-error`, zero unsafe casts anywhere in `web/src`. `api.ts` gives every endpoint a concrete response type and every page consumes it without escape hatches.
- **All network I/O goes through `api.ts`** — no stray `fetch(` calls found outside it. No inconsistent bypasses.
- **No silent `catch {}` blocks** in page/component logic — every async handler in `TransactionsPage.tsx`, `OverviewPage.tsx`, and (with one exception, see Findings) `SettingsPage.tsx` sets an error state that gets rendered. The one intentional empty catch (`api.ts:154-156`, swallowing a JSON-parse failure on an already-erroring response) is appropriate.
- **Debit/credit signal is not color-only**: every amount is prefixed with `+`/`−` (`TransactionsPage.tsx:346`, `ClassifyPanel.tsx:90-91`) in addition to red/green, so colorblind users still get a non-color cue.
- **`EmailViewerModal` sandboxes untrusted email HTML correctly**: `sandbox=""` (`EmailViewerModal.tsx:113`) is the most restrictive setting, blocking script execution and same-origin access for arbitrary bank/UPI email HTML rendered via `srcDoc`.
- **React list keys are all stable domain IDs** (`tx.id`, `cat.id`, `sub.id`, `${year}-${month}`) — no index-based keys anywhere.
- **`useModalChrome`/`useBackdropClose` is a well-factored, reused abstraction** for scroll-lock, Escape-to-close, and "ignore the opening click" backdrop behavior — genuinely DRY across all three modals.
- **On-brand visual identity**: the teal/slate palette, serif display font for numerals, and soft blur panels do not match the "purple gradient / cream+terracotta AI slop" anti-pattern called out in CLAUDE.md. The gradient background (`styles.css:34-38`) is restrained and on-theme.

## Findings

**High — `pages/TransactionsPage.tsx:44` + `api.ts:168-181`: Transactions list has no pagination; anything past the first 50/100 rows is unreachable.**

`api.transactions()` never sends an `offset`, and the backend (`api/routes/transactions.py:38-39`) explicitly supports `offset` (up to `limit=200`). The UI hardcodes `limit: needsReview ? 100 : 50` (line 44) and only renders "Showing {items.length} of {total}" (lines 406-408) with no next-page/load-more control anywhere.

*Failure scenario:* once a user has synced more than 50 transactions (trivial after a couple of weeks of Gmail ingestion), the Transactions ledger silently caps at the newest 50 rows — anything older is invisible except by typing an exact merchant search term that happens to narrow the result set below the cap. Directly contradicts the page's own copy, "Searchable ledger of normalized transactions."

*Fix:* add offset-based "Load more" / page controls in `TransactionsPage.tsx` and thread `offset` through `api.transactions()`.

**High — `pages/TransactionsPage.tsx:37-52` (used at line 220 for search input): search/filter fetches race, with no cancellation.**

`load()` (lines 37-52) is called from a `useEffect` keyed on `[needsReview, q, directionFilter]` (lines 54-56), and `q` updates on every keystroke with no debounce (`onChange={(e) => setQ(e.target.value)}`, line 220). Unlike `OverviewPage.tsx`'s effect (lines 15-29), which guards with a `cancelled` flag, `load()` has no `AbortController` and no staleness check.

*Failure scenario:* typing "amazon" fires 6 overlapping requests for "a", "am", "ama", … "amazon". If the response for "ama" resolves after the response for "amazon" (plausible under any DB/network jitter — note CLAUDE.md's own gotcha about SQLite lock contention), the table and `total` get overwritten with the stale, wrong-filtered result and nothing corrects it.

*Fix:* debounce the search input, and/or track a request id / use `AbortController` in `load()` and ignore out-of-order responses, mirroring the pattern already used in `OverviewPage.tsx`.

**Medium — `pages/SettingsPage.tsx:413`: "Refresh status" button swallows fetch errors with no user feedback.**

`onClick={() => void refresh()}` calls `refresh()` (lines 35-44) directly with no `.catch`. Contrast with the mount-time call at line 47, `refresh().catch((err: Error) => setError(err.message))`, which does handle failure. `refresh()` itself has no internal try/catch.

*Failure scenario:* user clicks "Refresh status" while the local API is briefly unreachable (e.g., mid-restart of the launchd service). The promise rejects, becomes an unhandled rejection, and the button just does nothing visible — no error banner, no busy indicator (this button never calls `setBusy`, unlike every other action on the page).

*Fix:* `onClick={() => void refresh().catch((err: Error) => setError(err.message))}`, and give it a busy state like the other buttons.

**Medium — `hooks/useModalChrome.ts:12-33`, used by `ClassifyPanel.tsx:33`, `EmailViewerModal.tsx:28`, `IncomeTrendModal.tsx:121`: modals have no focus trap.**

`useModalChrome` sets initial focus and closes on Escape, but never constrains Tab order to within the dialog, and the background content is never marked `inert`/`aria-hidden`.

*Failure scenario:* a keyboard user opens the "Classify" panel from Needs Review, presses Tab repeatedly, and tabs straight out of the dialog into the top nav / other page controls still in the DOM and focusable underneath the (visual-only) backdrop, while the modal remains open on screen. This is exactly the kind of flow CLAUDE.md flags as needing to be keyboard-friendly.

*Fix:* add a focus-trap loop in `useModalChrome` (cycle Tab/Shift+Tab within the panel's focusable elements) or mark `#root`'s non-modal content `inert` while a modal is open.

**Medium — `pages/SettingsPage.tsx:95,101,259`: sync-to-2026 is hardcoded, not date-derived.**

`syncGmail(true)` sets `afterDate: "2026/01/01"` (line 101) and the button is permanently labeled "Sync 2026 dataset" (line 259) / busy key `"sync2026"` (line 95).

*Failure scenario:* come January 2027, the button still reads "Sync 2026 dataset" and still backfills from `2026/01/01` — a stale, misleading label with a rolling requirement someone has to remember to bump every year.

*Fix:* derive the label and `afterDate` from the current year, e.g. `` `${new Date().getFullYear()}/01/01` `` and `` `Sync ${new Date().getFullYear()} dataset` ``.

**Low/Medium — `components/ClassifyPanel.tsx:104-124,129-154`: `role="listbox"`/`role="option"` used without listbox keyboard semantics.**

The category and subcategory pickers are `<div role="listbox">` containing `<button role="option">` children, but there is no roving-tabindex/arrow-key navigation — each chip is an independent Tab stop.

*Failure scenario:* a screen-reader user hears "listbox, N options" and reasonably tries arrow keys to move between options (the expected listbox pattern per WAI-ARIA APG); nothing happens, and they must Tab through every chip individually — for a category list with several categories × subcategories, this is a confusing mismatch between announced role and actual behavior.

*Fix:* either implement roving tabindex + arrow-key handling for a true listbox, or drop `role="listbox"/"option"` and let them be a plain group of toggle buttons with `aria-pressed`, matching the pattern already used correctly for the direction filter (`TransactionsPage.tsx:223-241`).

**Low — `styles.css:344-354` vs `517-523`: debit/credit colors are hardcoded twice via two different selector strategies instead of one shared utility.**

`.tx-row.debit .tx-amount` / `.tx-row.credit .tx-amount` (used by `TransactionsPage.tsx` via ancestor `tr` class) hardcode `#8f3d2c` / `#0c6e5c`. `.tx-amount.debit` / `.tx-amount.credit` (used directly by `ClassifyPanel.tsx:89-92`) redeclare the same two hex values and the same font rules independently. `#0c6e5c` is also literally the value of `--accent` (`styles.css:9`) but isn't referenced via the variable in either spot.

*Failure scenario:* a future rebrand changes `--accent`, and the credit-amount green silently drifts out of sync in one or both duplicated rule blocks because there's no single source of truth.

*Fix:* consolidate to one `.tx-amount.debit`/`.tx-amount.credit` pair (used consistently by class, not ancestor selector) referencing `var(--accent)` for credit and a new `--debit` variable for debit.

**Low — pervasive one-off inline `style={{...}}` instead of styles.css classes**, most notably `pages/SettingsPage.tsx:220`.

12 inline-style occurrences across `SettingsPage.tsx` (211, 220, 225, 295, 366, 412), `TransactionsPage.tsx` (338, 352, 406), and `IncomeTrendModal.tsx` (144, 147) — mostly ad hoc `marginTop`. The most notable is `SettingsPage.tsx:220`, the OAuth JSON textarea, which inlines `fontFamily: "ui-monospace, monospace"` instead of reusing the `.mono` class already defined in `styles.css:851-855` (`ui-monospace, SFMono-Regular, Menlo, monospace`) — a second, slightly different monospace stack invented inline.

*Fix:* add small spacing utility classes (or contextual selectors) to `styles.css`, and give the credentials textarea a dedicated class that extends `.input`/`.mono` rather than an inline style block.

**Low — `styles.css:92,300,360,485,654,934`: six different components use fully-rounded (`999px`) pill shapes.**

Nav links, the category bar track, status badges, classify chips, the email transaction-id chip, and subcategory chips are all pill-shaped. CLAUDE.md explicitly asks to avoid "pill spam." Individually each is reasonable, but collectively it's the dominant shape language across the whole app, which is the pattern the guidance warns about.

*Fix:* not urgent, but worth a design pass — e.g. give badges/chips a smaller `border-radius` (matching `.btn`'s 12px) rather than full pill, reserving true pills for one or two elements.

**Low — duplicated modal shell markup across `ClassifyPanel.tsx:54-61`, `EmailViewerModal.tsx:66-73`, `IncomeTrendModal.tsx:130-137`.**

All three modals hand-repeat the identical `modal-backdrop` → `modal-panel[role=dialog][aria-modal][aria-labelledby]` → `stopPropagation` wrapper, even though `useModalChrome`/`useBackdropClose` already factor out the behavioral half of this pattern.

*Failure scenario:* not a live bug, but a maintainability risk — if the ARIA wiring needs to change (e.g. adding `aria-describedby`, or fixing the focus-trap gap above), it has to be edited in three places and can silently drift.

*Fix:* extract a `<ModalShell titleId trigger onClose>` wrapper component that owns the backdrop/panel/dialog markup, with each modal supplying only header/body content.

**Low — `pages/OverviewPage.tsx:42`: no retry affordance when the initial load fails.**

`if (error) return <p className="error">Could not load overview: {error}</p>;` is a dead end — the effect only runs once (`[]` deps, lines 15-29), so a failed initial fetch (e.g., API not yet up) leaves the user with only a full page reload to recover. `TransactionsPage` has a "Refresh" button and `SettingsPage` has "Refresh status," so this is an inconsistency in error-recovery UX across the three pages.

*Fix:* add a "Try again" button on the error branch that re-runs the load effect.

**Low — `components/EmailViewerModal.tsx:37-47,113`: sandboxed iframe blocks scripts but not image network requests.**

`sandbox=""` correctly blocks script execution for arbitrary bank/UPI HTML emails, but sandboxing alone does not stop `<img>` tags in `body_html` from firing network requests (tracking pixels) when rendered.

*Failure scenario:* minor for transactional bank alerts specifically, but if any ingested email contains a tracking pixel, viewing it in this modal would fetch that pixel — a small tension with the app's "local-first"/privacy framing.

*Fix:* not urgent for this use case, but if it matters, strip `<img>` src rewriting/proxying or add a "load images" opt-in similar to email clients.
