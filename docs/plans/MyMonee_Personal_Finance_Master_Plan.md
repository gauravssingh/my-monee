# MyMonee — Complete Personal Finance Application
## Product Features, Architecture & Phased Development Plan

**Document status:** Product / Technical Master Plan  
**Target platform:** macOS, local-first  
**Primary use case:** Single-user personal finance management and financial intelligence  
**Current foundation:** Local transaction ingestion, Gmail OAuth, transaction normalization, classification, deduplication, refunds/transfers, and a learning-oriented classification engine.

---

# 1. Product Vision

MyMonee should evolve from a personal expense tracker into a **local-first personal financial operating system**.

The application should answer five questions whenever the user opens it:

1. **Where am I financially?**
   - Net worth
   - Cash
   - Investments
   - Debt
   - Assets

2. **What happened?**
   - Income
   - Spending
   - Transfers
   - Investments
   - Debt payments
   - Refunds

3. **What is coming?**
   - Bills
   - Recurring expenses
   - Expected income
   - EMI payments
   - Upcoming obligations
   - Projected cash position

4. **What is unusual?**
   - Spending spikes
   - Merchant anomalies
   - Category deviations
   - Duplicate transactions
   - Unexpected bills
   - Cash-flow risks

5. **What needs my attention?**
   - Transactions needing classification
   - Reconciliation differences
   - Unmatched refunds
   - Unknown merchants
   - Failed ingestion
   - Missing account data

The core product principle is:

> **Build a reliable financial data model first; use AI to make that data intelligent, explainable, and actionable.**

---

# 2. Product Principles

## 2.1 Local-first

The Mac is both the server and client.

Default architecture:

```text
macOS
 ├── FastAPI
 ├── SQLite
 ├── Scheduler
 ├── Local Web UI
 ├── macOS Keychain
 └── Local intelligence
          │
          └── Gmail API / optional external AI
```

Financial data should never leave the Mac unless the user explicitly enables a feature that requires external processing.

## 2.2 Privacy by default

- OAuth tokens in macOS Keychain.
- Financial data in local SQLite.
- No cloud database.
- No telemetry by default.
- No full card numbers.
- Mask account information.
- Do not store complete email bodies unless explicitly enabled.
- External AI disabled by default.
- Clearly indicate when financial data will leave the machine.

## 2.3 Deterministic before AI

Use:

```text
Exact rule
    ↓
Historical verified match
    ↓
Statistical / similarity model
    ↓
Local AI
    ↓
Optional cloud AI
    ↓
User review
    ↓
Learned rule
```

AI should not be responsible for basic correctness.

## 2.4 Explainability

Every important automated decision should answer:

> Why did MyMonee do this?

For example:

```text
Category: Dining
Confidence: 96%

Reasons:
- Merchant previously classified as Dining 14 times.
- Same UPI merchant ID used in 9 verified transactions.
- Amount/date pattern consistent with prior transactions.
```

---

# 3. High-Level Architecture

```text
┌───────────────────────────────────────────────────────────────┐
│                         MyMonee UI                            │
│                                                               │
│ Dashboard · Money · Spending · Planning · Wealth · AI        │
└──────────────────────────────┬────────────────────────────────┘
                               │
┌──────────────────────────────▼────────────────────────────────┐
│                     Financial Domain                          │
│                                                               │
│ Accounts · Events · Postings · Transactions · Categories      │
│ Transfers · Liabilities · Assets · Budgets · Goals           │
│ Recurring · Bills · Investments · Loans                       │
└──────────────────────────────┬────────────────────────────────┘
                               │
┌──────────────────────────────▼────────────────────────────────┐
│                 Intelligence & Analytics                      │
│                                                               │
│ Classification · Merchant Intelligence · Forecasting          │
│ Recurring Detection · Anomaly Detection · Insights            │
│ Financial Health · Personal Financial Model                    │
└──────────────────────────────┬────────────────────────────────┘
                               │
┌──────────────────────────────▼────────────────────────────────┐
│                 Reconciliation Engine                         │
│                                                               │
│ Deduplication · Matching · Transfers · Refunds · EMI          │
│ Balance Reconciliation · Account Linking                       │
└──────────────────────────────┬────────────────────────────────┘
                               │
┌──────────────────────────────▼────────────────────────────────┐
│                      Data Connectors                           │
│                                                               │
│ Gmail · CSV · Statements · Bank Data · UPI · Investment Data  │
│ Manual Entry · Future APIs                                     │
└───────────────────────────────────────────────────────────────┘
```

---

# 4. Core Financial Model

The existing transaction-centric model should evolve into an account/event/ledger-oriented model.

The four foundational concepts are:

```text
Account
Financial Event
Posting
Category
```

Everything else should build around them.

## 4.1 Account

An account represents a financial container.

Examples:

