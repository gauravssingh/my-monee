"""Flag and exclude Zype loan promotional emails.

Usage:
    python scripts/flag_and_exclude_zype_loans.py --dry-run
    python scripts/flag_and_exclude_zype_loans.py --apply
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
from expense_tracker.db.models import Transaction
from expense_tracker.db.session import init_engine
from expense_tracker.services.data_issues import flag_transaction_issue
from expense_tracker.services.transactions import exclude_as_non_transaction


def main() -> None:
    parser = argparse.ArgumentParser(description="Flag and exclude Zype loan emails")
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
        stmt = select(Transaction).where(Transaction.description.like("%unlock Zype loan%"))
        zype_txs = list(session.scalars(stmt).all())

        print(f"Found {len(zype_txs)} Zype promotional loan transactions:")
        for tx in zype_txs:
            print(f"  - [{tx.id}] {tx.transaction_date} | {tx.amount} {tx.currency} | {tx.description}")

        if args.dry_run:
            print("\n[DRY RUN] Would flag with issue_type='not_a_transaction' and exclude from spending.")
            print("Run with --apply to commit.")
            return

        print("\nApplying flags and excluding from spending...")
        for tx in zype_txs:
            flag_transaction_issue(
                session,
                tx.id,
                issue_type="not_a_transaction",
                note="Promotional marketing email for Zype loan, not a real financial transaction",
            )
            exclude_as_non_transaction(session, tx.id)

        session.commit()
        print(f"Successfully flagged and excluded {len(zype_txs)} Zype loan transactions.")


if __name__ == "__main__":
    main()
