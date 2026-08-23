"""Sync and ensure all flagged data issues (not_a_transaction, duplicate) and non-transactions have excludes_from_spending = True.

Usage:
    python scripts/sync_flagged_and_excluded_spends.py --apply
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
from mymonee.db.models import DataIssueFlag, Transaction
from mymonee.db.session import init_engine
from mymonee.domain.enums import DataIssueStatus


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync flagged data issues and excluded spends")
    parser.add_argument("--apply", action="store_true", help="Apply changes to database")
    args = parser.parse_args()

    settings = get_settings()
    engine = init_engine(settings)
    print(f"Connecting to database: {settings.database_path()}")

    with Session(engine) as session:
        # 1. Flagged as not_a_transaction or duplicate
        flagged_stmt = select(Transaction).join(
            DataIssueFlag, Transaction.id == DataIssueFlag.transaction_id
        ).where(
            DataIssueFlag.status == DataIssueStatus.OPEN,
            DataIssueFlag.issue_type.in_(["not_a_transaction", "duplicate"]),
            Transaction.excludes_from_spending.is_(False),
        )
        flagged_txs = list(session.scalars(flagged_stmt).all())

        # 2. Marked as not_a_transaction / declined / is_duplicate
        non_tx_stmt = select(Transaction).where(
            (Transaction.transaction_type.in_(["not_a_transaction", "declined"]) | Transaction.is_duplicate.is_(True)),
            Transaction.excludes_from_spending.is_(False),
        )
        non_txs = list(session.scalars(non_tx_stmt).all())

        print(f"Found {len(flagged_txs)} open flagged transactions with excludes_from_spending=False")
        print(f"Found {len(non_txs)} non_transaction/declined/duplicate rows with excludes_from_spending=False")

        if not args.apply:
            print("Run with --apply to commit.")
            return

        for tx in flagged_txs:
            tx.excludes_from_spending = True
            tx.needs_review = False

        for tx in non_txs:
            tx.excludes_from_spending = True

        session.commit()
        print("Successfully synced all flagged and non-transaction records to excludes_from_spending=True.")


if __name__ == "__main__":
    main()
