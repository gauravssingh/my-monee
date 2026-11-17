# MyMonee — Full-Width Warm Minimalist UI Design System

**Status:** Proposed implementation specification  
**Target branch:** `feat/full-width-warm-finance-ui`  
**Scope:** Visual redesign of the desktop application, with responsive adaptation  
**Reference direction:** Warm minimalist fintech UI; Swiss-inspired typography; simple, expressive financial data visualization

---

## 1. Product and design intent

MyMonee should feel like a calm, confident personal-finance workspace—not a generic SaaS admin template and not a dense accounting system.

The visual reference is the supplied spending card: strong black typography, generous whitespace, warm neutral canvas, white surfaces with subtle outlines, rounded horizontal bars, and a restrained teal/orange palette.

Use the full desktop viewport. Do not preserve the old centered/narrow content constraint merely for compatibility with the previous layout.

### Design principles

1. **Financial information first.** Amounts, cash flow, spending composition, and trends take visual priority over decorative UI.
2. **Calm, not sterile.** Warm surfaces, restrained color, clear hierarchy, and comfortable spacing.
3. **Dense when useful, spacious where it matters.** A dashboard can use the full width without turning every card into an oversized tile.
4. **Consistent, not repetitive.** Reusable components should share tokens, but each visualization should use the form that best explains its data.
5. **Truthful financial semantics.** Never imply that a category is fixed, flexible, income, savings, or available cash unless the existing domain model supports that meaning.
6. **Local-first stays local-first.** This is a visual change. Do not introduce remote dependencies, telemetry, cloud persistence, or external AI calls.
7. **Preserve behavior.** Do not change ledger semantics, transaction classification, reconciliation, calculations, database schema, or API contracts as part of this redesign.

---

## 2. Visual language

### Overall aesthetic

- Warm minimalist fintech
- Swiss-inspired typographic hierarchy
- Soft minimalism, not neumorphism
- Flat surfaces with fine borders; avoid heavy shadows
- Rounded but not excessively bubbly
- Teal and orange as visualization accents, not universal semantic status colors

### Avoid

- Generic enterprise SaaS dashboard styling
- Purple/blue gradient backgrounds
- Glassmorphism and blur panels
- Strong drop shadows on every card
- Excessive pills and badges
- Tiny low-contrast labels
- Decorative charts that do not encode real data
- Arbitrary fixed heights that clip content
- Narrow centered desktop containers

---

## 3. Design tokens

Use CSS custom properties in the existing global stylesheet. Do not scatter literal colors, radii, and spacing values throughout components.

### Color palette

| Token | Value | Use |
|---|---|---|
| `--canvas` | `#F7F6F2` | Main application background |
| `--surface` | `#FFFFFF` | Cards, panels, menus |
| `--surface-subtle` | `#F1F0EC` | Quiet inset areas and hover backgrounds |
| `--border` | `#E5E4DF` | Default card and control outline |
| `--border-strong` | `#D5D4CE` | Stronger separators |
| `--ink` | `#171717` | Primary text and financial values |
| `--ink-secondary` | `#555650` | Supporting text |
| `--ink-muted` | `#777871` | Metadata, captions, labels |
| `--accent-teal` | `#19A581` | Primary spending/data visualization |
| `--accent-teal-soft` | `#DDF2EA` | Teal subtle backgrounds |
| `--accent-orange` | `#F16B32` | Secondary spending/data visualization |
| `--accent-orange-soft` | `#FCE8DE` | Orange subtle backgrounds |
| `--accent-plum` | Existing brand token | Preserve existing brand identity for selected/interactive states where already used |
| `--success` | Existing semantic success token | Positive status, not inferred from chart palette |
| `--warning` | Existing semantic warning token | Warnings |
| `--danger` | Existing semantic danger token | Errors, destructive actions, negative status |
| `--focus-ring` | Accessible high-contrast focus color | Keyboard focus |

