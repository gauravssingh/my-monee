"""Split housing transactions into Home -> Maintenance and Utilities -> Electricity, and exclude receipt duplicates.

Rule:
- First 10 days of the month and amount around 7k (or annual maintenance) -> Home -> Maintenance
- Other society / power / utility bills -> Utilities -> Electricity
- Razorpay / NoBrokerHood duplicate receipts, notices, and circulars -> Exclude as non-transactions

Usage:
    python scripts/reconcile_housing_and_utilities.py --dry-run
    python scripts/reconcile_housing_and_utilities.py --apply
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
from mymonee.db.models import Category, Email, Subcategory, Transaction
from mymonee.db.session import init_engine
from mymonee.services.transactions import classify_transaction, exclude_as_non_transaction


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconcile housing and electricity transactions")
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
        home_cat = session.scalar(select(Category).where(Category.slug == "home"))
        maintenance_sub = session.scalar(
            select(Subcategory).where(
                Subcategory.category_id == home_cat.id,
                Subcategory.slug == "maintenance",
            )
        )

        util_cat = session.scalar(select(Category).where(Category.slug == "utilities"))
        electricity_sub = session.scalar(
            select(Subcategory).where(
                Subcategory.category_id == util_cat.id,
                Subcategory.slug == "electricity",
            )
        )

        # 1. Non-transaction duplicates / notices to exclude
        exclude_stmt = select(Transaction).where(
            (
                Transaction.description.like("Payment successful for NOBROKER%")
                | Transaction.description.like("Payment Successful for Monthly Maintenance%")
                | Transaction.description.like("Payment failed for NOBROKER%")
                | Transaction.description.like("Notice - MOVE IN%")
                | Transaction.description.like("New Monthly Maintenance Charges Bill is added%")
                | Transaction.description.like("Annual Maintenance - Payable April 2026 generated%")
            )
            & (Transaction.transaction_type != "not_a_transaction")
        )
        to_exclude = list(session.scalars(exclude_stmt).all())

        # 2. Genuine bank debits
        genuine_stmt = select(Transaction).where(
            (
                Transaction.merchant_raw.like("%nobroker%")
                | Transaction.merchant_normalized.like("%nobroker%")
                | Transaction.description.like("%nobroker%")
                | Transaction.merchant_raw.like("%aparna%")
                | Transaction.merchant_normalized.like("%aparna%")
                | Transaction.merchant_raw.like("%mygate%")
                | Transaction.description.like("%mygate%")
                | Transaction.merchant_raw.like("%pnb*nobroke%")
                | Transaction.merchant_normalized.like("%pnb*nobroke%")
            )
            & (Transaction.direction == "debit")
            & (~Transaction.id.in_([t.id for t in to_exclude]))
            & (Transaction.transaction_type != "declined")
        )
        genuine_txs = list(session.scalars(genuine_stmt).all())

        # Filter out Aparna Cinemas (movies)
        genuine_txs = [t for t in genuine_txs if "cinemas" not in (t.merchant_normalized or "").lower()]

        maintenance_txs: list[Transaction] = []
        electricity_txs: list[Transaction] = []

        for tx in genuine_txs:
            day = tx.transaction_date.day
            amt = float(tx.amount)
            # Rule: paid within first 10 days and around 7k (6k..8k) or annual maintenance (> 20k)
            if (day <= 10 and 6000 <= amt <= 8000) or (day <= 10 and amt >= 20000 and "mygate" in (tx.merchant_raw or "").lower()):
                maintenance_txs.append(tx)
            else:
                electricity_txs.append(tx)

        print(f"=== 1. TO EXCLUDE (Duplicates & Notices): {len(to_exclude)} ===")
        for t in to_exclude:
            print(f"  - [{t.id}] {t.transaction_date} | {t.amount} INR | {t.description}")

        print(f"\n=== 2. HOME -> MAINTENANCE (First 10 days, ~7k): {len(maintenance_txs)} ===")
        for t in maintenance_txs:
            print(f"  - [{t.id}] {t.transaction_date} | {t.amount} INR | {t.merchant_normalized or t.merchant_raw}")

        print(f"\n=== 3. UTILITIES -> ELECTRICITY (Other periodic bills): {len(electricity_txs)} ===")
        for t in electricity_txs:
            print(f"  - [{t.id}] {t.transaction_date} | {t.amount} INR | {t.merchant_normalized or t.merchant_raw}")

        if args.dry_run:
            print("\n[DRY RUN] No changes committed. Run with --apply to commit.")
            return

        print("\nApplying updates...")
        for t in to_exclude:
            exclude_as_non_transaction(session, t.id)

        for t in maintenance_txs:
            classify_transaction(
                session,
                t.id,
                category_id=home_cat.id,
                subcategory_id=maintenance_sub.id,
            )
            t.excludes_from_spending = False
            t.needs_review = False
            t.user_verified = True

        for t in electricity_txs:
            classify_transaction(
                session,
                t.id,
                category_id=util_cat.id,
                subcategory_id=electricity_sub.id,
            )
            t.excludes_from_spending = False
            t.needs_review = False
            t.user_verified = True

        session.commit()
        print("\nSuccessfully updated all housing, maintenance, and electricity transactions.")


if __name__ == "__main__":
    main()