```text
HDFC Savings
HDFC Salary Account
HDFC Credit Card
ICICI Credit Card
Cash
Groww Investment Account
EPF
Home Loan
Car Loan
```

Suggested schema:

```text
accounts
---------
id
name
institution_id
account_type
currency
account_number_masked
card_last4
upi_identifier_masked
status
is_asset
is_liability
credit_limit
opening_balance
opening_date
current_balance
metadata_json
created_at
updated_at
```

Account types:

```text
ASSET
 ├── BANK
 ├── CASH
 ├── WALLET
 ├── INVESTMENT
 ├── PF
 └── OTHER_ASSET

LIABILITY
 ├── CREDIT_CARD
 ├── PERSONAL_LOAN
 ├── HOME_LOAN
 ├── CAR_LOAN
 └── OTHER_LIABILITY
```

---

# 5. Financial Events and Postings

The application should not depend on transaction rows as the ultimate source of truth.

Introduce:

```text
financial_events
postings
```

A financial event represents something that happened.

A posting represents its effect on an account.

Example: purchase using credit card:

```text
Financial Event
-----------------------------
Amazon purchase
₹3,500

Postings
-----------------------------
Shopping expense       +₹3,500
HDFC Credit Card       +₹3,500 liability
```

Credit-card payment:

```text
Financial Event
-----------------------------
Credit card payment
₹3,500

Postings
-----------------------------
HDFC Bank               -₹3,500
HDFC Credit Card        -₹3,500 liability
```

The second event is a transfer and must not count as spending.

This model supports:

- Purchases
- Transfers
- Refunds
- Reversals
- Credit-card payments
- Cash withdrawals
- Deposits
- Investments
- Investment sales
- Loan payments
- EMI
- Reimbursements
- Adjustments

Suggested structure:

```text
financial_events
----------------
id
event_type
event_date
source
source_reference
description
status
metadata_json
created_at
updated_at

postings
--------
id
event_id
account_id
category_id
amount
direction
posting_type
metadata_json
```

---

# 6. Transaction Layer

Transactions remain a user-friendly representation of financial activity.

The existing canonical transaction fields should be retained and expanded.

Core fields:

```text
id
financial_event_id
source
source_email_id
source_thread_id

transaction_date
posted_date

amount
currency
direction
transaction_type

merchant_raw
merchant_normalized
merchant_entity_id

payment_method
account_id
card_last4
upi_id

reference_number
bank_reference

description
location

category_id
subcategory_id

classification_confidence
classification_source
classification_signals
user_verified

parent_transaction_id

is_duplicate
is_refund
is_transfer
excludes_from_spending

extra_json

created_at
updated_at
```

The existing architecture already defines many of these concepts and should be extended rather than discarded.

---

# 7. Institutions

Create a normalized institution layer.

```text
institutions
------------
id
name
institution_type
country
logo_reference
metadata_json
```

Examples:

```text
HDFC Bank
ICICI Bank
Axis Bank
SBI
American Express
Groww
Zerodha
Coin
```

Benefits:

- Better account grouping.
- Consistent merchant/institution identity.
- Easier future connectors.
- Cleaner dashboard.

---

# 8. Income Management

Income should be modeled separately from generic credits.

Categories:

```text
Income
 ├── Salary
 ├── Bonus
 ├── Freelance
 ├── Business
 ├── Interest
 ├── Dividends
 ├── Rental
 ├── Reimbursement
 └── Other
```

Track:

```text
income_sources
--------------
id
name
category_id
account_id
expected_amount
frequency
next_expected_date
confidence
```

This enables:

- Income history.
- Expected salary.
- Income variance.
- Monthly savings rate.
- Cash-flow forecasting.

---

# 9. Spending Classification

The current classification architecture should become a central intelligence service.

Decision pipeline:

```text
Normalize merchant
       ↓
Exact rule?
       ├── yes → classify
       ↓ no
Verified historical match?
       ├── yes → classify
       ↓ no
Similarity model
       ├── high confidence → classify
       ↓
Local AI
       ├── high confidence → classify
       ↓
Needs Review
       ↓
User correction
       ↓
Learn rule
```

Sources:

```text
rule
historical
model
ai
user
unknown
```

Every classification should retain:

```text
confidence
source
signals
model_version
rule_id
verified_at
```

---

# 10. Merchant Intelligence

Create a merchant entity layer.

```text
merchants
---------
id
canonical_name
display_name
category_hint
merchant_type
default_category_id
default_subcategory_id
metadata_json

merchant_aliases
----------------
id
merchant_id
raw_value
normalized_value
source
confidence
```

Examples:

```text
"AMZN MKTPL"
"AMAZON PAY"
"AMAZON.IN"
"Amazon Seller"

        ↓

Amazon
```

Merchant intelligence should support:

- Canonical names.
- Aliases.
- Merchant category.
- UPI identifiers.
- Payment descriptions.
- Location.
- Historical classification.
- Spending trends.

