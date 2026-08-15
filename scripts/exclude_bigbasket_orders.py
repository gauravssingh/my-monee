"""Exclude Bigbasket order confirmation emails that were ingested as transactions.

Usage:
    python scripts/exclude_bigbasket_orders.py --dry-run
    python scripts/exclude_bigbasket_orders.py --apply
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

from expense_tracker.config import get_settings
from expense_tracker.db.models import Transaction
from expense_tracker.db.session import init_engine
from expense_tracker.services.transactions import exclude_as_non_transaction
from sqlalchemy.orm import Session


def main() -> None:
    parser = argparse.ArgumentParser(description="Exclude Bigbasket order confirmations")
    parser.add_argument("--apply", action="store_true", help="Apply changes to the database")
    parser.add_argument("--dry-run", action="store_true", help="Dry run without committing changes")
    args = parser.parse_args()

    if not args.apply and not args.dry_run:
        print("Please specify either --dry-run or --apply")
        sys.exit(1)

    settings = get_settings()
    engine = init_engine(settings)
    print(f"Connecting to database: {settings.database_path()}")

    with Session(engine) as session:
        stmt = (
            select(Transaction)
            .where(
                (Transaction.merchant_normalized.like("Bigbasket Order No%"))
                | (Transaction.merchant_raw.like("bigbasket Order No%"))
            )
            .where(Transaction.excludes_from_spending.is_(False) | Transaction.needs_review.is_(True))
        )
        txs = list(session.scalars(stmt).all())

        print(f"Found {len(txs)} Bigbasket order confirmation transactions to exclude.")

        if not txs:
            print("No matching transactions found. Ledger is clean.")
            return

        for tx in txs:
            print(
                f"  - [{tx.id}] {tx.transaction_date} | {tx.merchant_raw} | "
                f"Amount: {tx.amount} {tx.currency} | Needs review: {tx.needs_review}"
            )

        if args.dry_run:
            print("\n[DRY RUN] No changes were written to the database. Run with --apply to commit.")
            return

        print(f"\nApplying exclusion for {len(txs)} transactions...")
        for tx in txs:
            exclude_as_non_transaction(session, tx.id)

        session.commit()
        print(f"Successfully excluded {len(txs)} Bigbasket order confirmations as non-transactions.")


if __name__ == "__main__":
    main()
