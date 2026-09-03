---
name: mymonee
description: "Local-first personal finance and expense ledger. Query spending totals, category breakdowns, merchant history, subscriptions, salary attribution, and transactions via MyMonee MCP."
version: 1.0.0
author: MyMonee
license: MIT
platforms: [macos]
metadata:
  hermes:
    tags: [Finance, Expenses, Budget, Spending, Money, MCP, Ledger]
prerequisites:
  mcp: [mymonee]
---

# MyMonee Personal Finance & Expense Ledger

Use this skill when the user asks questions about their personal finances, spending, budget categories, merchants, subscriptions, salary, income, or transaction history.

MyMonee is a local-first personal financial ledger. The tools are exposed via the `mymonee` MCP server under the prefix:
`mcp__mymonee__<tool_name>`

---

## Core Invariants & Financial Rules

1. **Treat Aggregates as Authoritative**:
   - Always prefer `mcp__mymonee__get_financial_summary` or `mcp__mymonee__get_category_spending` over summing up results from `mcp__mymonee__search_transactions`.
   - MyMonee's aggregate calculations already apply canonical financial filters: they **exclude credit card bill payments, internal account transfers, duplicate alerts, and refunds**. If you try to sum raw transactions yourself, you will double-count transfers or count credit card payments as expenses.