---

# 11. Categories

Use a hierarchical category system.

Example:

```text
Housing
 ├── Rent
 ├── Electricity
 ├── Water
 ├── Internet
 └── Maintenance

Food
 ├── Groceries
 ├── Restaurants
 ├── Delivery
 ├── Coffee
 └── Snacks

Transportation
 ├── Fuel
 ├── Uber
 ├── Ola
 ├── Metro
 └── Parking

Shopping
 ├── Electronics
 ├── Clothing
 ├── Household
 └── Other

Financial
 ├── Insurance
 ├── Bank Fees
 ├── Loan Interest
 └── Investment Fees
```

Add a second classification dimension:

```text
expense_type
------------
essential
discretionary
financial
investment
transfer
```

---

# 12. Recurring Transactions

Automatically detect recurring activity.

Signals:

```text
merchant
amount
date interval
account
category
description
```

Example:

```text
Netflix
₹649
Monthly
Confidence: 98%

Internet
₹999
Monthly
Confidence: 94%

Insurance
₹24,500
Annual
Confidence: 91%
```

Schema:

```text
recurring_transactions
----------------------
id
merchant_id
account_id
category_id
expected_amount
frequency
interval_days
next_expected_date
amount_variance
confidence
status
```

---

# 13. Subscriptions

Recurring transactions and subscriptions should be distinct.

A subscription represents an ongoing service relationship.

```text
subscriptions
-------------
id
merchant_id
name
amount
billing_frequency
next_billing_date
annual_cost
account_id
category_id
status
first_detected_at
last_detected_at
```

Features:

- Subscription discovery.
- Annual cost.
- Monthly equivalent cost.
- Price increase detection.
- Forgotten subscription detection.
- Subscription utilization notes if manually provided.

---

# 14. Bills and Obligations

Bills represent financial obligations.

```text
bills
-----
id
name
account_id
merchant_id
expected_amount
minimum_amount
due_date
frequency
autopay
status
category_id
```

Examples:

```text
Credit Card
Electricity
Internet
Insurance
Home Loan
Car Loan
School Fee
Rent
```

Dashboard:

```text
Upcoming 7 Days

Credit Card       ₹42,350
Electricity        ₹3,120
Home Loan EMI     ₹38,500

Total             ₹83,970
```

---

# 15. Budgeting

Budgets should be based on actual financial behavior.

Schema:

```text
budgets
-------
id
name
period
category_id
amount
rollover_enabled
status

budget_periods
--------------
id
budget_id
start_date
end_date
allocated_amount
spent_amount
projected_amount
remaining_amount
```

Show:

```text
Food

Budget             ₹12,000
Spent               ₹9,240
Projected          ₹12,430

Projected variance   +₹430
```

The system should forecast the end-of-period value instead of simply showing current spending.

---

# 16. Cash-Flow Forecasting

Build a 30/60/90-day cash-flow engine.

Inputs:

```text
Current account balances
Expected salary
Recurring income
Upcoming bills
Recurring expenses
EMIs
Known investments
Planned transfers
```

Output:

```text
Date
Expected balance
Confidence
Events affecting balance
```

Example:

```text
Today             ₹1,42,000
Salary           +₹1,85,000
Rent              -₹35,000
EMIs              -₹52,000
Bills             -₹14,000

Projected month-end:
₹2,26,000
```

Add confidence bands when forecasts become sophisticated.

---

# 17. Assets

Create an asset model.

```text
assets
------
id
name
asset_type
account_id
purchase_value
current_value
valuation_date
ownership
metadata_json
```

Asset types:

```text
Cash
Property
Vehicle
Gold
FD
EPF
PPF
Stocks
Mutual Funds
Bonds
Other
```

Not all assets need automatic valuation initially.

---

# 18. Liabilities

Create a liability model.

```text
liabilities
-----------
id
name
liability_type
account_id
principal
outstanding
interest_rate
start_date
maturity_date
minimum_payment
scheduled_payment
metadata_json
```

Types:

```text
Credit Card
Home Loan
Car Loan
Personal Loan
Education Loan
Other
```

---

# 19. Loans and EMI

EMIs require special treatment.

Example:

```text
EMI = ₹42,000

Principal       ₹31,500
Interest        ₹10,500
```

The principal reduces liability.

The interest is an expense.

Create:

```text
loans
-----
id
name
account_id
principal
interest_rate
tenure_months
emi
start_date
maturity_date

loan_schedules
-------------
id
loan_id
due_date
principal
interest
emi
opening_balance
closing_balance
status

loan_payments
-------------
id
loan_id
transaction_id
principal
interest
payment_date
```

This makes debt analytics accurate.

---

# 20. Net Worth

Net worth becomes one of the primary product metrics.

```text
Net Worth = Total Assets - Total Liabilities
```

Dashboard:

