#!/usr/bin/env python3
"""Merge duplicate recurring subscriptions (e.g. ACT Internet and ACT Broadband)."""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from sqlalchemy import select, delete
from mymonee.config import load_settings
from mymonee.db.session import get_session_factory
from mymonee.db.models import (
    Subscription,
    RecurringTransaction,
    TransactionRecurringLink,
    Transaction,
    Merchant,
    utcnow,
)


def merge_act_subscriptions():
    load_settings()
    SessionFactory = get_session_factory()

    with SessionFactory() as session:
        target_sub = session.scalars(
            select(Subscription).where(Subscription.name.ilike("%act broadband%"))
        ).first()
        source_sub = session.scalars(
            select(Subscription).where(Subscription.name.ilike("%act internet%"))
        ).first()

        if not target_sub and not source_sub:
            print("No ACT subscriptions found to merge.")
            return

        if not target_sub and source_sub:
            print("Only ACT Internet found; renaming to ACT Broadband.")
            source_sub.name = "ACT Broadband"
            target_rt = session.get(RecurringTransaction, source_sub.recurring_transaction_id)
            if target_rt:
                target_rt.name = "ACT Broadband"
            session.commit()
            print("Renamed successfully.")
            return

        if not source_sub and target_sub:
            print("Only ACT Broadband exists. Already merged or single entry.")
            return

        print(f"Merging '{source_sub.name}' (ID: {source_sub.id}) into '{target_sub.name}' (ID: {target_sub.id})...")

        target_rt = session.get(RecurringTransaction, target_sub.recurring_transaction_id)
        source_rt_id = source_sub.recurring_transaction_id

        # 1. Explicitly delete all links and subscriptions pointing to source_rt_id
        session.execute(
            delete(TransactionRecurringLink).where(
                TransactionRecurringLink.recurring_transaction_id == source_rt_id
            )
        )
        session.execute(
            delete(Subscription).where(
                Subscription.recurring_transaction_id == source_rt_id
            )
        )
        session.execute(
            delete(RecurringTransaction).where(
                RecurringTransaction.id == source_rt_id
            )
        )
        session.flush()

        # 2. Get existing target linked transaction IDs
        existing_target_links = {
            link.transaction_id
            for link in session.scalars(
                select(TransactionRecurringLink).where(
                    TransactionRecurringLink.recurring_transaction_id == target_rt.id
                )
            ).all()
        }

        # 3. Find all ACT / Broadband transactions of amount ~2948.82
        act_txs = session.scalars(
            select(Transaction).where(
                Transaction.amount >= 2948.0,
                Transaction.amount <= 2949.0,
            )
        ).all()

        auto_linked = 0
        for tx in act_txs:
            if tx.id not in existing_target_links:
                session.add(
                    TransactionRecurringLink(
                        transaction_id=tx.id,
                        recurring_transaction_id=target_rt.id,
                        match_type="auto",
                        confidence=1.0,
                    )
                )
                existing_target_links.add(tx.id)
                auto_linked += 1

        # 4. Update target subscription and RT fields
        target_sub.name = "ACT Broadband"
        target_sub.amount = 2948.82
        target_sub.annual_cost = 2948.82 * 12
        target_sub.status = "active"
        target_sub.updated_at = utcnow()

        target_rt.name = "ACT Broadband"
        target_rt.expected_amount = 2948.82
        target_rt.frequency = "monthly"
        target_rt.status = "active"
        target_rt.updated_at = utcnow()

        # Link merchant if available
        act_merchant = session.scalars(
            select(Merchant).where(Merchant.display_name.ilike("%act broadband%"))
        ).first()
        if act_merchant:
            target_rt.merchant_id = act_merchant.id

        session.commit()
        print(f"✅ Successfully merged ACT Internet into ACT Broadband!")
        print(f"  • Auto-linked {auto_linked} broadband transactions")
        print(f"  • Target RT ID: {target_rt.id}")


if __name__ == "__main__":
    merge_act_subscriptions()
