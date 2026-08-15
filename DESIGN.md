# MyMonee --- Design System & UX Conventions

*.. my finances*

Design specifications, user experience conventions, component patterns,
and visual rules for the MyMonee local-first personal finance
application.

This document is the frontend design source of truth. It defines the
visual language, information hierarchy, interaction patterns, financial
presentation rules, and page-level UX conventions that should be used
when building or refining MyMonee.

The goal is not to maximize information density. The goal is
**information efficiency**: helping the user understand their finances
with the least cognitive effort while preserving the practical,
desktop-grade nature of the application.

------------------------------------------------------------------------

## 1. Design Philosophy

MyMonee is a **calm, practical financial ledger and analysis tool for
macOS**.

It should feel closer to a well-designed financial report and
professional ledger than a generic SaaS dashboard.

The interface combines:

-   Editorial typography for identity and important financial numbers.
-   Clean sans-serif typography for everyday interaction.
-   High scanability for transaction-heavy screens.
-   Strong financial semantics.
-   Restrained visual styling.
-   Progressive disclosure of secondary information.
-   Clear, predictable interaction.

### Core Design Tenets

  -----------------------------------------------------------------------
  Principle                           Rule
  ----------------------------------- -----------------------------------
  **Financial Clarity**               The user should understand the
                                      financial meaning before the UI
                                      details.

  **Information Efficiency**          Show the most useful information
                                      with the least cognitive effort.

  **Scanability**                     Users should be able to understand
                                      a screen by scanning labels,
                                      numbers, alignment, and hierarchy.

  **Financial Integrity**             Amounts, direction, categories,
                                      transfers, and account
                                      relationships must be represented
                                      accurately.

  **Calm Utility**                    Use restrained styling and avoid
                                      decorative UI that does not improve
                                      comprehension.

  **Progressive Disclosure**          Show the important information
                                      first; reveal secondary detail
                                      through drill-down, expansion, or
                                      "View all".

  **Deterministic Polish**            Interactions should be predictable,
                                      immediate, keyboard-friendly, and
                                      accessible.
  -----------------------------------------------------------------------

### The Attention Budget

Every screen has a limited amount of visual attention.

Only a small number of elements should receive strong emphasis at the
same time.

For example, Monthly Analysis may emphasize:

1.  Selected month.
2.  Total spending.
3.  Net cash flow.
4.  Important review/data-quality issues.

Everything else should be visually subordinate.

Do not make every metric, chart, card, warning, and button equally
prominent.

------------------------------------------------------------------------

## 2. Visual Identity

MyMonee uses a restrained editorial/utilitarian visual language.

### Desired Characteristics

-   Quiet.
-   Clean.
-   Practical.
-   Financial.
-   Structured.
-   Easy to scan.
-   Desktop-first.
-   Minimal decoration.
-   Consistent spacing and alignment.

### Avoid

-   Generic SaaS dashboard styling.
-   Excessive cards.
-   Bento-box layouts.
-   Large decorative illustrations.
-   Gradient backgrounds.
-   Glassmorphism.
-   Neon colors.
-   Excessive rounded containers.
-   Oversized icons.
-   Excessive shadows.
-   Charts added only because data is available.
-   Equal visual weight for unrelated metrics.

### Core Rule

> **Prefer structure over containers.**

Use typography, whitespace, alignment, and hairline dividers to create
hierarchy before reaching for cards, shadows, or colored backgrounds.

------------------------------------------------------------------------

## 3. Design Tokens & Foundations

All design tokens are defined as CSS Custom Properties in
`web/src/styles.css`.

### 3.1 Color Palette

