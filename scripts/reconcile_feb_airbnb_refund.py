"""Reconcile February 2026 Airbnb purchase and matching refund (18,900 INR).

Usage:
    python scripts/reconcile_feb_airbnb_refund.py --dry-run
    python scripts/reconcile_feb_airbnb_refund.py --apply
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

from mymonee.config import get_settings
from mymonee.db.models import Category, Subcategory, Transaction
from mymonee.db.session import init_engine
from mymonee.services.transactions import classify_transaction


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconcile Feb Airbnb refund")
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
        travel_cat = session.scalar(select(Category).where(Category.slug == "travel"))
        hotels_sub = session.scalar(
            select(Subcategory).where(
                Subcategory.category_id == travel_cat.id,
                Subcategory.slug == "hotels",
            )
        )

        debit_id = "7e45e822-7e75-40af-9c6d-54dd02868d2e"
        credit_id = "11671c9f-aa42-4afe-a921-d18c615fcb89"

        debit = session.get(Transaction, debit_id)
        credit = session.get(Transaction, credit_id)

        print(f"1. Airbnb Debit: [{debit.id}] {debit.transaction_date} | {debit.merchant_raw} | {debit.amount} INR")
        print(f"2. Refund Credit: [{credit.id}] {credit.transaction_date} | {credit.merchant_raw} | {credit.amount} INR")

        if args.dry_run:
            print("\n[DRY RUN] Would pair and close both 18,900 transactions:")
            print("  - Exclude debit from spending as refunded (excludes_from_spending=True)")
            print("  - Mark credit as refund (is_refund=True, excludes_from_spending=True)")
            print("  - Classify both under Travel -> Hotels and clear from Needs Review")
            print("Run with --apply to commit.")
            return

        print("\nApplying reconciliation...")
        # 1. Debit
        classify_transaction(
            session,
            debit.id,
            category_id=travel_cat.id,
            subcategory_id=hotels_sub.id if hotels_sub else None,
        )
        debit.excludes_from_spending = True
        debit.needs_review = False
        debit.user_verified = True

        # 2. Credit
        credit.merchant_normalized = "Airbnb"
        classify_transaction(
            session,
            credit.id,
            category_id=travel_cat.id,
            subcategory_id=hotels_sub.id if hotels_sub else None,
        )
        credit.is_refund = True
        credit.excludes_from_spending = True
        credit.needs_review = False
        credit.user_verified = True

        session.commit()
        print("Successfully reconciled and closed the 18,900 INR Airbnb purchase and refund pair.")


if __name__ == "__main__":
    main()
