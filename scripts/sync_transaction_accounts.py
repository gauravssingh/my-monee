"""Sync and backfill transaction.account with canonical account names.

Usage:
    python scripts/sync_transaction_accounts.py --dry-run
    python scripts/sync_transaction_accounts.py --execute
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from expense_tracker.config import get_settings
from expense_tracker.db.models import Account, Posting, Transaction
from expense_tracker.db.session import get_session_factory, init_db


def sync_transaction_accounts(execute: bool = False) -> None:
    settings = get_settings()
    init_db(settings)
    factory = get_session_factory()

    with factory() as session:
        all_accounts = session.query(Account).all()
        acc_map = {a.id: a for a in all_accounts}

        txs = session.query(Transaction).all()
        updates: list[tuple[Transaction, str | None, str]] = []

        for tx in txs:
            target: str | None = None
            card = (tx.card or "").strip()
            acc_str = (tx.account or "").strip()

            # 1. Match by card last-4
            if card == "4951" or "4951" in acc_str or acc_str == "Axis Bank Credit Card":
                target = "Axis Bank Credit Card (XX4951)"
            elif card == "0863" or "0863" in acc_str or ("scapia_federal" in (tx.source or "") and card != "1221"):
                target = "Scapia VISA Credit Card (XX0863)"
            elif card == "1221" or "1221" in acc_str:
                target = "Scapia RuPay Credit Card (XX1221)"
            elif acc_str == "FASTag Wallet" or "Axis Bank FASTag" in (tx.description or ""):
                target = "FASTag Wallet"
            # 2. Match by account digits or known sources
            elif any(k in acc_str for k in ["1022", "801022", "Axis Bank", "PhonePe", "XXX424", "XXX838"]) or tx.source in [
                "gmail:axis_alerts",
                "gmail:axis_bank",
                "gmail:upi_phonepe",
            ]:
                target = "Axis Bank (XX1022)"
            elif "1456" in acc_str or "Standard Chartered" in acc_str:
                target = "Standard Chartered Bank (XX1456)"
            elif "0143" in acc_str or "XX43" in acc_str or "ICICI" in acc_str:
                target = "ICICI Bank (XX0143)"
            elif tx.financial_event_id:
                posting = (
                    session.query(Posting)
                    .filter(Posting.event_id == tx.financial_event_id, Posting.account_id.is_not(None))
                    .first()
                )
                if posting and posting.account_id and posting.account_id in acc_map:
                    acc = acc_map[posting.account_id]
                    if acc.card_last4:
                        target = f"{acc.name} (XX{acc.card_last4})"
                    elif acc.account_number_masked:
                        num = acc.account_number_masked
                        num_str = f"XX{num}" if not num.startswith("XX") else num
                        target = f"{acc.name} ({num_str})"
                    else:
                        target = acc.name

            if target and tx.account != target:
                updates.append((tx, tx.account, target))

        print(f"Found {len(updates)} transaction(s) requiring account normalization.")
        
        breakdown: dict[str, int] = {}
        for _, old, new in updates:
            key = f"{repr(old)} -> {repr(new)}"
            breakdown[key] = breakdown.get(key, 0) + 1

        for key, count in sorted(breakdown.items(), key=lambda x: -x[1]):
            print(f"  {count:3d}x : {key}")

        if execute:
            for tx, _, new in updates:
                tx.account = new
            session.commit()
            print("\n[SUCCESS] Applied account normalization to database.")
        else:
            print("\n[DRY RUN] No changes were written. Pass --execute to apply.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync transaction account names to canonical ledger accounts.")
    parser.add_argument("--execute", action="store_true", help="Apply updates to database")
    parser.add_argument("--dry-run", action="store_true", help="Preview updates without modifying DB")
    args = parser.parse_args()

    if not args.execute and not args.dry_run:
        print("Please specify either --dry-run or --execute")
        sys.exit(1)

    sync_transaction_accounts(execute=args.execute)


if __name__ == "__main__":
    main()