```text
Net Worth

₹55.2L

Assets
Bank             ₹4.8L
Investments     ₹38.5L
EPF              ₹7.1L
Other            ₹1.9L

Liabilities
Credit Cards     ₹0.8L
Home Loan        ₹9.4L
Other            ₹0.3L
```

Track historical net worth:

```text
Month     Net Worth
Jan       ₹48.0L
Feb       ₹49.1L
Mar       ₹50.0L
Apr       ₹50.8L
May       ₹52.0L
Jun       ₹53.2L
Jul       ₹54.1L
Aug       ₹55.2L
```

---

# 21. Investments

Investment management should be its own subsystem.

Support:

```text
Stocks
Mutual Funds
ETFs
Bonds
Fixed Deposits
EPF
PPF
Gold
Other investments
```

Core entities:

```text
investment_accounts
investment_holdings
investment_transactions
investment_prices
```

Track:

```text
Cost basis
Current value
Unrealized gain/loss
Realized gain/loss
XIRR
Allocation
Asset class
Investment account
```

Portfolio view:

```text
Equity           48%
Mutual Funds     22%
EPF              10%
FD                6%
Gold              2%
Cash              12%
```

Investment market data can remain optional and separately configurable.

---

# 22. Goals

Introduce financial goals.

Examples:

```text
Emergency Fund
Vacation
New Car
House Down Payment
Child Education
Retirement
```

Schema:

```text
goals
-----
id
name
target_amount
current_amount
target_date
priority
category
status

goal_contributions
------------------
id
goal_id
amount
date
source_account_id
transaction_id
```

Goal intelligence:

```text
Goal: Vacation

Target: ₹2,00,000
Current: ₹1,20,000
Target date: Dec 2026

Required monthly contribution:
₹26,700

Current contribution:
₹20,000

Status:
Behind by ₹6,700/month
```

---

# 23. Financial Health Engine

Calculate a set of personal finance metrics.

## Savings Rate

```text
Savings Rate =
(Income - Spending) / Income
```

## Investment Rate

```text
Investment Rate =
Investment Contributions / Income
```

## Fixed Expense Ratio

```text
Fixed Expenses / Income
```

## Debt Service Ratio

```text
Debt Payments / Income
```

## Emergency Fund Coverage

```text
Liquid Assets / Monthly Essential Expenses
```

## Net Worth Growth

```text
Current Net Worth - Previous Net Worth
```

These should become time-series metrics.

---

# 24. Anomaly Detection

Identify:

- Unusually large transaction.
- Category spending spike.
- Merchant spending spike.
- Unexpected recurring payment.
- Duplicate payment.
- Unusual bill.
- New merchant.
- Unexpected credit.
- Unusual cash withdrawal.
- Significant deviation from historical behavior.

Example:

```text
⚠ Electricity spending anomaly

Current:
₹5,820

6-month average:
₹3,210

Deviation:
+81%
```

---

# 25. Personal Financial Intelligence

Build an intelligence layer on top of structured data.

Examples:

### Spending explanation

> Dining spending is 38% higher than your six-month average, primarily because of five unusually large weekend transactions.

### Subscription insight

> You spent ₹4,788 on this subscription in the last 12 months.

### Cash-flow insight

> Your projected cash balance may fall below ₹50,000 around September 22.

### Merchant insight

> Amazon spending increased 42% compared with your previous three-month average.

### Budget insight

> You are currently on track to exceed the Dining budget by approximately ₹1,200.

---

# 26. Financial Context Layer for AI

Never give a general-purpose LLM unrestricted access to the raw database.

Create a controlled financial context service:

```text
FinancialContext
----------------
current_balances
monthly_income
monthly_expenses
category_spending
merchant_spending
recurring_expenses
upcoming_bills
debts
investments
net_worth
goals
anomalies
financial_health
```

Example request:

```text
User:
"Why did I spend more this month?"
```

Pipeline:

```text
Question
   ↓
Intent detection
   ↓
Financial context retrieval
   ↓
Deterministic calculations
   ↓
Comparison
   ↓
Relevant transactions
   ↓
AI explanation
```

The AI explains the data. It does not invent the numbers.

---

# 27. Dashboard Information Architecture

```text
🏠 Dashboard

💳 Money
   ├── Accounts
   ├── Transactions
   ├── Transfers
   └── Reconciliation

📊 Spending
   ├── Overview
   ├── Categories
   ├── Merchants
   ├── Trends
   └── Budgets

📅 Planning
   ├── Bills
   ├── Recurring
   ├── Subscriptions
   ├── Cash Flow
   └── Goals

💰 Wealth
   ├── Net Worth
   ├── Investments
   ├── Assets
   └── Liabilities

🧠 Intelligence
   ├── Insights
   ├── Anomalies
   ├── Recommendations
   └── Needs Review

⚙️ System
   ├── Connections
   ├── Sync
   ├── Rules
   ├── Classification
   ├── Backup
   └── Privacy
```

