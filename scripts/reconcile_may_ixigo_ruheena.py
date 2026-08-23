"""Reconcile May 2026 Ixigo flight ticket booking and Ruheena S transfer.

Usage:
    python scripts/reconcile_may_ixigo_ruheena.py --dry-run
    python scripts/reconcile_may_ixigo_ruheena.py --apply
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
from mymonee.services.transactions import (
    classify_transaction,
    exclude_as_non_transaction,
    mark_reimbursed,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconcile May Ixigo flight tickets and Ruheena transfer")
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
        # Find Transfers -> Ruheena
        transfers_cat = session.scalar(select(Category).where(Category.slug == "transfers"))
        ruheena_sub = session.scalar(
            select(Subcategory).where(
                Subcategory.category_id == transfers_cat.id,
                Subcategory.slug == "ruheena",
            )
        )

        ixigo_debit_id = "720e0545-a625-4d5b-a257-00e10bd8c5fe"
        ruheena_credit_id = "072c74e8-f183-4aa7-b8b7-2fc30f25609d"
        ixigo_invoice_id = "ac44ba04-dd26-4818-89c7-ec1d9351cc6b"

        ixigo_debit = session.get(Transaction, ixigo_debit_id)
        ruheena_credit = session.get(Transaction, ruheena_credit_id)
        ixigo_invoice = session.get(Transaction, ixigo_invoice_id)

        print(f"1. Ixigo Debit: [{ixigo_debit.id}] {ixigo_debit.transaction_date} | {ixigo_debit.amount} INR")
        print(f"2. Ruheena Credit: [{ruheena_credit.id}] {ruheena_credit.transaction_date} | {ruheena_credit.amount} INR")
        print(f"3. Ixigo Duplicate Invoice: [{ixigo_invoice.id}] {ixigo_invoice.transaction_date} | {ixigo_invoice.amount} INR")

        if args.dry_run:
            print("\n[DRY RUN] Would:")
            print("  - Mark Ixigo debit as reimbursed (excludes_from_spending=True)")
            print(f"  - Classify Ruheena credit as Transfers -> Ruheena (is_transfer=True, excludes_from_spending=True)")
            print("  - Exclude duplicate Ixigo invoice email as non-transaction")
            print("Run with --apply to commit.")
            return

        print("\nApplying changes...")
        # 1. Reimbursed flight debit
        mark_reimbursed(session, ixigo_debit.id)
        ixigo_debit.excludes_from_spending = True
        ixigo_debit.needs_review = False
        ixigo_debit.user_verified = True

        # 2. Ruheena transfer credit
        ruheena_credit.merchant_raw = "RUHEENA S"
        ruheena_credit.merchant_normalized = "Ruheena S"
        classify_transaction(
            session,
            ruheena_credit.id,
            category_id=transfers_cat.id,
            subcategory_id=ruheena_sub.id,
        )
        ruheena_credit.is_transfer = True
        ruheena_credit.excludes_from_spending = True
        ruheena_credit.needs_review = False
        ruheena_credit.user_verified = True

        # 3. Exclude duplicate invoice
        exclude_as_non_transaction(session, ixigo_invoice.id)

        session.commit()
        print("Successfully reconciled May Ixigo flights and Ruheena transfer.")


if __name__ == "__main__":
    main()