``` css
:root {
  /* Surfaces */
  --bg: #eff1f2;
  --surface: #f7f8f8;
  --panel: var(--surface);
  --panel-solid: var(--surface);
  --line: #d8dbde;

  /* Typography */
  --ink: #1b1d22;
  --ink-muted: #6b707a;

  /* Brand / interaction */
  --accent: #4b2e58;
  --accent-hover: #3b2245;
  --accent-soft: rgba(75, 46, 88, 0.1);

  /* Financial semantics */
  --debit: #a5333b;
  --debit-soft: rgba(165, 51, 59, 0.1);

  --credit: #2f6d4f;
  --credit-soft: rgba(47, 109, 79, 0.1);

  --warn: #8a5a12;
  --warn-soft: rgba(138, 90, 18, 0.12);

  --danger: #a5333b;

  /* Geometry */
  --radius: 8px;
  --radius-sm: 4px;
}
```

### Color Rules

**Purple / Accent**

Use for:

-   Brand identity.
-   Active navigation.
-   Focus states.
-   Selected controls.
-   Primary actions.
-   Important interactive affordances.

Do not use purple simply to decorate a component.

**Red / Debit**

Use for:

-   Expenses/outflows.
-   Negative financial direction where appropriate.
-   Errors.
-   Destructive actions.

**Green / Credit**

Use for:

-   Income/inflows.
-   Refunds.
-   Positive financial direction where appropriate.

**Amber / Warning**

Use for:

-   Needs Review.
-   Data-quality problems.
-   Attention required.

### Semantic Color Rule

> **Color is semantic, not decorative.**

Do not use arbitrary colors simply to differentiate chart series or make
a dashboard look more colorful.

------------------------------------------------------------------------

## 4. Typography

MyMonee uses an editorial serif and a practical sans-serif.

  ---------------------------------------------------------------------------------------------
  Role                    Font                                          Usage
  ----------------------- --------------------------------------------- -----------------------
  Display                 `"Newsreader", Georgia, serif`                Brand, page titles,
                                                                        major financial values,
                                                                        modal headings

  UI                      `"Public Sans", -apple-system, sans-serif`    Navigation, labels,
                                                                        tables, forms, buttons,
                                                                        body

  Monospace               `ui-monospace, "SF Mono", Menlo, monospace`   IDs, masked account
                                                                        numbers,
                                                                        technical/provenance
                                                                        values
  ---------------------------------------------------------------------------------------------

### Typography Rules

1.  **Brand**
    -   Newsreader.
    -   `600`.
    -   Distinctive but restrained.
2.  **Page Titles**
    -   Newsreader.
    -   `600`.
    -   Used sparingly.
3.  **Major Financial Values**
    -   Newsreader.
    -   `600`.
    -   Tabular numerals.
    -   Use only for values that deserve emphasis.
4.  **Section Headers**
    -   Public Sans.
    -   Small uppercase.
    -   `700`.
    -   `0.06–0.08em` tracking.
    -   Accent or muted ink depending on hierarchy.
5.  **Field / Table Headers**
    -   Public Sans.
    -   Small uppercase.
    -   `600–700`.
    -   Muted.
6.  **Body**
    -   Public Sans.
    -   Comfortable line height.
    -   Avoid unnecessarily small text.

### Serif Rule

> **Serif is for emphasis, not information density.**

Use serif typography to establish identity and hierarchy, not for
ordinary table content.

### Financial Numbers

All financial figures must use:

``` css
font-variant-numeric: tabular-nums;
```

This is required for aligned financial columns.

------------------------------------------------------------------------

## 5. Layout Principles

### 5.1 App Shell

The application uses a centered desktop layout:

``` css
.app-shell {
  max-width: 1120px;
  margin: 0 auto;
  padding: 0 20px 64px;
}
```

Do not increase the application width simply to fit more information.

When a page feels crowded, first reduce visual noise and secondary
information before increasing width.

### 5.2 Page Rhythm

Use a consistent vertical rhythm:

``` text
Page title
    ↓
Context / controls
    ↓
Primary information
    ↓
Primary analysis
    ↓
Secondary detail
    ↓
Drill-down / supporting information
```

Do not stack many unrelated sections with identical spacing and
identical visual weight.

### 5.3 Grid Usage

Use grids according to information relationships rather than forcing
every page into the same layout.

A 60/40 layout is appropriate when:

