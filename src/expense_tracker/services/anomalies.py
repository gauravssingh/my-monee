"""Spending anomaly and price-surge detection engine."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from expense_tracker.db.models import (
    RecurringTransaction,
    Transaction,
    utcnow,
)

logger = logging.getLogger(__name__)


@dataclass
class AnomalyAlert:
    id: str
    anomaly_type: str  # "SUBSCRIPTION_HIKE", "SPENDING_SPIKE", "DUPLICATE_CHARGE_SAME_DAY"
    severity: str  # "high", "medium", "low"
    title: str
    description: str
    amount: float
    currency: str
    transaction_id: str | None
    date: str
    merchant: str | None
    category: str | None
    metadata: dict[str, Any]


def detect_spending_anomalies(
    session: Session,
    lookback_days: int = 60,
) -> list[AnomalyAlert]:
    """Scan recent transactions for spending spikes, subscription price hikes, and duplicate charges."""
    alerts: list[AnomalyAlert] = []
    since_date = utcnow() - timedelta(days=lookback_days)

    recent_txs = session.scalars(
        select(Transaction)
        .where(
            Transaction.transaction_date >= since_date,
            Transaction.direction == "debit",
            Transaction.excludes_from_spending.is_(False),
            Transaction.is_transfer.is_(False),
        )
        .order_by(Transaction.transaction_date.desc())
    ).all()

    # 1. Detect Subscription & Recurring Price Hikes
    recurring_items = session.scalars(select(RecurringTransaction)).all()
    for rec in recurring_items:
        if not rec.expected_amount or rec.expected_amount <= 0:
            continue

        import re
        rec_tokens = set(re.findall(r"\w+", rec.name.lower())) - {"subscription", "bill", "plan", "monthly", "autopay"}
        matched_txs = []
        for t in recent_txs:
            t_text = f"{t.merchant_normalized or ''} {t.merchant_raw or ''} {t.description or ''}".lower()
            t_tokens = set(re.findall(r"\w+", t_text))
            if rec_tokens and rec_tokens.intersection(t_tokens):
                matched_txs.append(t)

        for t in matched_txs:
            actual_amt = float(t.amount)
            expected_amt = float(rec.expected_amount)
            diff = actual_amt - expected_amt
            pct_increase = (diff / expected_amt) * 100

            # Flag if price increased by > 5% and at least ₹50
            if pct_increase >= 5.0 and diff >= 50.0:
                alerts.append(
                    AnomalyAlert(
                        id=f"hike_{t.id}",
                        anomaly_type="SUBSCRIPTION_HIKE",
                        severity="medium" if diff < 500 else "high",
                        title=f"Price Surge on {rec.name}",
                        description=f"Billed ₹{actual_amt:,.2f} vs expected baseline ₹{expected_amt:,.2f} (+{pct_increase:.1f}% increase)",
                        amount=actual_amt,
                        currency=t.currency,
                        transaction_id=t.id,
                        date=t.transaction_date.isoformat(),
                        merchant=t.merchant_normalized or t.merchant_raw,
                        category=t.category.name if t.category else None,
                        metadata={
                            "recurring_name": rec.name,
                            "expected_amount": expected_amt,
                            "actual_amount": actual_amt,
                            "percentage_increase": round(pct_increase, 1),
                        },
                    )
                )

    # 2. Detect Same-Day Multiple Charges to Same Merchant
    merchant_day_map: dict[tuple[str, str, float], list[Transaction]] = {}
    for t in recent_txs:
        if not t.merchant_raw and not t.merchant_normalized:
            continue
        m_key = (t.merchant_normalized or t.merchant_raw or "").lower().strip()
        day_key = t.transaction_date.strftime("%Y-%m-%d")
        amt_key = round(float(t.amount), 2)
        key = (m_key, day_key, amt_key)
        merchant_day_map.setdefault(key, []).append(t)

    for (m_key, day_key, amt_key), same_txs in merchant_day_map.items():
        if len(same_txs) > 1 and amt_key >= 100:  # Same amount twice on the same day
            for tx in same_txs[1:]:
                alerts.append(
                    AnomalyAlert(
                        id=f"dupcharge_{tx.id}",
                        anomaly_type="DUPLICATE_CHARGE_SAME_DAY",
                        severity="high",
                        title=f"Repeated Same-Day Charge: {tx.merchant_normalized or tx.merchant_raw}",
                        description=f"Charged ₹{amt_key:,.2f} multiple times ({len(same_txs)}x) on {day_key}",
                        amount=amt_key,
                        currency=tx.currency,
                        transaction_id=tx.id,
                        date=tx.transaction_date.isoformat(),
                        merchant=tx.merchant_normalized or tx.merchant_raw,
                        category=tx.category.name if tx.category else None,
                        metadata={
                            "charge_count": len(same_txs),
                            "merchant": m_key,
                            "date": day_key,
                        },
                    )
                )

    # 3. Detect Outlier Spikes (> 3x 90-day category average for discretionary spending)
    category_totals = (
        session.query(
            Transaction.category_id,
            func.avg(Transaction.amount).label("avg_amt"),
            func.count(Transaction.id).label("tx_count"),
        )
        .filter(
            Transaction.direction == "debit",
            Transaction.excludes_from_spending.is_(False),
            Transaction.transaction_date >= utcnow() - timedelta(days=90),
        )
        .group_by(Transaction.category_id)
        .all()
    )

    avg_by_cat = {
        row[0]: float(row[1]) for row in category_totals if row[0] and row[2] >= 5
    }

    for t in recent_txs:
        if t.category_id and t.category_id in avg_by_cat:
            cat_avg = avg_by_cat[t.category_id]
            amt = float(t.amount)
            # If transaction is > 4x average and > ₹5,000
            if amt >= 4 * cat_avg and amt >= 5000:
                cat_name = t.category.name if t.category else "Uncategorized"
                alerts.append(
                    AnomalyAlert(
                        id=f"spike_{t.id}",
                        anomaly_type="SPENDING_SPIKE",
                        severity="medium" if amt < 25000 else "high",
                        title=f"Unusual Spending Spike in {cat_name}",
                        description=f"₹{amt:,.2f} is {round(amt / cat_avg, 1)}x higher than your average {cat_name} expense (₹{cat_avg:,.2f})",
                        amount=amt,
                        currency=t.currency,
                        transaction_id=t.id,
                        date=t.transaction_date.isoformat(),
                        merchant=t.merchant_normalized or t.merchant_raw,
                        category=cat_name,
                        metadata={
                            "category_avg": round(cat_avg, 2),
                            "multiplier": round(amt / cat_avg, 1),
                        },
                    )
                )

    # Sort alerts by date descending
    return sorted(alerts, key=lambda a: a.date, reverse=True)