The values above are the light-theme baseline. Keep semantic tokens separate from chart palette tokens. Teal does not automatically mean income or positive cash flow; orange does not automatically mean expense or warning.

### Dark theme

Preserve dark mode. Define a separate dark token map rather than applying CSS filters or inverting the light palette. Maintain equivalent contrast, border visibility, and chart distinguishability. Do not force the warm ivory canvas into dark mode.

### Typography

Use the repository's existing font assets/families where available; avoid adding a new font dependency without a clear reason.

- Primary UI family: existing **Public Sans**.
- Existing **Newsreader** may be retained sparingly for editorial/long-form accents if it is already loaded, but should not compete with financial figures.
- Financial amounts and dashboard headings use a strong sans-serif weight.
- Use tabular numerals for amounts, balances, dates, and percentages.

Suggested scale (desktop):

| Role | Size | Weight | Line height |
|---|---:|---:|---:|
| Page title | 32–40px | 700–750 | 1.1 |
| Hero amount | 40–52px | 650–750 | 1.05 |
| Section title | 20–24px | 650–700 | 1.2 |
| Card amount | 24–32px | 650–700 | 1.15 |
| Body | 14–16px | 400–500 | 1.45 |
| Supporting | 12–13px | 400–500 | 1.4 |
| Micro label | 10–11px | 600–700 | 1.3 |

Use uppercase micro labels sparingly. Do not make every card title uppercase.

### Spacing

Use a consistent 4px base scale:

- 4px: icon/text micro gap
- 8px: compact control spacing
- 12px: dense internal spacing
- 16px: standard component spacing
- 20px: compact card padding
- 24px: standard card padding
- 32px: section spacing
- 40–48px: major page separation

### Shape and elevation

| Token | Value |
|---|---|
| Small control radius | 8–10px |
| Standard control radius | 10–12px |
| Standard card radius | 18–20px |
| Hero card radius | 24–28px |
| Pill radius | 999px |
| Card border | 1px solid `--border` |
| Default shadow | none |
| Overlay shadow | restrained, used only where elevation is needed |

Prefer a border over a shadow for ordinary cards. Use shadows only for overlays, menus, and floating surfaces.

---

## 4. Desktop application shell

### Viewport and content

Design desktop-first for 1440px–1920px viewports.

- App shell fills `100vw` and at least `100vh`.
- Remove the old narrow centered max-width constraint from the main application workspace.
- Use a persistent left navigation rail, approximately 224–248px wide when expanded.
- Main content consumes all remaining horizontal space.
- Main content uses responsive grid columns and sensible internal gutters; do not stretch individual text blocks across the entire screen.
- Use 24–32px outer content gutters on large screens.
- Keep the content scrollable independently where appropriate; avoid nested scroll traps.

### Navigation rail

- Persistent on desktop.
- MyMonee brand at top.
- Clear active state with a quiet tinted background and strong text.
- Group routes by user task (workspace/analysis/management) using existing route structure.
- Keep labels visible in expanded desktop mode.
- Mobile navigation may continue to use a drawer.
- Do not remove or rename existing routes as part of the visual restyle.

### Top bar

Use a lightweight top bar for current page context and global actions. Avoid duplicating the entire left navigation. Month selection belongs near the dashboard heading or relevant analytics context, not hidden in a global settings menu.

### Desktop grid

Use CSS Grid with fluid columns and minimum widths. Suggested patterns:

- Overview hero: 1.3fr / 0.7fr or full-width hero followed by metric row.
- Analytical region: 2fr / 1fr.
- Three-column card layout only where each card has enough room for readable content.
- Use `minmax(0, 1fr)` to prevent overflow.
- At 1440px, favor two-column content regions.
- At 1920px, allow three-column analytical regions where content benefits.
- Do not enlarge every card just because there is more screen space.

---

## 5. Core component specifications

Create or refactor shared components only where they improve consistency. Reuse existing components if they already provide the same behavior.

### SurfaceCard