-   The left side contains primary analysis.
-   The right side contains supporting analysis.

A 50/50 layout is appropriate when the two sections have similar
importance.

Full-width layout is preferred for:

-   Transaction tables.
-   Large analytical lists.
-   Detailed comparisons.

### Responsive Breakpoint

At `<= 900px`:

-   Collapse multi-column layouts.
-   Preserve logical grouping.
-   Reduce horizontal padding.
-   Avoid horizontal scrolling except where a genuine table requires it.

------------------------------------------------------------------------

## 6. Navigation

The top navigation remains compact and understated.

``` text
MyMonee .. my finances

Overview
Transactions ▾
Accounts
Merchants
Categories
Settings
```

### Navigation Rules

-   Active page uses a subtle accent underline.
-   Do not use large filled navigation pills.
-   Dropdowns are reserved for meaningful hierarchical navigation.
-   Navigation should never visually compete with page content.
-   Preserve the existing sticky topbar.

------------------------------------------------------------------------

## 7. Information Hierarchy

Every page should answer:

1.  **What is happening?**
2.  **How much?**
3.  **Where did it happen?**
4.  **What changed?**
5.  **What needs attention?**
6.  **How can I drill down?**

The answer should not require reading every element.

### Primary vs Secondary Information

Primary information:

-   Major financial totals.
-   Selected period.
-   Financial direction.
-   Major categories.
-   Major exceptions.
-   Actions requiring attention.

Secondary information:

-   Transaction counts.
-   Percentages.
-   Supporting metadata.
-   Raw descriptions.
-   Provenance.
-   Technical information.

Secondary information should visually recede without becoming
inaccessible.

------------------------------------------------------------------------

## 8. Progressive Disclosure

Do not display every available record or metric by default.

Preferred patterns:

``` text
Top 5
    ↓
View all →

Summary
    ↓
Details →

Collapsed
    ↓
Expand →

Metric
    ↓
Click for drill-down
```

Use progressive disclosure for:

-   Category lists.
-   Merchant lists.
-   Payment methods.
-   Largest transactions.
-   Technical/provenance details.
-   Data-quality details.

### Rule

> **The default screen should be understandable without expanding
> anything.**

------------------------------------------------------------------------

## 9. Metric Strips

Metric strips are for genuinely related metrics.

Example:

``` text
┌──────────────────────┬──────────────────────┬──────────────────────┐
│ TOTAL SPENT          │ INCOME               │ NET CASH FLOW        │
│ ₹84,230              │ ₹1,50,000            │ +₹65,770             │
│ ↓ 12% vs last month  │ ↑ 4% vs last month   │ Income − spending    │
└──────────────────────┴──────────────────────┴──────────────────────┘
```

### Rules

-   Keep the number of primary metrics small.
-   Do not force unrelated metrics into the same strip.
-   Major metrics use larger typography.
-   Supporting metrics use normal UI typography.
-   Comparisons must explain what they compare against.

### Financial Flow vs Financial Position

These are different concepts.

**Financial Flow**

-   Spending.
-   Income.
-   Net cash flow.
-   Transaction volume.

**Financial Position**

-   Net worth.
-   Account balances.
-   Credit utilization.
-   Assets.
-   Liabilities.

Do not place Net Worth in the same visual hierarchy as monthly spending
unless the page specifically concerns overall financial position.

------------------------------------------------------------------------

## 10. Financial Tables

Tables are intentionally the densest part of MyMonee.

``` text
Date       Merchant / Description             Category        Amount
15 Aug     Swiggy                             Food            -₹1,237
14 Aug     Salary                             Income         +₹95,000
```

### Rules

-   Horizontal row separators.
-   No interior vertical borders unless required for clarity.
-   Subtle hover background.
-   Text left-aligned.
-   Numbers right-aligned.
-   Actions right-aligned.
-   Amounts use tabular numerals.
-   Debits use semantic debit styling.
-   Credits use semantic credit styling.

### Table Density

Transactions may be compact.

Other pages should not automatically inherit transaction-table density.

