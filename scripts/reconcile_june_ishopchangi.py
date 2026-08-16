"""Reconcile June 2026 iShopChangi purchase with actual INR transaction (37,467 INR).

Usage:
    python scripts/reconcile_june_ishopchangi.py --dry-run
    python scripts/reconcile_june_ishopchangi.py --apply
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
from expense_tracker.db.models import Category, Subcategory, Transaction
from expense_tracker.db.session import init_engine
from expense_tracker.services.transactions import classify_transaction, exclude_as_non_transaction


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconcile iShopChangi SGD and INR transactions")
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
        # Find Shopping -> Electronics
        shopping_cat = session.scalar(select(Category).where(Category.slug == "shopping"))
        electronics_sub = session.scalar(
            select(Subcategory).where(
                Subcategory.category_id == shopping_cat.id,
                Subcategory.slug == "electronics",
            )
        )

        sgd_tx_id = "91559376-69bd-43b2-9f3a-2482e42eb5c8"
        inr_tx_id = "5dda2bc4-6a0f-48a5-8714-ef89878fa59a"

        sgd_tx = session.get(Transaction, sgd_tx_id)
        inr_tx = session.get(Transaction, inr_tx_id)

        print(f"1. SGD Transaction: [{sgd_tx.id}] {sgd_tx.transaction_date} | {sgd_tx.amount} INR | {sgd_tx.description}")
        print(f"2. INR Transaction: [{inr_tx.id}] {inr_tx.transaction_date} | {inr_tx.amount} INR | {inr_tx.merchant_raw}")

        if args.dry_run:
            print("\n[DRY RUN] Would:")
            print("  - Discard/exclude SGD transaction (1,114,781.63 INR) as non-transaction")
            print(f"  - Classify 37,467 INR transaction under Shopping -> Electronics ({electronics_sub.id})")
            print("Run with --apply to commit.")
            return

        print("\nApplying updates...")
        # 1. Exclude SGD parse artifact
        exclude_as_non_transaction(session, sgd_tx.id)

        # 2. Classify actual 37,467 INR purchase under Shopping -> Electronics
        inr_tx.merchant_normalized = "iShopChangi (Singapore Airport)"
        classify_transaction(
            session,
            inr_tx.id,
            category_id=shopping_cat.id,
            subcategory_id=electronics_sub.id,
        )
        inr_tx.excludes_from_spending = False
        inr_tx.needs_review = False
        inr_tx.user_verified = True

        session.commit()
        print("Successfully reconciled iShopChangi SGD and INR transactions.")


if __name__ == "__main__":
    main()
