"""Create Personal Care category and classify Pony Salons transactions.

Usage:
    python scripts/create_personal_care_category.py --dry-run
    python scripts/create_personal_care_category.py --apply
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
from mymonee.db.models import Category, Merchant, Subcategory, Transaction, new_id
from mymonee.db.session import init_engine
from mymonee.services.transactions import classify_transaction


def main() -> None:
    parser = argparse.ArgumentParser(description="Create Personal Care category and classify salon transactions")
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
        # Check or create Personal Care category
        cat = session.scalar(select(Category).where(Category.slug == "personal-care"))
        if not cat:
            cat = Category(
                id=new_id(),
                name="Personal Care",
                slug="personal-care",
                expense_type="discretionary",
                sort_order=15,
                is_system=False,
            )
            session.add(cat)
            session.flush()
            print(f"Created category: {cat.name} ({cat.id})")
        else:
            print(f"Existing category: {cat.name} ({cat.id})")

        # Subcategories
        subs_to_create = [
            ("Salon & Haircut", "salon-haircut"),
            ("Grooming", "grooming"),
            ("Spa", "spa"),
        ]
        sub_map = {}
        for sub_name, sub_slug in subs_to_create:
            sub = session.scalar(
                select(Subcategory).where(
                    Subcategory.category_id == cat.id,
                    Subcategory.slug == sub_slug,
                )
            )
            if not sub:
                sub = Subcategory(
                    id=new_id(),
                    category_id=cat.id,
                    name=sub_name,
                    slug=sub_slug,
                    sort_order=len(sub_map),
                )
                session.add(sub)
                session.flush()
                print(f"  + Created subcategory: {sub.name} ({sub.id})")
            else:
                print(f"  * Existing subcategory: {sub.name} ({sub.id})")
            sub_map[sub_slug] = sub

        salon_sub = sub_map["salon-haircut"]

        # Find Pony Salons transactions
        target_merchant = "Pony Salons"
        stmt = select(Transaction).where(
            (Transaction.merchant_normalized == target_merchant)
            | (Transaction.merchant_raw == target_merchant)
        )
        txs = list(session.scalars(stmt).all())

        print(f"\nFound {len(txs)} transactions for '{target_merchant}':")
        for tx in txs:
            print(
                f"  - [{tx.id}] {tx.transaction_date} | {tx.amount} {tx.currency} | "
                f"Needs review: {tx.needs_review}"
            )

        if args.dry_run:
            print(f"\n[DRY RUN] Would classify {len(txs)} transactions as '{cat.name} -> {salon_sub.name}'.")
            print("Run with --apply to commit.")
            return

        print(f"\nApplying classification for {len(txs)} transactions...")
        for tx in txs:
            classify_transaction(
                session,
                tx.id,
                category_id=cat.id,
                subcategory_id=salon_sub.id,
            )

        # Update or create Merchant record
        merchant = session.scalar(select(Merchant).where(Merchant.display_name == target_merchant))
        if merchant:
            merchant.default_category_id = cat.id
            merchant.default_subcategory_id = salon_sub.id

        session.commit()
        print(f"Successfully classified {len(txs)} transactions as '{cat.name} -> {salon_sub.name}'.")


if __name__ == "__main__":
    main()