---

# 28. Home Dashboard

The home dashboard should prioritize decisions, not raw data.

## Financial position

```text
Net Worth       ₹55.2L
Cash            ₹4.8L
Investments    ₹38.5L
Debt           ₹12.1L
```

## Current month

```text
Income          ₹2.15L
Expenses        ₹1.28L
Investments     ₹35K
Net Cash Flow   +₹52K
```

## Upcoming

```text
Bills           ₹62K
Expected Income ₹1.85L
Projected Cash  ₹2.14L
```

## Alerts

```text
⚠ Dining +38%
⚠ Electricity +63%
⚠ Amazon +₹8,400
```

## Attention

```text
7 transactions need classification
2 possible duplicates
1 unmatched refund
1 reconciliation difference
```

---

# 29. Transactions UI

Transactions should support:

- Search.
- Date range.
- Account.
- Merchant.
- Category.
- Amount.
- Direction.
- Transaction type.
- Confidence.
- Classification source.
- Needs review.
- Transfer.
- Refund.
- Duplicate.
- Recurring.

Bulk actions:

```text
Select 20
→ Categorize
→ Mark transfer
→ Mark duplicate
→ Verify
→ Reclassify
```

Keyboard-first classification should be supported.

---

# 30. Reconciliation UI

For each account:

```text
Account Balance
-------------------------
Statement       ₹184,532
MyMonee         ₹184,517
Difference           ₹15

Potential causes
-------------------------
1. Missing transaction
2. Incorrect opening balance
3. Bank fee
4. Duplicate transaction
```

Allow:

- Add adjustment.
- Link transaction.
- Mark reconciled.
- Ignore difference.
- Re-run reconciliation.

---

# 31. Import and Connector Framework

Connector architecture:

```text
Connector
   ↓
Raw Source
   ↓
Discovery
   ↓
Parser
   ↓
Canonical Event
   ↓
Reconciliation
   ↓
Ledger
```

Initial connectors:

```text
Gmail
CSV
Manual
```

Later:

```text
Bank APIs
Open Banking
Investment APIs
Statement PDFs
Other email providers
```

Parsers should remain plugins.

---

# 32. Gmail Architecture

Use the existing OAuth architecture:

```text
Connect Gmail
      ↓
OAuth
      ↓
127.0.0.1 callback
      ↓
Token exchange
      ↓
macOS Keychain
      ↓
Gmail API
```

Minimum scope:

```text
gmail.readonly
```

Ingestion:

```text
Scheduler
   ↓
Gmail history / watermark
   ↓
Discover financial emails
   ↓
Fetch
   ↓
Persist email metadata
   ↓
Identify provider
   ↓
Parse
   ↓
Canonical event
   ↓
Deduplicate
   ↓
Reconcile
   ↓
Classify
```

---

# 33. Data Quality Framework

Every ingestion should produce quality metrics.

```text
ingestion_runs
--------------
id
started_at
completed_at
messages_scanned
financial_messages
transactions_created
transactions_updated
duplicates
parse_failures
classification_failures
reconciliation_issues
status
```

The system should expose:

```text
Sync Health
-----------
Last sync: 4 minutes ago
Messages scanned: 127
Transactions added: 19
Transactions updated: 6
Needs review: 3
Errors: 0
```

---

# 34. Backup and Restore

Implement before calling the system production-ready.

Requirements:

- SQLite backup.
- Restore.
- Export.
- Import.
- Versioned schema.
- Backup validation.
- Optional encrypted backup.
- Configuration export without secrets.
- Keychain credentials excluded from database backups.

Suggested commands:

```text
mymonee backup
mymonee restore
mymonee export
mymonee import
mymonee verify-backup
```

---

# 35. Notifications

Later add native macOS notifications.

Examples:

```text
Upcoming bill
Unusual spending
Reconciliation issue
Classification queue
Cash-flow warning
Goal milestone
Subscription renewal
```

Notifications should be configurable and never spam the user.

---

# 36. Search

Build global financial search.

Examples:

```text
Amazon last 6 months
Dining in July
transactions above ₹10,000
all HDFC credit-card payments
refunds from Amazon
subscriptions
transactions needing review
```

Search should support structured filters as well as natural language.

---

# 37. Reporting

Provide:

```text
Monthly report
Quarterly report
Annual report
Net worth report
Spending report
Tax-oriented transaction export
Investment report
Debt report
```

Exports:

```text
CSV
JSON
PDF
Excel
```

Reports should be generated from the canonical financial model.

---

# 38. API Design

FastAPI modules:

