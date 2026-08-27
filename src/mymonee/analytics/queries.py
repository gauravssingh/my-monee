"""Reusable database SQL aggregation queries for the analytics engine."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from mymonee.analytics.common import as_float, spending_transaction_filter
from mymonee.db.models import Category, Merchant, Subcategory, Transaction


def query_total_living_spend(
    session: Session,
    start: datetime,
    end: datetime,
) -> float:
    """Return total qualifying consumer spend across all non-excluded categories in the date range."""
    stmt = (
        select(func.coalesce(func.sum(Transaction.amount), 0))
        .where(
            Transaction.transaction_date >= start,
            Transaction.transaction_date <= end,
            *spending_transaction_filter(),
        )
    )
    return as_float(session.scalar(stmt))


def query_category_spend_and_count(
    session: Session,
    category_id: str,
    start: datetime,
    end: datetime,
) -> tuple[float, int]:
    """Return (total_spend, transaction_count) for a specific category within the date range."""
    stmt = (
        select(
            func.coalesce(func.sum(Transaction.amount), 0),
            func.count(Transaction.id),
        )
        .where(
            Transaction.category_id == category_id,
            Transaction.transaction_date >= start,
            Transaction.transaction_date <= end,
            *spending_transaction_filter(),
        )
    )
    row = session.execute(stmt).one()
    return as_float(row[0]), int(row[1] or 0)


def query_category_transaction_amounts(
    session: Session,
    category_id: str,
    start: datetime,
    end: datetime,
) -> list[float]:
    """Return list of individual qualifying transaction amounts for median ticket calculation."""
    stmt = (
        select(Transaction.amount)
        .where(
            Transaction.category_id == category_id,
            Transaction.transaction_date >= start,
            Transaction.transaction_date <= end,
            *spending_transaction_filter(),
        )
        .order_by(Transaction.amount.asc())
    )
    return [as_float(val) for val in session.scalars(stmt).all()]


def query_subcategory_monthly_series(
    session: Session,
    category_id: str,
    start: datetime,
    end: datetime,
) -> list[dict[str, Any]]:
    """Return monthly bucketed spend and transaction count by subcategory."""
    # SQLite strftime('%Y-%m', transaction_date)
    month_expr = func.strftime("%Y-%m", Transaction.transaction_date)

    stmt = (
        select(
            month_expr.label("month_str"),
            Transaction.subcategory_id,
            func.coalesce(func.sum(Transaction.amount), 0).label("spend"),
            func.count(Transaction.id).label("tx_count"),
        )
        .where(
            Transaction.category_id == category_id,
            Transaction.transaction_date >= start,
            Transaction.transaction_date <= end,
            *spending_transaction_filter(),
        )
        .group_by(month_expr, Transaction.subcategory_id)
        .order_by(month_expr.asc())
    )

    results = []
    for row in session.execute(stmt).all():
        results.append(
            {
                "month_str": str(row.month_str),
                "subcategory_id": row.subcategory_id,
                "spend": as_float(row.spend),
                "tx_count": int(row.tx_count or 0),
            }
        )
    return results


def query_subcategory_period_totals(
    session: Session,
    category_id: str,
    start: datetime,
    end: datetime,
) -> list[dict[str, Any]]:
    """Return period aggregate metrics for each subcategory."""
    stmt = (
        select(
            Transaction.subcategory_id,
            func.coalesce(func.sum(Transaction.amount), 0).label("spend"),
            func.count(Transaction.id).label("tx_count"),
        )
        .where(
            Transaction.category_id == category_id,
            Transaction.transaction_date >= start,
            Transaction.transaction_date <= end,
            *spending_transaction_filter(),
        )
        .group_by(Transaction.subcategory_id)
    )

    results = []
    for row in session.execute(stmt).all():
        results.append(
            {
                "subcategory_id": row.subcategory_id,
                "spend": as_float(row.spend),
                "tx_count": int(row.tx_count or 0),
            }
        )
    return results


def query_category_merchants(
    session: Session,
    category_id: str,
    start: datetime,
    end: datetime,
    limit: int = 15,
) -> list[dict[str, Any]]:
    """Return top merchants for the category aggregating by canonical merchant identity."""
    # Preferred merchant name: Merchant.display_name > Transaction.merchant_normalized > Transaction.merchant_raw
    canonical_name = case(
        (Merchant.display_name.is_not(None), Merchant.display_name),
        (Transaction.merchant_normalized.is_not(None), Transaction.merchant_normalized),
        else_=func.coalesce(Transaction.merchant_raw, "Unknown Merchant"),
    ).label("merchant_name")

    stmt = (
        select(
            Transaction.merchant_entity_id,
            canonical_name,
            func.coalesce(func.sum(Transaction.amount), 0).label("spend"),
            func.count(Transaction.id).label("tx_count"),
        )
        .outerjoin(Merchant, Transaction.merchant_entity_id == Merchant.id)
        .where(
            Transaction.category_id == category_id,
            Transaction.transaction_date >= start,
            Transaction.transaction_date <= end,
            *spending_transaction_filter(),
        )
        .group_by(canonical_name)
        .order_by(func.sum(Transaction.amount).desc())
        .limit(limit)
    )

    merchants = []
    for row in session.execute(stmt).all():
        merchants.append(
            {
                "merchant_id": row.merchant_entity_id,
                "name": str(row.merchant_name).strip() if row.merchant_name else "Unknown Merchant",
                "spend": as_float(row.spend),
                "tx_count": int(row.tx_count or 0),
            }
        )
    return merchants
