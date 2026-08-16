"""Reconcile February 2026 Shubham transfers and Hotel payments.

Usage:
    python scripts/reconcile_feb_shubham_hotels.py --dry-run
    python scripts/reconcile_feb_shubham_hotels.py --apply
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parents[1]
src_dir = root_dir / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from sqlalchemy import select
from sqlalchemy.orm import Session

from expense_tracker.config import get_settings
from expense_tracker.db.models import Category, Subcategory, Transaction, new_id
from expense_tracker.db.session import init_engine
from expense_tracker.services.transactions import classify_transaction


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconcile Feb Shubham transfers and Hotel payments")
    parser.add_argument("--apply", action="store_true", help="Apply changes to database")
    parser.add_argument("--dry-run", action="store_true", help="Dry run without committing changes")
    args = parser.parse_args()

    if not args.apply and not args.dry_run:
        print("Please specify either --dry-run or --apply")
        sys.exit(1)

    settings = get_settings()
    engine = init_engine(settings)
    print(f"Connecting to database: {settings.database_path()}")

    with Session(engine) as session:
        # 1. Categories
        transfers_cat = session.scalar(select(Category).where(Category.slug == "transfers"))
        travel_cat = session.scalar(select(Category).where(Category.slug == "travel"))
        hotels_sub = session.scalar(
            select(Subcategory).where(
                Subcategory.category_id == travel_cat.id,
                Subcategory.slug == "hotels",
            )
        )

        shubham_sub = session.scalar(
            select(Subcategory).where(
                Subcategory.category_id == transfers_cat.id,
                Subcategory.slug == "shubham",
            )
        )
        if not shubham_sub:
            shubham_sub = Subcategory(
                id=new_id(),
                category_id=transfers_cat.id,
                name="Shubham",
                slug="shubham",
                sort_order=11,
            )
            session.add(shubham_sub)
            session.flush()
            print(f"Created subcategory: Transfers -> {shubham_sub.name} ({shubham_sub.id})")
        else:
            print(f"Found subcategory: Transfers -> {shubham_sub.name} ({shubham_sub.id})")

        # 2. Shubham transactions (5 on Feb 13)
        shubham_tx_ids = [
            "98f8fc3e-aa5a-41bb-a8ce-550a01da1dc8",  # Debit 10,000
            "8088d2c2-357d-4f48-8942-0e682ccea942",  # Debit 15,000
            "13295da4-5d0a-4320-abec-c707a6ccd4c0",  # Credit 5,000
            "3b8b6e61-ea4f-4124-8fa9-9f7900efb6f4",  # Credit 20,000
            "33d32a1a-c6a7-483f-bfa6-ec5f331e3a02",  # Credit 15,000
        ]
        shubham_txs = list(
            session.scalars(select(Transaction).where(Transaction.id.in_(shubham_tx_ids))).all()
        )

        # 3. Hotel payments (2 payments of 12,750)
        hotel_tx_ids = [
            "75890ca2-b5c6-4657-bf0c-d45314c5c4f5",  # Feb 05: 12,750 (Rahul Kumar Verma)
            "6d91cd2e-ab88-4915-92b1-643d6d8d4e6f",  # Feb 16: 12,750 (Anesh Gokuldas Pagi)
        ]
        hotel_txs = list(
            session.scalars(select(Transaction).where(Transaction.id.in_(hotel_tx_ids))).all()
        )

        print(f"\nFound {len(shubham_txs)} Shubham transfers to classify under Transfers -> Shubham:")
        for tx in shubham_txs:
            print(
                f"  - [{tx.id}] {tx.transaction_date} | {tx.direction.upper()} | "
                f"{tx.amount} {tx.currency}"
            )

        print(f"\nFound {len(hotel_txs)} Hotel debits to classify under Travel -> Hotels:")
        for tx in hotel_txs:
            print(
                f"  - [{tx.id}] {tx.transaction_date} | {tx.merchant_raw} | {tx.amount} {tx.currency}"
            )

        if args.dry_run:
            print("\n[DRY RUN] No changes committed. Run with --apply to commit.")
            return

        print("\nApplying updates...")
        for tx in shubham_txs:
            tx.merchant_raw = "SHUBHAM GUPTA"
            tx.merchant_normalized = "Shubham Gupta"
            classify_transaction(
                session,
                tx.id,
                category_id=transfers_cat.id,
                subcategory_id=shubham_sub.id,
            )
            tx.is_transfer = True
            tx.excludes_from_spending = True
            tx.needs_review = False
            tx.user_verified = True

        for tx in hotel_txs:
            classify_transaction(
                session,
                tx.id,
                category_id=travel_cat.id,
                subcategory_id=hotels_sub.id if hotels_sub else None,
            )
            tx.is_transfer = False
            tx.excludes_from_spending = False
            tx.needs_review = False
            tx.user_verified = True

        session.commit()
        print("Successfully reconciled Shubham transfers and Hotel payments.")


if __name__ == "__main__":
    main()
