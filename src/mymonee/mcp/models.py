"""Explicit, allowlisted Agent DTOs for MyMonee MCP server.

Guarantees:
- Extra fields are forbidden (ConfigDict(extra="forbid", frozen=True))
- No raw floats for money values (Money: amount str + currency str)
- No internal database IDs leaked (stable, opaque public IDs)
- No raw email content, OAuth tokens, or unmasked account numbers
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from decimal import Decimal
from typing import Generic, TypeVar

from cryptography.fernet import Fernet, InvalidToken
from pydantic import BaseModel, ConfigDict, Field

ID_SALT = b"mymonee-agent-v1-opaque-salt"

T = TypeVar("T")


def money_from_decimal(value: Decimal | float | None, currency: str = "INR") -> Money:
    """Format numeric amount to 2-decimal string Money DTO."""
    if value is None:
        return Money(amount="0.00", currency=currency)
    dec = Decimal(str(value)).quantize(Decimal("0.01"))
    return Money(amount=f"{dec:.2f}", currency=currency)


def _get_fernet_cipher(profile: str = "default") -> Fernet:
    key_material = hashlib.sha256(ID_SALT + profile.encode("utf-8")).digest()
    b64_key = base64.urlsafe_b64encode(key_material)
    return Fernet(b64_key)


def to_public_id(prefix: str, internal_id: str | int, profile: str = "default") -> str:
    """Generate a stable, opaque, profile-scoped public identifier.

    For transactions ('txn'), uses authenticated Fernet encryption so IDs can be
    safely and reversibly resolved by Hermes during classification without ever
    leaking internal database UUIDs or allowing sequential guessing.
    """
    if prefix == "txn":
        cipher = _get_fernet_cipher(profile)
        token = cipher.encrypt(str(internal_id).encode("utf-8")).decode("utf-8")
        return f"{prefix}_{token}"
    key = ID_SALT + profile.encode("utf-8")
    raw_bytes = str(internal_id).encode("utf-8")
    digest = hmac.new(key, raw_bytes, hashlib.sha256).hexdigest()[:16]
    return f"{prefix}_{digest}"


def from_public_id(expected_prefix: str, public_id: str, profile: str = "default") -> str:
    """Resolve an opaque public identifier back to its internal identifier.

    Raises ValueError if the prefix does not match, or if the token has been tampered with.
    """
    prefix_tag = f"{expected_prefix}_"
    if not public_id.startswith(prefix_tag):
        raise ValueError(f"Invalid identifier: expected prefix '{prefix_tag}'")
    token = public_id[len(prefix_tag) :]
    try:
        cipher = _get_fernet_cipher(profile)
        decrypted = cipher.decrypt(token.encode("utf-8")).decode("utf-8")
        return decrypted
    except (InvalidToken, Exception) as err:
        raise ValueError("Invalid or tampered transaction identifier") from err


class AgentDTO(BaseModel):
    """Base DTO with strict allowlist and immutability settings."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )


class Money(AgentDTO):
    """Explicit decimal money representation avoiding floating-point ambiguity."""

    amount: str = Field(description="Decimal money amount as formatted string e.g. '420.00'")
    currency: str = Field(default="INR", description="ISO currency code e.g. 'INR'")


class Page(AgentDTO, Generic[T]):  # noqa: UP046
    """Standard pagination wrapper with bounded items and opaque cursor."""

    items: list[T]
    has_more: bool
    next_cursor: str | None = None
    total_count: int | None = None


class CategorySummaryItem(AgentDTO):
    name: str
    amount: Money
    percentage: float


class TopMerchantSummaryItem(AgentDTO):
    name: str
    amount: Money
    count: int
    public_id: str | None = None


class FinancialSummary(AgentDTO):
    """High-level monthly financial overview grounded in canonical spending truth."""

    period: str
    currency: str
    total_spent: Money
    consumer_spent: Money
    commitments_spent: Money
    income: Money
    net_cash_flow: Money
    previous_month_spent: Money
    spent_change_pct: float | None
    transaction_count: int
    top_categories: list[CategorySummaryItem]
    top_merchants: list[TopMerchantSummaryItem]


class CategorySpendingItem(AgentDTO):
    category: str
    total: Money
    previous_total: Money
    change_pct: float | None
    transaction_count: int
    share_pct: float


class SubcategorySpendingItem(AgentDTO):
    subcategory: str
    total: Money
    transaction_count: int
    mom_change_pct: float | None = None


class CategoryInsightItem(AgentDTO):
    type: str
    title: str
    message: str
    severity: str


class CategoryDeepDive(AgentDTO):
    """Deep-dive analytics for a single category."""

    category: str
    period_range: str
    total_spent: Money
    previous_period_spent: Money
    period_change_pct: float | None
    current_month_spent: Money
    previous_month_spent: Money
    current_month_mom_change_pct: float | None
    avg_ticket: Money
    median_ticket: Money
    share_of_living_pct: float
    subcategories: list[SubcategorySpendingItem]
    top_merchants: list[TopMerchantSummaryItem]
    insights: list[CategoryInsightItem]