Purpose: Base container for financial content.

- White surface in light theme.
- 1px subtle border.
- 18–28px radius depending on hierarchy.
- 20–28px internal padding.
- No default shadow.
- Optional compact/standard/hero density variants.
- Do not nest card inside card without a clear information hierarchy.

### MetricDisplay

Purpose: Show one primary financial metric.

- Label above or beside amount.
- Amount uses tabular numerals and high contrast.
- Optional comparison/period caption.
- Sign and color must reflect actual metric semantics.
- Avoid decorative icons unless they add meaning.

### SpendingComposition

Purpose: Display a real breakdown of spending groups, such as fixed/flexible only if the domain classification supports it.

- Strong section title.
- Amount aligned to the right of each group label.
- Rounded horizontal track with a proportional fill.
- Use teal/orange for distinct series.
- Provide exact amount and percentage in accessible text, not color alone.
- Clamp visual widths to 0–100%; handle zero total safely.
- Preserve existing source-of-truth calculations and grouping logic.

### ProgressBar

- Track uses a subtle neutral surface.
- Fill has fully rounded ends.
- Animation is subtle and respects reduced-motion preferences.
- Support accessible label/value attributes.
- Never communicate status through color alone.

### SectionHeading

- Consistent title and optional subtitle/action.
- Strong but not oversized.
- Use semantic heading levels.
- Actions remain visible and keyboard accessible.

### ComparisonIndicator

- Display change value and comparison period.
- Use explicit up/down/neutral language or icon plus text.
- A rise in spending is not automatically positive; derive meaning from the metric.
- Do not use green/red solely based on numerical direction.

### Charts

- Use the existing charting implementation unless it blocks the required design.
- Remove unnecessary chart borders, legends, grid lines, and gradients.
- Keep axes and labels readable.
- Use actual ledger-derived data only.
- Tooltips must be keyboard accessible where the chart library permits.
- Provide a text/table alternative for key chart values.
- Use consistent series colors across pages.

---

## 6. Overview page information architecture

The Overview should answer these questions quickly:

1. How much money came in during the selected period?
2. How much was spent?
3. What is the resulting net cash flow?
4. Where did the spending go?
5. How is spending changing over time?
6. Which transactions need attention?

Suggested hierarchy:

### A. Page context

- Page title: Overview
- Selected month and month navigation
- Optional data freshness/sync context, only if currently supported

### B. Primary spending composition

A prominent, wide card inspired by the supplied reference image.

- Heading: Spending this month (or selected period)
- Total amount as the primary figure
- Existing supported spending groups shown as horizontal proportional bars
- Amounts right-aligned
- No invented fixed/flexible categorization

### C. Financial summary metrics

A row or grid for existing metrics such as income, total spending, net cash flow, and savings/retained amount only if that metric is already correctly defined.

### D. Spending trend and category analysis

- Daily/weekly/monthly trend at a useful width
- Category breakdown with readable labels and values
- Avoid squeezing charts into small cards

### E. Attention and activity

- Needs-review transactions
- Recent or largest transactions
- Recurring/subscription insights if already supported

This is a proposed hierarchy, not permission to invent new metrics or modify calculations.

---

## 7. Responsive behavior

Desktop is the primary design target, but the UI must remain usable at smaller widths.

- >= 1600px: use wide analytical grid where useful.
- 1200–1599px: two-column content regions; reduce gutters slightly.
- 768–1199px: collapse navigation to compact rail/drawer; mostly one- or two-column cards.
- < 768px: single-column content; preserve the most important metrics first; charts may scroll horizontally only when unavoidable.
- Never hide critical transaction actions or financial values on mobile.
- Avoid fixed pixel widths for primary content.

---

## 8. Accessibility and interaction