```text
/api/accounts
/api/institutions

/api/events
/api/transactions
/api/transfers

/api/categories
/api/merchants

/api/budgets
/api/bills
/api/recurring
/api/subscriptions

/api/assets
/api/liabilities
/api/loans

/api/investments

/api/goals

/api/net-worth
/api/cash-flow
/api/analytics

/api/insights
/api/anomalies

/api/connectors
/api/sync

/api/reconciliation

/api/settings
```

Keep API models separate from database models.

---

# 39. Suggested Backend Structure

```text
src/mymonee/
├── app.py
├── config.py
├── logging_setup.py
│
├── db/
│   ├── models/
│   │   ├── accounts.py
│   │   ├── transactions.py
│   │   ├── events.py
│   │   ├── postings.py
│   │   ├── categories.py
│   │   ├── merchants.py
│   │   ├── budgets.py
│   │   ├── bills.py
│   │   ├── recurring.py
│   │   ├── assets.py
│   │   ├── liabilities.py
│   │   ├── loans.py
│   │   ├── investments.py
│   │   └── goals.py
│   ├── session.py
│   └── migrations/
│
├── domain/
│   ├── enums.py
│   ├── money.py
│   └── financial_context.py
│
├── ingestion/
│   ├── pipeline.py
│   ├── discovery.py
│   ├── gmail/
│   └── csv/
│
├── parsers/
│   ├── base.py
│   ├── registry.py
│   └── providers/
│
├── reconciliation/
│   ├── dedupe.py
│   ├── transfers.py
│   ├── refunds.py
│   ├── balances.py
│   └── matching.py
│
├── classification/
│   ├── hierarchy.py
│   ├── rules.py
│   ├── historical.py
│   ├── similarity.py
│   └── ai.py
│
├── finance/
│   ├── ledger.py
│   ├── net_worth.py
│   ├── cash_flow.py
│   ├── budgets.py
│   ├── recurring.py
│   ├── loans.py
│   └── investments.py
│
├── intelligence/
│   ├── anomalies.py
│   ├── insights.py
│   ├── forecasting.py
│   ├── financial_health.py
│   └── context.py
│
├── services/
│   ├── dashboard.py
│   ├── reports.py
│   └── search.py
│
├── scheduler/
│   └── jobs.py
│
└── api/
    └── routes/
```

---

# 40. Frontend Structure

The current React/Vite direction can support the larger product.

Recommended pages:

```text
web/src/
├── pages/
│   ├── Dashboard
│   ├── Accounts
│   ├── Transactions
│   ├── Reconciliation
│   ├── Spending
│   ├── Budgets
│   ├── Bills
│   ├── Recurring
│   ├── Subscriptions
│   ├── CashFlow
│   ├── NetWorth
│   ├── Investments
│   ├── Loans
│   ├── Goals
│   ├── Insights
│   ├── Review
│   └── Settings
│
├── components/
├── hooks/
├── services/
├── types/
└── utils/
```

If the existing preference is to avoid React, the same API/domain architecture can instead be implemented with server-rendered HTML + Tailwind + lightweight JavaScript. The backend architecture should not depend on the frontend framework.

---

# 41. Phased Development Plan

## Phase 1 — Foundation

### Objective

Create a stable local financial platform.

### Scope

- SQLite.
- SQLAlchemy.
- FastAPI.
- Configuration.
- Logging.
- Database migrations.
- Canonical transactions.
- Categories.
- Basic dashboard.
- Transaction table.
- System health.
- Basic testing.

### Exit criteria

```text
Application starts locally
Database initializes
Transactions can be stored
Dashboard renders
API works
Migrations work
Backup can be created
```

---

# 42. Phase 2 — Gmail Ingestion

### Objective

Automatically discover financial transactions from Gmail.

### Scope

- Gmail OAuth.
- Keychain token storage.
- Gmail history/watermark.
- Email discovery.
- Email metadata storage.
- Parser plugin framework.
- First financial provider parsers.
- Ingestion runs.
- Idempotency.

### Exit criteria

```text
Connect Gmail
       ↓
Discover emails
       ↓
Parse transactions
       ↓
Persist canonical records
       ↓
Repeat sync without duplicates
```

---

# 43. Phase 3 — Financial Core

### Objective

Move from expense tracking to financial accounting.

### Scope

- Institutions.
- Accounts.
- Financial events.
- Postings.
- Transfers.
- Refunds.
- Reversals.
- Account balances.
- Reconciliation.
- Credit-card payments.
- Cash movements.

### Priority

This is the most important architectural phase.

### Exit criteria

MyMonee can accurately distinguish:

```text
Expense
Income
Transfer
Refund
Credit-card payment
Cash withdrawal
Adjustment
```

---

# 44. Phase 4 — Classification Intelligence

### Objective

Make categorization increasingly automatic.

### Scope

- Merchant normalization.
- Merchant entities.
- Merchant aliases.
- Category hierarchy.
- Rules.
- Historical matching.
- Similarity model.
- Confidence scoring.
- Bulk review.
- User corrections.
- Learned rules.

