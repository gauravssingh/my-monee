"""Common analytics predicates, date calculations, and statistical helpers."""

from __future__ import annotations

from calendar import monthrange
from datetime import datetime
from decimal import Decimal
import statistics
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.sql.elements import BinaryExpression

from mymonee.db.models import Category, DataIssueFlag, Subcategory, Transaction
from mymonee.domain.enums import DataIssueStatus

IST = ZoneInfo("Asia/Kolkata")


def spending_transaction_filter() -> list[Any]:
    """Canonical single-source-of-truth filter predicate for consumer spending transactions.

    Excludes:
    - Credits / refunds / inflows (direction != 'debit')
    - Duplicates (is_duplicate == True)
    - Account-to-account transfers (is_transfer == True or category 'transfers')
    - Credit card payments (subcategory 'credit-card-payment' or transaction_type 'credit_card_payment')
    - Excluded transactions (excludes_from_spending == True)
    - Non-spending ledger events (not_a_transaction, declined, statement)
    - Transactions with open blocking data issues (duplicate, not_a_transaction)
    """
    open_issue_subq = select(DataIssueFlag.transaction_id).where(
        DataIssueFlag.status == DataIssueStatus.OPEN,
        DataIssueFlag.issue_type.in_(["not_a_transaction", "duplicate"]),
    )
    transfers_cat_subq = select(Category.id).where(Category.slug == "transfers")
    cc_subcat_subq = select(Subcategory.id).where(Subcategory.slug == "credit-card-payment")

    return [
        Transaction.direction == "debit",
        Transaction.is_duplicate.is_(False),
        Transaction.is_transfer.is_(False),
        Transaction.excludes_from_spending.is_(False),
        Transaction.transaction_type.notin_(
            [
                "not_a_transaction",
                "declined",
                "transfer",
                "credit_card_payment",
                "cc_payment",
                "statement",
            ]
        ),
        (Transaction.category_id.is_(None) | ~Transaction.category_id.in_(transfers_cat_subq)),
        (Transaction.subcategory_id.is_(None) | ~Transaction.subcategory_id.in_(cc_subcat_subq)),
        ~Transaction.id.in_(open_issue_subq),
    ]


def month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    """Return timezone-aware start and end datetime for a specific calendar month."""
    start = datetime(year, month, 1, tzinfo=IST)
    last_day = monthrange(year, month)[1]
    end = datetime(year, month, last_day, 23, 59, 59, 999999, tzinfo=IST)
    return start, end


def shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    """Shift calendar year/month by delta months (positive or negative)."""
    absolute = year * 12 + (month - 1) + delta
    return absolute // 12, absolute % 12 + 1


def resolve_period(
    range_str: str = "6m",
    year: int | None = None,
    month: int | None = None,
) -> dict[str, Any]:
    """Resolve range semantics and compute precise date boundaries for active and comparison periods.

    Supported ranges:
    - '1m': Active single month
    - '3m': Last 3 calendar months ending at (year, month)
    - '6m': Last 6 calendar months ending at (year, month)
    - '12m': Last 12 calendar months ending at (year, month)
    - 'ytd': From January 1st of year to end of (year, month)
    """
    now = datetime.now(IST)
    end_year = year if year is not None else now.year
    end_month = month if month is not None else now.month

    range_clean = (range_str or "6m").strip().lower()

    if range_clean == "1m":
        num_months = 1
        start_year, start_month = end_year, end_month
    elif range_clean == "3m":
        num_months = 3
        start_year, start_month = shift_month(end_year, end_month, -2)
    elif range_clean == "12m":
        num_months = 12
        start_year, start_month = shift_month(end_year, end_month, -11)
    elif range_clean == "ytd":
        num_months = end_month
        start_year, start_month = end_year, 1
    else:  # default '6m'
        range_clean = "6m"
        num_months = 6
        start_year, start_month = shift_month(end_year, end_month, -5)

    start_dt, _ = month_bounds(start_year, start_month)
    _, end_dt = month_bounds(end_year, end_month)

    # Calculate comparison period (equivalent length preceding the start date)
    comp_end_year, comp_end_month = shift_month(start_year, start_month, -1)
    comp_start_year, comp_start_month = shift_month(comp_end_year, comp_end_month, -(num_months - 1))

    comp_start_dt, _ = month_bounds(comp_start_year, comp_start_month)
    _, comp_end_dt = month_bounds(comp_end_year, comp_end_month)

    # Current single month bounds
    cur_month_start, cur_month_end = month_bounds(end_year, end_month)
    prev_m_year, prev_m_month = shift_month(end_year, end_month, -1)
    prev_month_start, prev_month_end = month_bounds(prev_m_year, prev_m_month)

    # Generate ordered list of month buckets: [(year, month), ...]
    month_buckets: list[tuple[int, int]] = []
    curr_y, curr_m = start_year, start_month
    for _ in range(num_months):
        month_buckets.append((curr_y, curr_m))
        curr_y, curr_m = shift_month(curr_y, curr_m, 1)

    return {
        "range": range_clean,
        "year": end_year,
        "month": end_month,
        "months_count": num_months,
        "start": start_dt,
        "end": end_dt,
        "comparison_start": comp_start_dt,
        "comparison_end": comp_end_dt,
        "cur_month_start": cur_month_start,
        "cur_month_end": cur_month_end,
        "prev_month_start": prev_month_start,
        "prev_month_end": prev_month_end,
        "month_buckets": month_buckets,
    }


def as_float(value: Any) -> float:
    """Safely convert numeric/Decimal/None to float."""
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def calculate_delta_pct(current: float, previous: float) -> float | None:
    """Calculate percentage change between current and previous values."""
    if previous <= 0 or current <= 0:
        return None
    return round(((current - previous) / previous) * 100.0, 1)


def calculate_median(values: list[float]) -> float:
    """Calculate median of a numeric list, returning 0.0 if empty."""
    if not values:
        return 0.0
    return round(float(statistics.median(values)), 2)


def calculate_rolling_average(values: list[float], window: int = 3) -> float:
    """Calculate rolling average of the last `window` non-empty values."""
    if not values:
        return 0.0
    recent = values[-window:] if len(values) >= window else values
    if not recent:
        return 0.0
    return round(sum(recent) / len(recent), 2)
