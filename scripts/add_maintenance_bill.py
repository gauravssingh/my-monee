#!/usr/bin/env python3
"""Add Monthly House Maintenance Bill (NoBrokerHood) to Recurring Bills."""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from sqlalchemy import select
from expense_tracker.config import load_settings
from expense_tracker.db.session import get_session_factory
from expense_tracker.db.models import (
    Bill,
    RecurringTransaction,
    TransactionRecurringLink,
    Transaction,
    Merchant,
    Category,
    utcnow,
)


def add_maintenance_bill():
    load_settings()
    SessionFactory = get_session_factory()

    with SessionFactory() as session:
        # Check if already exists
        existing = session.scalars(
            select(Bill).where(Bill.name.ilike("%maintenance%"))
        ).first()

        if existing:
            print(f"Bill already exists: {existing.name} (ID: {existing.id})")
            return

        # Find NoBrokerHood merchant
        merchant = session.scalars(
            select(Merchant).where(Merchant.display_name.ilike("%nobrokerhood%"))
        ).first()

        # Find Home category
        home_cat = session.scalars(
            select(Category).where(Category.name.ilike("%home%"))
        ).first()

        # Find all NoBrokerHood maintenance transactions (amounts between 6800 and 7300)
        maint_txs = session.scalars(
            select(Transaction).where(
                (Transaction.amount >= 6800.0) & (Transaction.amount <= 7300.0),
                (
                    (Transaction.merchant_normalized.ilike("%nobroker%"))
                    | (Transaction.merchant_raw.ilike("%nobroker%"))
                    | (Transaction.description.ilike("%maintenance%"))
                ),
            ).order_by(Transaction.transaction_date.desc())
        ).all()

        print(f"Found {len(maint_txs)} historical maintenance transactions.")
        amounts = [float(tx.amount) for tx in maint_txs]
        avg_amount = sum(amounts) / len(amounts) if amounts else 6858.0
        min_amount = min(amounts) if amounts else 6858.0
        max_amount = max(amounts) if amounts else 7201.0
        latest_tx = maint_txs[0] if maint_txs else None

        rt_id = str(uuid.uuid4())
        bill_id = str(uuid.uuid4())

        # Next expected date: 1st of next month (Sept 1, 2026)
        next_date = datetime(2026, 9, 1, 0, 0, 0, tzinfo=timezone.utc)

        rt = RecurringTransaction(
            id=rt_id,
            name="House Maintenance (NoBrokerHood)",
            expected_amount=round(avg_amount, 2),
            frequency="monthly",
            interval_days=30,
            expected_day=1,
            date_tolerance_days=5,
            merchant_id=merchant.id if merchant else None,
            category_id=home_cat.id if home_cat else None,
            status="active",
            confidence=1.0,
            next_expected_date=next_date,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        session.add(rt)
        session.flush()

        bill = Bill(
            id=bill_id,
            recurring_transaction_id=rt.id,
            name="House Maintenance (NoBrokerHood)",
            bill_type="UTILITY",
            autopay=False,
            minimum_amount=round(min_amount, 2),
            max_amount=round(max_amount, 2),
            average_amount=round(avg_amount, 2),
            last_paid_date=latest_tx.transaction_date if latest_tx else None,
            last_paid_amount=float(latest_tx.amount) if latest_tx else round(avg_amount, 2),
            next_expected_amount=6858.00,
            status="active",
        )
        session.add(bill)
        session.flush()

        # Link all maintenance transactions
        linked_count = 0
        for tx in maint_txs:
            session.add(
                TransactionRecurringLink(
                    transaction_id=tx.id,
                    recurring_transaction_id=rt.id,
                    match_type="auto",
                    confidence=1.0,
                )
            )
            linked_count += 1

        session.commit()

        print("✅ Successfully created House Maintenance Bill!")
        print(f"  • Bill Name: {bill.name}")
        print(f"  • Expected / Avg Amount: ₹{round(avg_amount, 2):,} (Recent bill: ₹6,858)")
        print(f"  • Frequency: Monthly on the 1st")
        print(f"  • Category: {home_cat.name if home_cat else 'None'}")
        print(f"  • Merchant: {merchant.display_name if merchant else 'None'}")
        print(f"  • Linked Historical Transactions: {linked_count}")


if __name__ == "__main__":
    add_maintenance_bill()