### Exit criteria

A large majority of recurring/predictable transactions should classify automatically while unknown transactions enter a review queue.

---

# 45. Phase 5 — Recurring, Bills and Subscriptions

### Objective

Understand future obligations.

### Scope

- Recurring detection.
- Subscription detection.
- Bills.
- Due dates.
- Autopay detection.
- Expected amount.
- Recurring income.
- Upcoming obligations dashboard.

### Exit criteria

The application can answer:

> What recurring payments do I have?

and:

> What bills are coming in the next 30 days?

---

# 46. Phase 6 — Budgeting and Cash Flow

### Objective

Move from historical reporting to planning.

### Scope

- Budgets.
- Budget periods.
- Historical baseline.
- Projected spend.
- Cash-flow forecast.
- 30/60/90-day projections.
- Income forecasting.
- Upcoming obligations.
- Cash-flow alerts.

### Exit criteria

The application can answer:

> How much money am I likely to have at month-end?

and:

> Am I likely to exceed my budget?

---

# 47. Phase 7 — Wealth and Net Worth

### Objective

Understand the complete financial position.

### Scope

- Assets.
- Liabilities.
- Net worth.
- Net-worth history.
- Account grouping.
- Manual valuations.
- Wealth dashboard.

### Exit criteria

The user can see:

```text
Assets
- Cash
- Investments
- Property
- EPF/PPF
- Other

Liabilities
- Credit cards
- Loans
- Other debt

Net Worth
```

---

# 48. Phase 8 — Loans and Investments

### Objective

Model wealth creation and debt accurately.

### Scope

### Loans

- Loan accounts.
- Interest.
- Principal.
- EMI schedules.
- Payment matching.
- Outstanding balance.
- Amortization.

### Investments

- Investment accounts.
- Holdings.
- Transactions.
- Cost basis.
- Market value.
- Gain/loss.
- Allocation.
- XIRR.

### Exit criteria

Net worth includes investment and liability data rather than only bank transactions.

---

# 49. Phase 9 — Intelligence and Anomaly Detection

### Objective

Turn data into useful observations.

### Scope

- Spending anomaly detection.
- Merchant anomaly detection.
- Category trends.
- New merchant detection.
- Subscription insights.
- Cash-flow risks.
- Budget warnings.
- Financial health metrics.
- Insight generation.

### Exit criteria

MyMonee proactively identifies important changes without requiring manual analysis.

---

# 50. Phase 10 — Goals and Financial Planning

### Objective

Help the user plan future financial outcomes.

### Scope

- Financial goals.
- Goal contributions.
- Goal forecasts.
- Emergency fund planning.
- Savings targets.
- Retirement planning foundation.
- Goal progress.
- Scenario modeling.

Example:

```text
Goal: Emergency Fund

Target: ₹6,00,000
Current: ₹3,80,000
Monthly contribution: ₹25,000

Expected completion:
May 2027
```

---

# 51. Phase 11 — AI Financial Assistant

### Objective

Make financial data conversational.

Example questions:

```text
Why did I spend more this month?

Where am I overspending?

How much did I spend on Amazon this year?

What are my recurring expenses?

What bills are coming up?

How much debt do I have?

How has my net worth changed?

Can I afford a ₹1 lakh purchase?

What changed financially this month?
```

Architecture:

```text
User Question
      ↓
Intent
      ↓
Structured financial queries
      ↓
Calculations
      ↓
Financial context
      ↓
AI explanation
```

AI should never be the primary calculator for financial facts.

---

# 52. Phase 12 — Native macOS Experience

### Objective

Turn the local web application into a polished Mac application.

### Scope

- launchd.
- Login startup.
- Menu-bar helper.
- Native notifications.
- Keychain hardening.
- Auto-update strategy.
- Native packaging.
- Health monitoring.
- Backup automation.

Possible packaging:

```text
PyInstaller
or
Briefcase
```

A thin Swift wrapper can be added if native macOS UX becomes important.

---

# 53. Future Connector Architecture

Do not hard-code Gmail as the only source.

Use:

```text
Connector
    ↓
Discovery
    ↓
Raw source
    ↓
Parser
    ↓
Canonical Event
```

Potential future connectors:

```text
Gmail
CSV
PDF statements
Bank APIs
Open Banking
Credit-card APIs
Investment APIs
Broker APIs
UPI data
Manual entry
```

The financial model must remain independent of the connector.

---

# 54. Testing Strategy

## Unit Tests

Test:

- Parsers.
- Merchant normalization.
- Classification.
- Deduplication.
- Refund matching.
- Transfer matching.
- Loan calculations.
- Budget calculations.
- Net worth.
- Cash flow.

## Integration Tests

Test:

```text
Gmail
 → parser
 → transaction
 → reconciliation
 → classification
 → account balance
```

## Financial Invariants

Examples:

