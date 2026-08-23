"""Reconcile Caratlane purchases and Ruheena S transfers into Transfers -> Ruheena.

Usage:
    python scripts/reconcile_caratlane_ruheena.py --dry-run
    python scripts/reconcile_caratlane_ruheena.py --apply
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
from mymonee.db.models import Category, Subcategory, Transaction, new_id
from mymonee.db.session import init_engine
from mymonee.services.transactions import classify_transaction, mark_reimbursed


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconcile Caratlane & Ruheena transactions")
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
        # Find or create Transfers -> Ruheena
        transfers_cat = session.scalar(select(Category).where(Category.slug == "transfers"))
        if not transfers_cat:
            print("Error: Transfers category not found.")
            sys.exit(1)

        ruheena_sub = session.scalar(
            select(Subcategory).where(
                Subcategory.category_id == transfers_cat.id,
                Subcategory.slug == "ruheena",
            )
        )
        if not ruheena_sub:
            ruheena_sub = Subcategory(
                id=new_id(),
                category_id=transfers_cat.id,
                name="Ruheena",
                slug="ruheena",
                sort_order=10,
            )
            session.add(ruheena_sub)
            session.flush()
            print(f"Created subcategory: Transfers -> {ruheena_sub.name} ({ruheena_sub.id})")
        else:
            print(f"Found subcategory: Transfers -> {ruheena_sub.name} ({ruheena_sub.id})")

        # 1. Caratlane debits in February 2026 (including PAY*CARATLA and CARATLANE T)
        caratlane_stmt = select(Transaction).where(
            (Transaction.merchant_raw.like("%caratla%") | Transaction.merchant_normalized.like("%caratla%"))
            & (Transaction.direction == "debit")
            & (Transaction.transaction_type != "declined")
            & (Transaction.transaction_date >= "2026-02-01")
            & (Transaction.transaction_date <= "2026-02-28 23:59:59")
        )
        caratlane_txs = list(session.scalars(caratlane_stmt).all())

        # 2. Ruheena credits in February 2026
        ruheena_credit_ids = [
            "d9d7682d-c495-4e0f-8689-0928ef5828ee",  # 84,432 (Feb 25)
            "55a39300-7563-482f-9a03-c664d35f30d4",  # 87,474 (Feb 26)
            "b6e37574-1ad0-4207-90b3-851ea742652a",  # 87,474 (Feb 28)
            "6306ce84-546a-414b-b16a-40e011741d14",  # 55,000 (Feb 03)
            "3dbd5e97-d8a6-4afe-b3cc-2da946b2b0ae",  # 80,000 (Feb 04)
        ]
        ruheena_credits = list(
            session.scalars(select(Transaction).where(Transaction.id.in_(ruheena_credit_ids))).all()
        )

        all_target_txs = caratlane_txs + ruheena_credits
        print(f"\nFound {len(caratlane_txs)} Caratlane debits to mark as reimbursed:")
        for tx in caratlane_txs:
            print(
                f"  - [{tx.id}] {tx.transaction_date} | {tx.merchant_raw} | "
                f"Amount: {tx.amount} {tx.currency}"
            )

        print(f"\nFound {len(ruheena_credits)} Ruheena credits to classify into Transfers -> Ruheena:")
        for tx in ruheena_credits:
            print(
                f"  - [{tx.id}] {tx.transaction_date} | Amount: {tx.amount} {tx.currency}"
            )

        if args.dry_run:
            print(
                f"\n[DRY RUN] Would mark {len(caratlane_txs)} Caratlane debits as reimbursed (excluded from spending) "
                f"and classify {len(ruheena_credits)} Ruheena credits into Transfers -> Ruheena (excluded from spending & income)."
            )
            print("Run with --apply to commit.")
            return

        print(f"\nApplying Caratlane debits mark_reimbursed...")
        for tx in caratlane_txs:
            mark_reimbursed(session, tx.id)
            tx.excludes_from_spending = True
            tx.needs_review = False
            tx.user_verified = True

        print(f"Applying Ruheena credits classification into Transfers -> Ruheena...")
        for tx in ruheena_credits:
            tx.merchant_raw = "RUHEENA S"
            tx.merchant_normalized = "Ruheena S"
            classify_transaction(
                session,
                tx.id,
                category_id=transfers_cat.id,
                subcategory_id=ruheena_sub.id,
            )
            tx.is_transfer = True
            tx.excludes_from_spending = True
            tx.needs_review = False
            tx.user_verified = True

        session.commit()
        print(f"\nSuccessfully reconciled all {len(caratlane_txs)} Caratlane debits as reimbursed and {len(ruheena_credits)} Ruheena credits into Transfers -> Ruheena.")


if __name__ == "__main__":
    main()