class CategorySpendingResponse(AgentDTO):
    """Summary of spending across all categories."""

    period: str
    range: str
    categories: list[CategorySpendingItem]
    total_qualifying_spent: Money


class TransactionItem(AgentDTO):
    """Sanitized, allowlist-only transaction DTO."""

    public_id: str
    date: str
    amount: Money
    merchant: str
    category: str | None = None
    subcategory: str | None = None
    account_masked: str | None = None
    payment_method: str | None = None
    description: str | None = None


RecentTransactionItem = TransactionItem


class MerchantHistory(AgentDTO):
    """Historical spending and recent purchases for a specific merchant."""

    public_id: str
    merchant_name: str
    total_spent: Money
    transaction_count: int
    average_ticket: Money
    first_seen: str | None = None
    last_seen: str | None = None
    recent_transactions: list[TransactionItem]


class RecurringExpenseItem(AgentDTO):
    service_name: str
    amount: Money
    billing_frequency: str
    next_expected_date: str | None = None
    annual_cost: Money
    status: str


class RecurringExpensesResponse(AgentDTO):
    """Active subscriptions and scheduled recurring bills."""

    subscriptions: list[RecurringExpenseItem]
    bills: list[RecurringExpenseItem]
    total_monthly_burn: Money
    total_annual_cost: Money


class SalaryAttributionItem(AgentDTO):
    calendar_month: str
    pay_period_month: str
    amount: Money
    received_date: str
    attribution_note: str


class IncomeSummaryItem(AgentDTO):
    month: str
    salary_income: Money
    other_income: Money
    total_income: Money


class IncomeResponse(AgentDTO):
    """Income and salary attribution over recent months."""

    months_count: int
    monthly_totals: list[IncomeSummaryItem]
    recent_salary_credits: list[SalaryAttributionItem]


class CashFlowTrendItem(AgentDTO):
    month: str
    label: str
    spent: Money
    income: Money
    net_cash_flow: Money


class CashFlowResponse(AgentDTO):
    currency: str
    points: list[CashFlowTrendItem]


class SubcategoryTaxonomyItem(AgentDTO):
    name: str
    slug: str


class CategoryTaxonomyItem(AgentDTO):
    name: str
    slug: str
    subcategories: list[SubcategoryTaxonomyItem]


class BudgetTaxonomyResponse(AgentDTO):
    """Authoritative category taxonomy configured in MyMonee."""

    categories: list[CategoryTaxonomyItem]


class AgentCapabilitiesResponse(AgentDTO):
    """Contract metadata and supported capabilities list."""

    agent_api_version: str
    application_version: str
    currency: str
    capabilities: list[str]


class UnclassifiedTransactionItem(AgentDTO):
    """A transaction pending user or agent category review."""

    public_id: str = Field(description="Opaque transaction identifier for classification")
    date: str = Field(description="ISO date YYYY-MM-DD")
    amount: Money = Field(description="Transaction amount and currency")
    merchant: str = Field(description="Cleaned merchant or counterparty name")
    description: str | None = Field(default=None, description="Transaction note or raw description")
    payment_method: str | None = Field(
        default=None, description="Payment channel e.g. UPI, card, netbanking"
    )
    account_masked: str | None = Field(
        default=None, description="Masked account or card identifier"
    )
    direction: str = Field(description="'debit' or 'credit'")
    suggested_category: str | None = Field(
        default=None, description="Current tentative category suggestion if any"
    )


class UnclassifiedSpendsResult(AgentDTO):
    """Response containing unclassified transactions requiring category review."""

    total_count: int = Field(description="Total count of transactions pending review")
    items: list[UnclassifiedTransactionItem] = Field(
        description="List of unclassified transactions"
    )
    has_more: bool = Field(description="True if more unclassified items exist beyond this page")
    next_cursor: str | None = Field(
        default=None, description="Opaque pagination cursor for next batch"
    )


class ClassifyTransactionResult(AgentDTO):
    """Outcome of a classify transaction operation."""

    public_id: str = Field(description="Opaque transaction identifier that was classified")
    status: str = Field(default="classified", description="Outcome status")
    category: str = Field(description="Assigned category name")
    category_slug: str = Field(description="Assigned category slug")
    subcategory: str | None = Field(default=None, description="Assigned subcategory name")
    subcategory_slug: str | None = Field(default=None, description="Assigned subcategory slug")
    rule_created: bool = Field(
        description="Whether a persistent merchant classification rule was created"
    )
    backfilled_count: int = Field(
        default=0, description="Count of past unreviewed transactions from same merchant backfilled"
    )
    message: str = Field(description="Human-readable summary of the action")
