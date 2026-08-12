"""Dashboard and overview aggregations."""

from __future__ import annotations

from calendar import monthrange
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

IST = ZoneInfo("Asia/Kolkata")

from expense_tracker.db.models import Category, Email, IngestionRun, SyncState, Transaction


def _month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    start = datetime(year, month, 1, tzinfo=IST)
    last_day = monthrange(year, month)[1]
    end = datetime(year, month, last_day, 23, 59, 59, 999999, tzinfo=IST)
    return start, end


def _prev_month(year: int, month: int) -> tuple[int, int]:
    if month == 1:
        return year - 1, 12
    return year, month - 1


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    absolute = year * 12 + (month - 1) + delta
    return absolute // 12, absolute % 12 + 1


def _as_float(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _pct_change(current: float, previous: float) -> float | None:
    if previous <= 0 or current <= 0:
        return None
    return round(((current - previous) / previous) * 100.0, 1)


def _spending_query(start: datetime, end: datetime) -> Select[Any]:
    return (
        select(func.coalesce(func.sum(Transaction.amount), 0))
        .where(Transaction.transaction_date >= start)
        .where(Transaction.transaction_date <= end)
        .where(Transaction.direction == "debit")
        .where(Transaction.is_duplicate.is_(False))
        .where(Transaction.excludes_from_spending.is_(False))
    )


def salary_pay_period(when: datetime) -> tuple[int, int]:
    """
    Map a salary credit date to the month it pays for.

    Income is salary only. Typical credit near month-end pays the *next* month.
    Delayed credits on the 1st–2nd pay the *current* month.
    """
    if when.tzinfo:
        when = when.astimezone(IST)
    if when.day <= 2:
        return when.year, when.month
    return _shift_month(when.year, when.month, 1)


def _income_candidates_around(session: Session, year: int, month: int) -> list[Transaction]:
    """Salary rows that could belong to this pay period (prev + current calendar months)."""
    prev_y, prev_m = _shift_month(year, month, -1)
    start, _ = _month_bounds(prev_y, prev_m)
    _, end = _month_bounds(year, month)
    return list(
        session.scalars(
            select(Transaction)
            .where(Transaction.transaction_date >= start)
            .where(Transaction.transaction_date <= end)
            .where(Transaction.is_duplicate.is_(False))
            .where(Transaction.transaction_type == "income")
        ).all()
    )


def income_for_pay_period(session: Session, year: int, month: int) -> float:
    total = 0.0
    for tx in _income_candidates_around(session, year, month):
        if tx.transaction_date is None:
            continue
        
        is_salary = tx.subcategory and tx.subcategory.slug == "salary"
        if is_salary:
            py, pm = salary_pay_period(tx.transaction_date)
        else:
            # Non-salary income (like interest) belongs to its actual calendar month
            dt = tx.transaction_date.astimezone(IST) if tx.transaction_date.tzinfo else tx.transaction_date
            py, pm = dt.year, dt.month

        if py == year and pm == month:
            total += _as_float(tx.amount)
    return total


def get_overview(session: Session, *, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(IST)
    start, end = _month_bounds(now.year, now.month)
    py, pm = _prev_month(now.year, now.month)
    prev_start, prev_end = _month_bounds(py, pm)

    current_spend = _as_float(session.scalar(_spending_query(start, end)))
    previous_spend = _as_float(session.scalar(_spending_query(prev_start, prev_end)))
    income = income_for_pay_period(session, now.year, now.month)
    previous_income = income_for_pay_period(session, py, pm)

    tx_count = session.scalar(
        select(func.count())
        .select_from(Transaction)
        .where(Transaction.transaction_date >= start)
        .where(Transaction.transaction_date <= end)
        .where(Transaction.is_duplicate.is_(False))
    ) or 0

    largest = session.execute(
        select(Transaction)
        .where(Transaction.transaction_date >= start)
        .where(Transaction.transaction_date <= end)
        .where(Transaction.direction == "debit")
        .where(Transaction.is_duplicate.is_(False))
        .where(Transaction.excludes_from_spending.is_(False))
        .order_by(Transaction.amount.desc())
        .limit(1)
    ).scalar_one_or_none()

    needs_review = session.scalar(
        select(func.count()).select_from(Transaction).where(Transaction.needs_review.is_(True))
    ) or 0

    return {
        "period": {"year": now.year, "month": now.month},
        "current_month_spending": current_spend,
        "previous_month_spending": previous_spend,
        "income": income,
        "previous_month_income": previous_income,
        "income_change_pct": _pct_change(income, previous_income),
        "net_cash_flow": income - current_spend,
        "transaction_count": int(tx_count),
        "largest_transaction": (
            {
                "id": largest.id,
                "amount": _as_float(largest.amount),
                "merchant": largest.merchant_normalized or largest.merchant_raw,
                "date": largest.transaction_date.isoformat(),
            }
            if largest
            else None
        ),
        "needs_review_count": int(needs_review),
        "currency": "INR",
    }


def income_trend(
    session: Session,
    *,
    months: int = 6,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(IST)
    months = max(1, min(int(months), 24))
    points: list[dict[str, Any]] = []
    for offset in range(-(months - 1), 1):
        year, month = _shift_month(now.year, now.month, offset)
        total = income_for_pay_period(session, year, month)
        points.append(
            {
                "year": year,
                "month": month,
                "label": datetime(year, month, 1).strftime("%b %Y"),
                "income": total,
            }
        )
    return {"months": months, "currency": "INR", "points": points}


def spending_by_category(session: Session, *, year: int | None = None, month: int | None = None, now: datetime | None = None) -> list[dict[str, Any]]:
    if year and month:
        start, end = _month_bounds(year, month)
    else:
        now = now or datetime.now(IST)
        start, end = _month_bounds(now.year, now.month)

    categories = session.execute(
        select(Category).order_by(Category.sort_order)
    ).scalars().all()

    totals = dict(
        session.execute(
            select(Transaction.category_id, func.coalesce(func.sum(Transaction.amount), 0))
            .where(Transaction.transaction_date >= start)
            .where(Transaction.transaction_date <= end)
            .where(Transaction.direction == "debit")
            .where(Transaction.is_duplicate.is_(False))
            .where(Transaction.excludes_from_spending.is_(False))
            .where(Transaction.category_id.is_not(None))
            .group_by(Transaction.category_id)
        ).all()
    )
    counts = dict(
        session.execute(
            select(Transaction.category_id, func.count(Transaction.id))
            .where(Transaction.transaction_date >= start)
            .where(Transaction.transaction_date <= end)
            .where(Transaction.direction == "debit")
            .where(Transaction.is_duplicate.is_(False))
            .where(Transaction.excludes_from_spending.is_(False))
            .where(Transaction.category_id.is_not(None))
            .group_by(Transaction.category_id)
        ).all()
    )

    return [
        {
            "category_id": cat.id,
            "category": cat.name,
            "total": _as_float(totals.get(cat.id, 0)),
            "count": int(counts.get(cat.id, 0)),
        }
        for cat in categories
    ]


def get_system_status(session: Session, settings_summary: dict[str, Any]) -> dict[str, Any]:
    last_sync = session.get(SyncState, "gmail.last_sync_at")
    last_run = session.scalar(
        select(IngestionRun).order_by(IngestionRun.started_at.desc()).limit(1)
    )
    total_tx = session.scalar(select(func.count()).select_from(Transaction)) or 0
    total_email = session.scalar(select(func.count()).select_from(Email)) or 0

    return {
        "app": settings_summary,
        "database": {
            "transaction_count": int(total_tx),
            "email_count": int(total_email),
        },
        "gmail": {
            "last_sync_at": last_sync.value if last_sync else None,
            "connected": False,  # Phase 2
        },
        "last_ingestion_run": (
            {
                "id": last_run.id,
                "status": last_run.status,
                "started_at": last_run.started_at.isoformat(),
                "finished_at": last_run.finished_at.isoformat() if last_run.finished_at else None,
                "emails_discovered": last_run.emails_discovered,
                "emails_processed": last_run.emails_processed,
                "transactions_extracted": last_run.transactions_extracted,
                "parsing_errors": last_run.parsing_errors,
            }
            if last_run
            else None
        ),
    }
