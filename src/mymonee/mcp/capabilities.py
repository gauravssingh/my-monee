"""Static capability registry for MyMonee Agent integration.

Operating law:
- Static dictionary mapping capability names to handler specs
- No dynamic dispatch via getattr/eval/exec
- Test assertion: registered MCP tools == set(AGENT_CAPABILITIES.keys())
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CapabilitySpec:
    name: str
    version: str
    description: str
    method_name: str
    read_only: bool = True


AGENT_CAPABILITIES: dict[str, CapabilitySpec] = {
    "get_financial_summary": CapabilitySpec(
        name="get_financial_summary",
        version="1.0",
        description=(
            "Returns MyMonee's authoritative monthly financial calculation. Spending excludes transfers, "
            "credit-card bill payments, duplicate records, and refunds by canonical spending filters. "
            "Treat returned aggregate values as authoritative and do not independently reconstruct them from raw transactions."
        ),
        method_name="get_financial_summary",
        read_only=True,
    ),
    "get_category_spending": CapabilitySpec(
        name="get_category_spending",
        version="1.0",
        description=(
            "Returns spending breakdown across all categories or a deep-dive into a specific category. "
            "For a single category, includes subcategories, median ticket, top merchants, 3-month trailing average, "
            "and rule-based insights. Supported ranges: '1m', '3m', '6m', '12m', 'ytd'."
        ),
        method_name="get_category_spending",
        read_only=True,
    ),
    "get_merchant_history": CapabilitySpec(
        name="get_merchant_history",
        version="1.0",
        description=(
            "Returns total spending, transaction count, average ticket size, first/last seen dates, "
            "and recent transactions for a merchant. Accounts are masked to last 4 digits."
        ),
        method_name="get_merchant_history",
        read_only=True,
    ),
    "search_transactions": CapabilitySpec(
        name="search_transactions",
        version="1.0",
        description=(
            "Search and filter recent transactions without exposing raw database IDs or PII. "
            "Returns sanitized transaction records with masked accounts ('•••• 1234'). Maximum limit is 50."
        ),
        method_name="search_transactions",
        read_only=True,
    ),
    "get_recurring_expenses": CapabilitySpec(
        name="get_recurring_expenses",
        version="1.0",
        description=(
            "Lists active recurring subscriptions (e.g. Netflix, Spotify, iCloud) and scheduled bills "
            "with amounts, billing frequencies, next due dates, and estimated annual costs."
        ),
        method_name="get_recurring_expenses",
        read_only=True,
    ),
    "get_income_and_salary": CapabilitySpec(
        name="get_income_and_salary",
        version="1.0",
        description=(
            "Returns salary and income by pay-period over the last N months. Accurately maps salary credits "
            "to the month they pay for using MyMonee's Axis /Sala and calendar pay-period attribution rules."
        ),
        method_name="get_income_and_salary",
        read_only=True,
    ),
    "get_cash_flow_trends": CapabilitySpec(
        name="get_cash_flow_trends",
        version="1.0",
        description=(
            "Returns multi-month cash flow trajectory comparing total qualifying spent, income, "
            "and net savings/deficit month-by-month."
        ),
        method_name="get_cash_flow_trends",
        read_only=True,
    ),
    "list_budget_categories": CapabilitySpec(
        name="list_budget_categories",
        version="1.0",
        description=(
            "Returns the authoritative MyMonee category and subcategory taxonomy. "
            "Use exact category names from this list when querying category spending."
        ),
        method_name="list_budget_categories",
        read_only=True,
    ),
    "get_agent_capabilities": CapabilitySpec(
        name="get_agent_capabilities",
        version="1.0",
        description="Returns contract versioning metadata and supported capability names.",
        method_name="get_agent_capabilities",
        read_only=True,
    ),
    "get_unclassified_spends": CapabilitySpec(
        name="get_unclassified_spends",
        version="1.0",
        description=(
            "Returns pending transactions in the 'Needs Review' queue requiring categorization. "
            "Includes sanitized merchant name, amount, date, masked account, and an opaque public transaction ID. "
            "Use this tool to find transactions that need your classification intelligence."
        ),
        method_name="get_unclassified_spends",
        read_only=True,
    ),
    "classify_transaction": CapabilitySpec(
        name="classify_transaction",
        version="1.0",
        description=(
            "Classifies an unreviewed transaction with a category and optional subcategory. "
            "Automatically records a user correction and persists a deterministic merchant classification rule "
            "(when create_rule=True) so MyMonee remembers this merchant permanently for future email syncs. "
            "Can also backfill past unreviewed transactions from the same merchant (when apply_to_past=True)."
        ),
        method_name="classify_transaction",
        read_only=False,
    ),
}

AGENT_CAPABILITY_NAMES: frozenset[str] = frozenset(AGENT_CAPABILITIES.keys())