2. **Salary & Pay-Period Attribution**:
   - Salary credits in India (particularly Axis Bank `/Sala` credits) often arrive at the end of the month or early next month.
   - MyMonee handles pay-period attribution rules internally (e.g., salary credited after the 2nd of the month counts toward the *next* month's budget).
   - Use `mcp__mymonee__get_income_and_salary` to get authoritative monthly salary and total income.

3. **Currency & Formatting**:
   - All amounts are in Indian Rupees (`INR`). Present amounts to the user using standard rupee formatting with the `₹` symbol (e.g., `₹38,697.88`).
   - All tool responses use string-formatted decimal `Money` objects (`{"amount": "420.00", "currency": "INR"}`) to eliminate floating-point rounding errors.

4. **Privacy & Identifiers**:
   - Account and card numbers are masked (`•••• 1234`).
   - Entity identifiers are opaque public IDs (`txn_...`, `merch_...`). Do not guess or modify them.
   - PII, email bodies, OAuth tokens, and database file paths are strictly redacted by MyMonee.

5. **Classification & External Brain (P1 Rule)**:
   - You act as the **External Brain** of MyMonee's categorization system.
   - Use `mcp__mymonee__get_unclassified_spends` to retrieve transactions from the "Needs Review" queue.
   - When categorizing, match against standard categories from `mcp__mymonee__list_budget_categories`.
   - Calling `mcp__mymonee__classify_transaction` records a user correction and persists a deterministic merchant classification rule (`create_rule=true`) so MyMonee remembers this merchant permanently.
   - If the user asks to categorize all past transactions from this merchant as well, set `apply_to_past=true`.

---

## When to Use

- User asks "How much did I spend this month / last month?"
- User asks about spending in specific categories ("How much did I spend on food / utilities / travel?")
- User asks about recent purchases or spending at a specific merchant ("How much have I spent on Zepto / Amazon?")
- User asks for specific transactions ("Find my transactions above ₹5000" or "Show transactions from last week")
- User asks about recurring expenses ("What subscriptions or recurring bills do I have?")
- User asks about their salary or total income ("What was my income over the last 3 months?")
- User asks about savings or cash flow trends ("Am I saving money?" or "Show my cash flow trajectory")
- User asks what expense categories exist in their budget.
- User asks to see unclassified transactions ("What transactions need review?" or "Show unclassified expenses").
- User instructs you to categorize a transaction ("Classify that ₹219 purchase as Entertainment > Subscriptions").
- You want to proactively inspect unclassified items and suggest appropriate categories to the user.

---

## When NOT to Use

- Real-time stock, mutual fund NAV, or cryptocurrency market quotes (MyMonee is an expense/income ledger, not a market ticker).
- Deleting transactions or modifying ledger accounts (transaction history is durable and immutable).
- Managing bank credentials or syncing email accounts.

---

## Tool Reference & Routing Guide

### 1. `mcp__mymonee__get_financial_summary`
Use for monthly overviews and general spending questions.
- **Parameters**:
  - `month`: `"current"`, `"last"`, or `"YYYY-MM"` (e.g., `"2026-08"`). Default is `"current"`.
- **Returns**:
  - Total qualifying spent, consumer living spend, commitments, income, net cash flow, month-over-month % change, top 5 categories, and top 5 merchants.
- **Example user queries**:
  - *"How much did I spend this month?"*
  - *"Give me a summary of August 2026 finances."*
  - *"What were my top expense categories this month?"*

### 2. `mcp__mymonee__get_category_spending`
Use to inspect spending by category, either across all categories or deep-diving into one.
- **Parameters**:
  - `category`: Category name (e.g. `"Food"`, `"Utilities"`, `"Travel"`). If omitted or `null`, returns spending across all categories.
  - `month`: `"current"`, `"last"`, or `"YYYY-MM"`.
  - `range`: `"1m"`, `"3m"`, `"6m"`, `"12m"`, or `"ytd"`. Default is `"1m"`.
- **Returns**:
  - When `category` is specified: Period total, previous period total, current month total, median ticket size, average ticket size, subcategory breakdown, top merchants in this category, and automated rule-based insights.
- **Example user queries**:
  - *"Break down my spending across all categories."*
  - *"How much did I spend on Food over the last 3 months?"*
  - *"Tell me about my Utilities expenses this year."*

### 3. `mcp__mymonee__get_merchant_history`
Use to analyze spending with a specific store, vendor, or merchant.
- **Parameters**:
  - `merchant_name`: Merchant name string (e.g. `"Zepto"`, `"Amazon"`, `"Swiggy"`).
  - `months`: Number of historical months to examine (default `6`, max `24`).
  - `limit`: Number of recent transactions to return (default `5`, max `25`).
- **Returns**:
  - Total spent with merchant, transaction count, average ticket size, first seen date, last seen date, and recent purchases with masked accounts.
- **Example user queries**:
  - *"How much have I spent on Zepto recently?"*
  - *"What's my spending history with Swiggy?"*

### 4. `mcp__mymonee__search_transactions`
Use to locate specific transaction records matching filters.
- **Parameters**:
  - `query`: Free-text search term (matches merchant or description).
  - `category`: Filter by category name.
  - `direction`: `"debit"` (default), `"credit"`, or `"all"`.
  - `start_date`: `"YYYY-MM-DD"`.
  - `end_date`: `"YYYY-MM-DD"`.
  - `min_amount`: Minimum amount in INR.
  - `max_amount`: Maximum amount in INR.
  - `limit`: Number of records (default `10`, max `50`).
  - `cursor`: Pagination cursor from previous response.
- **Returns**:
  - List of sanitized transaction items (`date`, `amount`, `merchant`, `category`, `subcategory`, `account_masked`, `payment_method`, `description`), `has_more` boolean, and `next_cursor`.
- **Example user queries**:
  - *"Show me my last 5 debit transactions."*
  - *"Find transactions over ₹10,000 in August."*
  - *"Did I pay for Jio recharge this week?"*

### 5. `mcp__mymonee__get_recurring_expenses`
Use to list active subscriptions and scheduled bills.
- **Parameters**: None.
- **Returns**:
  - Active subscriptions (service name, amount, billing frequency, next due date, annual cost) and scheduled recurring bills, along with total monthly burn rate and annual cost.
- **Example user queries**:
  - *"What subscriptions am I paying for?"*
  - *"What are my recurring monthly bills?"*
  - *"How much do I spend on subscriptions each year?"*

### 6. `mcp__mymonee__get_income_and_salary`
Use for income and salary attribution questions.
- **Parameters**:
  - `months`: Lookback months (default `6`, max `24`).
- **Returns**:
  - Monthly breakdown of salary income vs. other income, plus recent salary credits mapped to pay-periods.
- **Example user queries**:
  - *"What was my salary for the last 3 months?"*
  - *"How much total income did I receive this month?"*

### 7. `mcp__mymonee__get_cash_flow_trends`
Use for multi-month trajectory and savings rate.
- **Parameters**:
  - `months`: Historical months (default `6`, max `24`).
- **Returns**:
  - Chronological list of monthly points with total qualifying spent, income, and net cash flow (`income - spent`).
- **Example user queries**:
  - *"Am I saving money over the last 6 months?"*
  - *"Show me my cash flow trend."*

### 8. `mcp__mymonee__list_budget_categories`
Use to check valid category and subcategory names.
- **Parameters**: None.
- **Returns**:
  - Complete list of taxonomy categories and their subcategories.
- **Example user queries**:
  - *"What expense categories are configured in my tracker?"*

### 9. `mcp__mymonee__get_unclassified_spends`
Use to inspect transactions that are currently in the "Needs Review" queue waiting for a category.
- **Parameters**:
  - `limit`: Number of items to fetch (default `10`, max `50`).
  - `cursor`: Opaque pagination cursor.
- **Returns**:
  - Total pending count, item list (`public_id`, `date`, `amount`, `merchant`, `description`, `account_masked`, `direction`, `suggested_category`), and `next_cursor`.
- **Example user queries**:
  - *"Show my unclassified spends."*
  - *"What transactions need my review?"*
  - *"Do I have any uncategorized expenses from this week?"*

### 10. `mcp__mymonee__classify_transaction`
Use to apply a category classification to an unreviewed transaction. Automatically records a user correction and creates a persistent rule.
- **Parameters**:
  - `transaction_id`: The opaque `txn_...` ID returned by `get_unclassified_spends` or `search_transactions`.
  - `category`: The category name or slug (e.g., `"Food"`, `"Entertainment"`). Must match a valid category from `list_budget_categories`.
  - `subcategory`: Optional subcategory name or slug (e.g., `"Groceries"`, `"Subscriptions"`).
  - `create_rule`: Boolean (default `true`). When `true`, persists a permanent merchant classification rule so MyMonee classifies future emails automatically.
  - `apply_to_past`: Boolean (default `false`). When `true`, also backfills past unreviewed transactions from the same merchant.
  - `reasoning`: Optional short note explaining why this category was selected.
- **Returns**:
  - Outcome status, assigned category & subcategory names/slugs, `rule_created` boolean, `backfilled_count`, and a confirmation message.
- **Example user queries**:
  - *"Classify txn_... as Entertainment > Subscriptions"*
  - *"Categorize that ₹60 Doddla Pushpa expense as Food > Groceries and remember it for all future transactions"*
  - *"Set this merchant to Utilities and update past transactions too"*

---

## Response Formatting Recommendations

1. **Be Concise and Direct**:
   Start with the answer to the user's primary question (e.g. *"You spent ₹38,697.88 in September 2026."*).
2. **Use Formatted Markdown**:
   - Use clean tables or bulleted lists for category breakdowns and merchant lists.
   - Format rupee amounts with commas and symbol: `₹20,000.00`.
   - Calculate percentages where helpful (e.g., *"Food accounted for 24% of living expenses"*).
3. **Highlight Key Insights**:
   - Note significant month-over-month shifts (e.g., *"Spending dropped by 86.3% compared to August"*).
   - If user asks about budget or overspending, check the insights block returned by `get_category_spending`.
