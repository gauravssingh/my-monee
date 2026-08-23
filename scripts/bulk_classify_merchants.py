"""Bulk classify transactions for specified merchants into category / subcategory.

Usage:
    python scripts/bulk_classify_merchants.py --dry-run
    python scripts/bulk_classify_merchants.py --apply
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

from mymonee.config import get_settings
from mymonee.db.models import Category, Merchant, Subcategory, Transaction
from mymonee.db.session import init_engine
from mymonee.services.transactions import classify_transaction
from sqlalchemy.orm import Session


def main() -> None:
    parser = argparse.ArgumentParser(description="Bulk classify merchants")
    parser.add_argument("--apply", action="store_true", help="Apply changes to the database")
    parser.add_argument("--dry-run", action="store_true", help="Dry run without committing changes")
    args = parser.parse_args()

    if not args.apply and not args.dry_run:
        print("Please specify either --dry-run or --apply")
        sys.exit(1)

    settings = get_settings()
    engine = init_engine(settings)
    print(f"Connecting to database: {settings.database_path()}")

    target_merchants = ["Syed Naseeruddin", "Kings Pan Shop"]

    with Session(engine) as session:
        # Find Food -> Tea Break
        food_cat = session.scalar(select(Category).where(Category.slug == "food"))
        if not food_cat:
            print("Error: 'Food' category not found in database.")
            sys.exit(1)

        tea_sub = session.scalar(
            select(Subcategory).where(
                Subcategory.category_id == food_cat.id,
                Subcategory.slug == "tea-break",
            )
        )
        if not tea_sub:
            print("Error: 'Tea Break' subcategory not found under Food.")
            sys.exit(1)

        print(f"Target Category: {food_cat.name} ({food_cat.id})")
        print(f"Target Subcategory: {tea_sub.name} ({tea_sub.id})\n")

        stmt = select(Transaction).where(
            (Transaction.merchant_normalized.in_(target_merchants))
            | (Transaction.merchant_raw.in_(target_merchants))
        )
        txs = list(session.scalars(stmt).all())

        print(f"Found {len(txs)} transactions matching target merchants {target_merchants}:")
        for tx in txs:
            print(
                f"  - [{tx.id}] {tx.transaction_date} | {tx.merchant_normalized} | "
                f"{tx.amount} {tx.currency} | Current: {tx.category_id} | Needs review: {tx.needs_review}"
            )

        if args.dry_run:
            print(f"\n[DRY RUN] Would classify {len(txs)} transactions as '{food_cat.name} -> {tea_sub.name}'.")
            print("Run with --apply to commit.")
            return

        print(f"\nApplying classification for {len(txs)} transactions...")
        for tx in txs:
            classify_transaction(
                session,
                tx.id,
                category_id=food_cat.id,
                subcategory_id=tea_sub.id,
            )

        # Also set default_category on Merchant records if they exist
        for m_name in target_merchants:
            merchant = session.scalar(select(Merchant).where(Merchant.display_name == m_name))
            if merchant:
                merchant.default_category_id = food_cat.id
                merchant.default_subcategory_id = tea_sub.id

        session.commit()
        print(f"Successfully classified {len(txs)} transactions as '{food_cat.name} -> {tea_sub.name}'.")


if __name__ == "__main__":
    main()