- Meet WCAG 2.2 AA contrast for text and controls.
- Visible keyboard focus on every interactive element.
- Use semantic buttons and links, not clickable generic divs.
- Minimum 40px practical target size for common controls; aim for 44px on touch.
- Respect `prefers-reduced-motion`.
- Do not rely on color alone for financial meaning or chart series.
- Preserve existing keyboard behavior, focus management, and modal semantics.
- Inputs need visible labels; placeholders are not labels.
- Maintain readable type at browser zoom 200%.

---

## 9. Engineering guardrails

This is a presentation-layer redesign.

**Do not change:**

- Database schema or migrations
- Ledger entries or accounting semantics
- Transaction classification rules
- Import pipelines or email parsing
- Financial calculations or rounding behavior
- API request/response contracts
- Authentication/session behavior
- Local-first/privacy guarantees
- Existing routes and deep links

**Prefer:**

- Existing React + TypeScript architecture
- Existing CSS approach and build tooling
- CSS variables for all shared tokens
- Reusable presentational components
- Existing icon and chart dependencies
- Small, reviewable commits

Do not add a component framework or a new styling system just to achieve the visual result. Do not rewrite the application shell or routing unless the existing structure makes the full-width shell impossible.

---

## 10. Implementation sequence

### Phase 0 — Baseline and inventory

- Read `DESIGN.md`, `web/src/styles.css`, `web/src/App.tsx`, and all Overview page dependencies.
- Identify current fonts, theme support, breakpoints, chart library, shared components, and route layout.
- Run existing tests and production build; record baseline.
- Capture screenshots at 1440px and 1920px before changes.

### Phase 1 — Design foundation and shell

- Add token system and light/dark mappings.
- Implement full-width app shell and desktop navigation rail.
- Preserve mobile drawer and all route behavior.
- Verify every existing route still renders.

### Phase 2 — Overview

- Implement primary spending composition card.
- Rework summary metric hierarchy.
- Restyle trends and category breakdown.
- Keep all displayed values bound to existing data.
- Compare screenshots against reference direction.

### Phase 3 — Remaining routes

Restyle transactions, category analytics, accounts, merchants, recurring, review, data issues, and settings. Keep route-specific information architecture intact.

### Phase 4 — Verification

- TypeScript check
- Lint
- Unit/integration tests
- Production build
- Desktop screenshots at 1440px and 1920px
- Tablet and mobile screenshots
- Light and dark theme review
- Keyboard and contrast review
- Regression check for navigation, filters, modals, tables, and transaction actions

Do not mark a phase complete based only on compilation. Browser verification is required for visual work.

---

## 11. Definition of done

- [ ] Full-width desktop workspace; no legacy narrow centered container.
- [ ] Persistent desktop navigation with clear active state.
- [ ] Warm neutral canvas and white bordered surfaces.
- [ ] Strong, consistent typographic hierarchy and tabular financial figures.
- [ ] Spending composition card matches the supplied visual direction.
- [ ] Existing domain categories and calculations remain unchanged.
- [ ] No clipped content or horizontal overflow at 1440px/1920px.
- [ ] Mobile and tablet layouts remain usable.
- [ ] Dark mode remains supported.
- [ ] Accessible contrast, focus, labels, and non-color cues.
- [ ] All existing routes and interactions work.
- [ ] Tests, lint, type check, and production build pass.
- [ ] Browser screenshots reviewed and included in implementation report.
- [ ] No database, ledger, API, or privacy architecture changes.

---

## 12. Agent execution instructions

Before coding, return:

1. A concise inventory of the current UI architecture.
2. A list of files to change and why.
3. A phased implementation plan.
4. Any conflicts between this spec and the existing `DESIGN.md`.
5. A list of behaviors that must remain unchanged.

Then implement Phase 1 and Phase 2 only. Do not proceed to Phase 3 until the Overview has been browser-verified and reviewed.

Use the supplied spending-card image as a visual reference, not as a pixel-perfect template. Make deliberate layout decisions for the full desktop viewport.

At completion, report changed files, screenshots, test/build results, known gaps, and confirmation that no ledger/database/API behavior was changed.