> **Density is a property of the content, not a design objective.**

------------------------------------------------------------------------

## 11. Lists & Ranked Data

Ranked lists should be simpler than cards.

Preferred:

``` text
TOP MERCHANTS

Swiggy                         ₹6,699
13 transactions

Amazon                         ₹4,820
4 transactions

Zepto                          ₹4,200
8 transactions
```

Avoid:

``` text
┌─────────────────┐
│ 🛒 Swiggy       │
│ ₹6,699          │
│ 13 transactions │
└─────────────────┘
```

Use alignment and dividers instead of containers.

### Long Names

Long merchant names should:

-   Use normalized merchant names where available.
-   Truncate visually when necessary.
-   Show the full value on hover/focus.
-   Never allow one long name to destroy table/list alignment.

------------------------------------------------------------------------

## 12. Category & Spending Bars

Progress bars are appropriate for ranked category spending.

``` css
.bar-track {
  height: 6px;
  background: var(--line);
  border-radius: var(--radius-sm);
}

.bar-fill {
  background: var(--accent);
}
```

### Rules

-   Scale relative to the maximum item in the displayed group.
-   Keep bars visually subordinate to the amounts.
-   Amount and percentage must remain easy to scan.
-   Do not use a different color for every category.
-   Show only the top categories by default.
-   Use "View all" for the remainder.

------------------------------------------------------------------------

## 13. Charts

Charts are explanatory tools, not decoration.

Before adding a chart, ask:

> What question does this chart answer better than a number or table?

### Appropriate Charts

**Daily spending**

Answers:

> When did I spend money?

**Category breakdown**

Answers:

> Where did I spend money?

**Month comparison**

Answers:

> How did spending change?

### Chart Rules

-   Minimal gridlines.
-   Restrained color.
-   Clear labels.
-   Meaningful tooltips.
-   No 3D effects.
-   No decorative gradients.
-   No excessive legends.
-   Avoid charts with too many categories.
-   Use tables when they communicate the information more clearly.

### Tooltips

A tooltip should provide useful context:

``` text
15 Aug
₹12,430
8 transactions
```

Do not make tooltips merely repeat the axis label.

------------------------------------------------------------------------

## 14. Monthly Analysis / Overview

The Overview page is a **monthly financial report**, not a generic
dashboard.

The user's mental model should be:

``` text
Selected month
    ↓
How much came in?
    ↓
How much went out?
    ↓
Where did it go?
    ↓
What changed?
    ↓
What needs attention?
```

### Recommended Page Hierarchy

``` text
Monthly Analysis

August 2026
1 Aug – 31 Aug
← Previous     This Month     Next →

Needs attention
64 transactions need classification
₹3,55,478 affected                         Review →

────────────────────────────────────────────

TOTAL SPENT          INCOME          NET CASH FLOW
₹4,38,722            ₹2,82,330       -₹1,56,392
↓ 11.5%              ↓ 2.9%

Transactions         Net Worth
126                  -₹34,09,981
93 out · 1 in        34 accounts

────────────────────────────────────────────

SPENDING BREAKDOWN                  DAILY SPENDING

Food                 26% ₹11,248    [chart]
Shopping             20%  ₹8,450
Transport            15%  ₹6,300
Bills                14%  ₹5,900
Education            10%  ₹4,200

View all categories →

────────────────────────────────────────────

VS LAST MONTH

Spending             ↓ 11.5%
Income                ↓ 2.9%
Largest increase      Education
Largest decrease      Shopping

────────────────────────────────────────────

TOP MERCHANTS                    PAYMENT METHODS

Swiggy                 ₹6,699    HDFC ····1022
Amazon                 ₹4,820    HDFC ····1456
Zepto                  ₹4,200    Unknown
...

────────────────────────────────────────────

LARGEST TRANSACTIONS

15 Aug   Merchant                    ₹65,000
14 Aug   Merchant                    ₹58,000
...

────────────────────────────────────────────

NET WORTH / FINANCIAL POSITION
```

### Important