```text
Transfers do not increase spending.

Credit-card payments do not increase expenses.

Refunds reduce net spending.

Loan principal reduces liability.

Loan interest increases expense.

Investment purchases move cash to investments.

Investment sales move investments to cash.

Duplicate ingestion does not change balances.
```

These invariants are critical.

---

# 55. Observability

Track:

```text
Ingestion health
Parser failures
Classification confidence
Review queue
Reconciliation differences
Database health
Scheduler health
Connector health
Backup status
```

System dashboard:

```text
MyMonee Health

Database             ✓
Gmail                ✓
Last sync             4m ago
Scheduler             ✓
Transactions          8,432
Needs review              7
Reconciliation issues     1
Parser errors             0
Last backup            1d ago
```

---

# 56. Security Architecture

## Secrets

Store only in:

```text
macOS Keychain
```

Never:

```text
SQLite
logs
Git
configuration files
```

## Financial data

SQLite locally.

## Logs

Never log:

- OAuth tokens.
- Full card numbers.
- Sensitive email bodies.
- Full UPI identifiers.
- Authentication headers.

## External AI

Require explicit opt-in.

Display:

```text
⚠ External AI enabled

Transaction information may leave this Mac.
```

---

# 57. Performance Strategy

For personal-scale data, SQLite should be more than sufficient.

Expected scale:

```text
10,000 transactions
100,000 transactions
1,000,000 transactions
```

Optimize with:

- Proper indexes.
- WAL.
- Batch ingestion.
- Bulk inserts.
- Materialized/summary tables where needed.
- Cached dashboard aggregates.
- Incremental analytics.

Do not prematurely introduce PostgreSQL.

---

# 58. Data Retention

Separate:

```text
Raw source
Canonical event
Financial record
Analytics
```

Possible retention:

```text
emails
 └── metadata retained indefinitely

raw email body
 └── optional / configurable

transactions
 └── indefinitely

financial events
 └── indefinitely

analytics
 └── rebuildable
```

Analytics should be reproducible from the canonical financial model wherever practical.

---

# 59. Migration Strategy

Existing transaction data should not be thrown away.

Migration:

```text
Existing transactions
        ↓
Create institutions
        ↓
Create accounts
        ↓
Create financial events
        ↓
Create postings
        ↓
Link existing transactions
        ↓
Validate balances
        ↓
Enable ledger as source of truth
```

Keep old fields during migration.

Use additive schema changes and migrations rather than destructive rewrites.

---

# 60. MVP Definition for the Full Product

Do not wait until every phase is complete to have a useful product.

The first genuinely valuable version should provide:

```text
✓ Gmail sync
✓ Accounts
✓ Transactions
✓ Merchant normalization
✓ Automatic classification
✓ Transfers
✓ Refunds
✓ Reconciliation
✓ Recurring detection
✓ Bills
✓ Monthly spending
✓ Net worth
✓ Cash-flow forecast
✓ Needs Review
✓ Backup
```

This is already a complete personal finance application.

---

# 61. Full Product Definition

The mature MyMonee product should provide:

```text
                    MYMONEE

Financial Position
 ├── Net Worth
 ├── Cash
 ├── Assets
 └── Liabilities

Money Movement
 ├── Accounts
 ├── Transactions
 ├── Transfers
 └── Reconciliation

Spending
 ├── Categories
 ├── Merchants
 ├── Budgets
 └── Trends

Planning
 ├── Bills
 ├── Recurring
 ├── Subscriptions
 ├── Cash Flow
 └── Goals

Wealth
 ├── Investments
 ├── Loans
 ├── Assets
 └── Net Worth

Intelligence
 ├── Classification
 ├── Anomalies
 ├── Insights
 ├── Forecasting
 └── AI Assistant

System
 ├── Gmail
 ├── Connectors
 ├── Backup
 ├── Privacy
 └── Configuration
```

---

# 62. Recommended Build Order

The most important sequencing rule is:

```text
DO NOT BUILD

AI assistant
      ↓
before
      ↓
Reliable financial model
```

Instead:

```text
1. Accounts
       ↓
2. Financial Events
       ↓
3. Postings / Ledger
       ↓
4. Transactions
       ↓
5. Reconciliation
       ↓
6. Classification
       ↓
7. Recurring / Bills
       ↓
8. Budgets / Cash Flow
       ↓
9. Net Worth
       ↓
10. Investments / Loans
       ↓
11. Analytics
       ↓
12. AI
```

The financial model is the moat.

The UI can change.

The AI model can change.

The Gmail connector can change.

But if the underlying financial model is correct, the entire application remains stable.

---

# 63. Product North Star

The eventual MyMonee experience should feel less like:

> "Here is a list of transactions."

and more like:

> **"Here is your current financial position, what changed, what is likely to happen next, and what deserves your attention."**

That is the transition from a **personal expense tracker** to a **personal financial operating system**.
