"""Safely merge and clean up duplicate auto-created accounts.

Usage:
    .venv/bin/python scripts/cleanup_duplicate_accounts.py --dry-run
    .venv/bin/python scripts/cleanup_duplicate_accounts.py --execute
"""

from __future__ import annotations

import argparse
import logging
import sys

from sqlalchemy import select

from expense_tracker.config import get_settings
from expense_tracker.db.models import (
    Account,
    CreditCardStatement,
    IncomeSource,
    Posting,
    RecurringTransaction,
    StatementAccount,
)
from expense_tracker.db.session import init_db, get_session_factory

logger = logging.getLogger("expense_tracker.scripts.cleanup_duplicate_accounts")

# Explicit mapping of known auto-created duplicate names to canonical primary account names
MERGE_TARGET_MAP = {
    "Credit Card 0863": "Scapia VISA Credit Card",
    "Credit Card 4951": "Axis Bank Credit Card",
    "Credit Card 1221": "Scapia RuPay Credit Card",
    "****1022 Account": "Axis Bank",
    "801022 Account": "Axis Bank",
    "UPI bigbasket": "Axis Bank",
    "card Account": "Axis Bank Credit Card",
    "upi Account": "Axis Bank",
}


def find_duplicates_and_targets(session) -> list[tuple[Account, Account, int]]:
    all_accounts = session.scalars(select(Account)).all()
    name_to_account = {acc.name: acc for acc in all_accounts}

    merges: list[tuple[Account, Account, int]] = []
    for dup_name, target_name in MERGE_TARGET_MAP.items():
        dup_acc = name_to_account.get(dup_name)
        target_acc = name_to_account.get(target_name)
        if dup_acc and target_acc and dup_acc.id != target_acc.id:
            postings_count = session.query(Posting).filter(Posting.account_id == dup_acc.id).count()
            merges.append((dup_acc, target_acc, postings_count))

    return merges


def run_cleanup(*, execute: bool = False) -> int:
    settings = get_settings()
    init_db(settings)
    session_factory = get_session_factory()

    with session_factory() as session:
        merges = find_duplicates_and_targets(session)
        if not merges:
            print("No duplicate accounts found to merge.")
            return 0

        print(f"Found {len(merges)} duplicate account(s) to merge:")
        for dup_acc, target_acc, postings_count in merges:
            print(f"  • {dup_acc.name!r} (ID: {dup_acc.id[:8]}, {postings_count} postings) -> {target_acc.name!r} (ID: {target_acc.id[:8]})")

        if not execute:
            print("\n[DRY RUN] No changes made. Run with --execute to apply the merge and cleanup.")
            return 0

        total_postings_moved = 0
        deleted_accounts = 0

        for dup_acc, target_acc, count in merges:
            # 1. Move postings
            postings = session.scalars(select(Posting).where(Posting.account_id == dup_acc.id)).all()
            for p in postings:
                p.account_id = target_acc.id
            total_postings_moved += len(postings)

            # 2. Check for other references
            for model, attr in [
                (IncomeSource, "account_id"),
                (RecurringTransaction, "account_id"),
                (CreditCardStatement, "account_id"),
                (StatementAccount, "linked_account_id"),
            ]:
                rows = session.scalars(select(model).where(getattr(model, attr) == dup_acc.id)).all()
                for r in rows:
                    setattr(r, attr, target_acc.id)

            # 3. Delete duplicate account
            session.delete(dup_acc)
            deleted_accounts += 1

        session.commit()
        print(f"\n[EXECUTE COMPLETE] Successfully re-linked {total_postings_moved} postings and removed {deleted_accounts} duplicate accounts.")
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Merge duplicate auto-created accounts into canonical accounts.")
    parser.add_argument("--execute", action="store_true", help="Execute the merge and deletion (default is dry-run)")
    parser.add_argument("--dry-run", action="store_true", help="Inspect without modifying")
    args = parser.parse_args(argv)

    return run_cleanup(execute=args.execute)


if __name__ == "__main__":
    raise SystemExit(main())