Do not display every analytical dimension at equal prominence.

Show the most important five items first and use progressive disclosure
for the rest.

------------------------------------------------------------------------

## 15. Financial Semantics

The UI must reflect the application's financial model.

### Expenses

Money leaving the user's financial ecosystem.

### Income

Money entering the user's financial ecosystem.

### Transfers

Movement between the user's own accounts.

Transfers must not be treated as spending or income where the
application's transaction semantics identify them as internal transfers.

### Credit Card Payments

A credit-card bill payment is a movement of money between accounts and
must not cause the underlying credit-card purchases to be counted twice.

### Loans

Loan principal, interest, repayments, and disbursements must follow the
application's established transaction semantics.

Do not assume that every loan-related transaction is ordinary consumer
spending.

### Refunds

Refunds should be represented as credits and should not be treated as
ordinary income unless the application's financial model explicitly
defines them that way.

### Critical Rule

> **Frontend presentation must never invent financial semantics.**

If the backend/domain model distinguishes Expense, Income, Transfer,
Loan, Credit Card Payment, Investment, or Refund, the UI should use
those classifications.

------------------------------------------------------------------------

## 16. Data Quality & Review UX

MyMonee relies on classification and parsing quality.

Data-quality problems are first-class UX concerns.

Examples:

-   Unclassified transactions.
-   Unknown account.
-   Unknown merchant.
-   Parser errors.
-   Duplicate transactions.
-   Wrong direction.
-   Missing provenance.

### Needs Review

Use a compact amber attention treatment:

``` text
⚠ Needs attention

64 transactions · ₹3,55,478 need classification

Review →
```

Do not make warnings visually dominate the financial summary.

### Unknown Data

Unknown values should be visible, but should communicate that they
represent incomplete data.

Example:

``` text
Unknown account
₹1,80,555
41.2% of spending

⚠ Some transactions are not linked to an account
```

Do not disguise data-quality problems as normal financial categories.

------------------------------------------------------------------------

## 17. Interactive Drill-Down

Analysis should lead naturally back to the ledger.

Examples:

**Category → Transactions**

``` text
Food & Restaurants
```

opens the Transactions view filtered to:

``` text
Month = August 2026
Category = Food & Restaurants
```

**Merchant → Transactions**

``` text
Swiggy
```

opens the corresponding monthly merchant transactions.

**Account → Transactions**

``` text
HDFC Credit Card ····1022
```

opens the corresponding account transactions.

**Largest Transaction → Transaction Detail**

Use the existing transaction detail/edit flow.

Do not build duplicate filtering or detail mechanisms when an existing
Transactions capability can be reused.

------------------------------------------------------------------------

## 18. Forms

Forms should be comfortable and predictable.

### Inputs

``` css
.input {
  background: white;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 8px 12px;
}
```

### Focus

Use:

``` css
border-color: var(--accent);
box-shadow: 0 0 0 2px var(--accent-soft);
```

### Form Rules

-   Clear labels.
-   Comfortable vertical spacing.
-   Related fields may share a row.
-   Avoid cramped vertical layouts.
-   Helper text should explain why a field matters.
-   Optional fields should be clearly marked.
-   Validation should be close to the affected field.
-   Avoid using toast notifications as the only validation feedback.

------------------------------------------------------------------------

## 19. Modals & Drawers

Modals are for focused tasks, not large application pages.

### Rules

-   Render through React Portals.
-   Lock background scroll.
-   Support Escape.
-   Preserve focus.
-   Close safely on backdrop interaction.
-   Use the established backdrop and surface tokens.
-   Keep header and footer visually distinct.
-   Avoid unnecessary decorative elements.

### Modal Hierarchy

``` text
Title
Supporting context

Section
Fields

Section
Fields

Footer
Cancel    Primary action
```

The modal should contain only the information necessary to complete the
task.

------------------------------------------------------------------------

## 20. Buttons & Actions

Use a small set of consistent button variants.

### Primary

Purple accent.

Use for:

-   Save.
-   Confirm.
-   Main workflow action.

### Secondary

Neutral surface/border.

Use for:

-   Cancel.
-   View.
-   Alternative actions.

### Destructive

Red.

Use only for genuinely destructive operations.

### Rule

Do not turn every action into a prominent button.

Prefer text links or subtle controls for secondary navigation such as:

``` text
View all →
Review →
Open →
```

------------------------------------------------------------------------

## 21. Destructive Actions

Use the existing two-phase arming pattern for minor destructive actions:

1.  Initial muted state.
2.  Armed red state.
3.  Second click executes.
4.  Clicking away disarms.

Use a structured confirmation modal for irreversible entity-level
deletions such as deleting an Account.

------------------------------------------------------------------------

## 22. Toasts

Toasts are for feedback, not essential information.

Use:

-   Success.
-   Error.
-   Informational confirmation.

Do not put critical financial warnings exclusively in a toast.

Important review/data-quality issues should remain visible in the page.

------------------------------------------------------------------------

## 23. Empty States

Empty states should explain the absence of data and, where appropriate,
what the user can do next.

Example:

``` text
No transactions in August 2026

There are no recorded transactions for this month.

← Previous month
```

Avoid:

-   Large illustrations.
-   Generic motivational copy.
-   Excessive empty-state decoration.

------------------------------------------------------------------------

## 24. Financial Formatting

All financial presentation must conform to `web/src/format.ts`.

### Currency

Indian Rupee:

``` text
₹1,23,456
```

Use `en-IN`.

High-level summaries use zero fractional digits unless precision is
necessary.

### Dates

Use:

``` text
24 Oct 2024
```

Date + time:

``` text
24 Oct 2024, 7:30 pm
```

Month:

``` text
October 2024
```

### Direction

Expenses/outflows:

``` text
-₹1,237
```

Income/inflows:

``` text
+₹95,000
```

Use the application's established display convention consistently.

------------------------------------------------------------------------

## 25. Provenance & Auditability

MyMonee is a local-first financial tool. Trust is a core product
requirement.

Raw provenance should remain accessible without cluttering the primary
UI.

Examples:

-   Original Gmail message.
-   Parser ID.
-   Transaction ID.
-   Source metadata.
-   Raw transaction description.

### Principle

> **Keep provenance accessible, not permanently visible.**

Use:

-   Detail views.
-   Tooltips.
-   Expandable metadata.
-   Email viewer modal.
-   Clickable transaction IDs.

Do not expose technical metadata in the primary financial summary unless
it helps the user.

------------------------------------------------------------------------

## 26. Page Catalog

  ------------------------------------------------------------------------
  Route                   View                    Primary UX
                                                  Responsibility
  ----------------------- ----------------------- ------------------------
  `/`                     **Overview / Monthly    Understand the selected
                          Analysis**              month's spending,
                                                  income, cash flow,
                                                  categories, major
                                                  merchants, trends, and
                                                  attention items.

  `/transactions`         **All Transactions**    Search, filter, sort,
                                                  inspect, classify, and
                                                  audit the complete
                                                  transaction ledger.

  `/review`               **Needs Review**        Efficiently classify
                                                  ambiguous/unclassified
                                                  transactions and improve
                                                  classification quality.

  `/recurring`            **Recurring &           Understand recurring
                          Subscriptions**         commitments, cadence,
                                                  and subscription
                                                  spending.

  `/merchants`            **Merchants**           Manage normalized
                                                  merchants, spend,
                                                  transaction counts, and
                                                  category associations.

  `/accounts`             **Accounts & Assets**   Manage bank accounts,
                                                  cards, wallets, UPI
                                                  identifiers, balances,
                                                  limits, and account
                                                  metadata.

  `/data-issues`          **Data Issues**         Investigate parser
                                                  errors, duplicates,
                                                  incorrect amounts,
                                                  direction errors, and
                                                  other data-quality
                                                  problems.

  `/settings`             **Settings & System**   Manage ingestion, Gmail
                                                  sync, database/local
                                                  privacy information,
                                                  categories, and system
                                                  configuration.
  ------------------------------------------------------------------------

------------------------------------------------------------------------

## 27. Page-Specific Density

Different pages intentionally have different information densities.

### Transactions

**High density**

Optimized for:

-   Scanning.
-   Searching.
-   Filtering.
-   Classification.
-   Audit.

### Overview / Monthly Analysis

**Medium density**

Optimized for:

-   Understanding.
-   Comparison.
-   Pattern recognition.
-   Quick drill-down.

### Accounts

**Medium density**

Optimized for:

-   Financial position.
-   Account management.
-   Limits and balances.

### Settings

**Low-to-medium density**

Optimized for:

-   Configuration.
-   Clarity.
-   Safe actions.

### Forms / Modals

**Comfortable density**

Optimized for:

-   Accurate input.
-   Minimal cognitive load.
-   Completion.

------------------------------------------------------------------------

## 28. Accessibility & Keyboard UX

All interactive elements must be keyboard accessible.

Requirements:

-   Visible focus states.
-   Logical tab order.
-   Buttons must have accessible labels.
-   Icon-only buttons require accessible names.
-   Charts should provide text alternatives or supporting data.
-   Do not rely on color alone to communicate financial direction or
    warnings.
-   Respect `prefers-reduced-motion`.

### Power UX

Where appropriate, support:

-   `/` --- focus search.
-   `j` / `k` --- move through transaction lists.
-   `c` --- classify.
-   `e` --- open source email.
-   `Esc` --- close modal/drawer.

Shortcuts must never interfere with normal text input.

------------------------------------------------------------------------

## 29. Motion

Motion is subtle and functional.

Preferred:

``` css
@keyframes rise {
  from {
    opacity: 0;
    transform: translateY(4px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}
```

Use animation for:

-   Small state changes.
-   Page entrance.
-   Progress changes.
-   Toasts.

Do not animate financial numbers excessively.

Disable animation when:

``` css
@media (prefers-reduced-motion: reduce) {
  * {
    animation: none !important;
    transition: none !important;
  }
}
```

------------------------------------------------------------------------

## 30. Responsive Behavior

MyMonee is desktop-first, but layouts must remain usable at smaller
widths.

### Desktop

-   Maximum width: 1120px.
-   Multi-column analytical layouts where useful.
-   Dense transaction tables.
-   Comfortable modal widths.

### Tablet / Small Laptop (`<= 900px`)

-   Collapse multi-column analytical sections.
-   Metrics may use two-column or single-column layouts depending on
    available space.
-   Preserve section hierarchy.
-   Keep controls usable.

### Mobile / Narrow Width

-   Stack content.
-   Use compact metric grids.
-   Tables may use horizontal scrolling when necessary.
-   Avoid horizontal scrolling for ordinary page content.
-   Modals may become full-height or bottom-sheet style where
    appropriate.

------------------------------------------------------------------------

## 31. Design Guardrails

The following are strict anti-patterns.

### Forbidden

-   Generic bento-box dashboards.
-   Decorative stat cards.
-   Random icons without semantic value.
-   Gradient-heavy UI.
-   Neon or glowing themes.
-   Purple-on-dark visual treatment.
-   Excessive rounded cards.
-   Excessive shadows.
-   Rainbow charts.
-   Giant hero sections.
-   Huge CTA buttons for ordinary actions.
-   Heavy UI frameworks.
-   Raw unformatted financial numbers.
-   Silent financial operations.
-   Hiding data-quality problems.
-   Showing every metric simply because it exists.
-   Adding charts without a clear analytical purpose.

### Framework Rule

Do not install Mantine, MUI, Ant Design, Tailwind, or another heavy UI
framework unless explicitly approved.

Use the existing CSS design tokens and React components.

------------------------------------------------------------------------

## 32. Implementation Rules for Coding Agents

When modifying an existing page:

1.  Inspect the existing component before changing it.
2.  Reuse existing tokens and components.
3.  Reuse existing API/data semantics.
4.  Do not create duplicate filtering or data logic.
5.  Do not change financial calculations as part of a visual redesign.
6.  Preserve existing functionality.
7.  Make the smallest coherent change that improves UX.
8.  Test at realistic desktop dimensions.
9.  Check empty, loading, error, and data-quality states.
10. Verify that financial totals remain correct.
11. Check keyboard accessibility.
12. Check responsive behavior.

### Before Adding a Component

Ask:

> Does this component make the user's financial task easier?

If not, do not add it.

### Before Adding a Chart

Ask:

> What question does this chart answer better than a number or table?

If there is no strong answer, do not add it.

### Before Adding a Card

Ask:

> Does this need a visual container, or can spacing and dividers
> communicate the hierarchy more clearly?

Prefer the latter.

------------------------------------------------------------------------

## 33. Design Review Checklist

Before considering a page complete:

### Clarity

-   [ ] Can the user identify the page purpose immediately?
-   [ ] Is the most important information visually dominant?
-   [ ] Can the page be understood by scanning?
-   [ ] Are secondary details visually subordinate?

### Financial correctness

-   [ ] Income and expenses are clearly distinguished.
-   [ ] Transfers are handled according to domain semantics.
-   [ ] Credit-card payments are not double-counted.
-   [ ] Amounts reconcile.
-   [ ] Financial direction is clear.
-   [ ] Unknown/data-quality states are visible.

### Visual quality

-   [ ] Existing MyMonee typography is used.
-   [ ] Existing colors are reused.
-   [ ] Borders and spacing are consistent.
-   [ ] No unnecessary cards or decorative UI.
-   [ ] No excessive visual emphasis.
-   [ ] Numbers are aligned and easy to scan.

### Interaction

-   [ ] Important items support drill-down.
-   [ ] Secondary information uses progressive disclosure.
-   [ ] Actions are obvious but not oversized.
-   [ ] Loading and empty states are handled.
-   [ ] Errors are understandable.

### Accessibility

-   [ ] Keyboard navigation works.
-   [ ] Focus states are visible.
-   [ ] Icon-only controls have labels.
-   [ ] Color is not the only semantic indicator.
-   [ ] Reduced motion is respected.

------------------------------------------------------------------------

## 34. UX Roadmap

Future improvements should follow this order:

### Phase A --- Visual Consistency

-   Standardize modal sizing.
-   Tighten table row rhythm.
-   Standardize button variants.
-   Align spacing and section hierarchy.
-   Reduce unnecessary visual containers.

### Phase B --- Information Efficiency

-   Apply progressive disclosure.
-   Reduce redundant metrics.
-   Improve monthly analysis hierarchy.
-   Improve drill-down between analysis and transactions.
-   Improve data-quality visibility.

### Phase C --- Power UX

-   Keyboard navigation.
-   Faster classification.
-   Search shortcuts.
-   Bulk actions.
-   Efficient transaction review.

### Phase D --- Enhanced Financial Analysis

-   Monthly spending curves.
-   Cash-flow comparisons.
-   Useful micro-charts.
-   Financial position trends.
-   Recurring-spend analysis.

Charts and advanced visualizations should only be added when they
improve understanding.

### Phase E --- Compact Viewports

-   Tablet refinement.
-   Mobile layouts.
-   Drawer/bottom-sheet interactions.
-   Touch-friendly controls.

------------------------------------------------------------------------

## 35. Final Design Principle

When deciding between two UI approaches, choose the one that makes the
financial information easier to understand.

The MyMonee interface should consistently communicate:

``` text
             WHAT HAPPENED?
                    ↓
              HOW MUCH?
                    ↓
              WHERE DID IT GO?
                    ↓
              WHAT CHANGED?
                    ↓
             WHAT NEEDS ATTENTION?
                    ↓
              SHOW ME THE DETAILS
```

The product should feel **quiet, trustworthy, practical, and
intelligent**.

Not because it contains more UI.

Because it makes the user's financial information easier to understand.
