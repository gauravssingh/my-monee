"""Consolidate accounts and clean up junk/artifact accounts in SQLite ledger safely."""

from __future__ import annotations

import argparse
from sqlalchemy import select, update, delete
from sqlalchemy.orm import Session

from expense_tracker.db.session import get_session_factory
from expense_tracker.db.models import Account, Transaction, Posting, RecurringTransaction


def consolidate_accounts(*, apply: bool = False) -> None:
    SessionLocal = get_session_factory()
    with SessionLocal() as session:
        # 1. Fetch all accounts
        all_accounts = session.scalars(select(Account)).all()
        acc_by_name = {a.name: a for a in all_accounts}

        # Canonical mapping targeting existing account objects to preserve PKs
        # (name, new_name, type, last4_card, masked_num, is_asset, is_liab)
        target_mappings = [
            ("Axis Bank", "Axis Bank (XX1022)", "BANK", None, "****1022", True, False),
            ("Standard Chartered", "Standard Chartered Bank (XX1456)", "BANK", None, "****1456", True, False),
            ("XXXX43 Account", "ICICI Bank (XX0143)", "BANK", None, "****0143", True, False),
            ("Credit Card 4951", "Axis Bank Credit Card (XX4951)", "CREDIT_CARD", "4951", None, False, True),
            ("Credit Card 0863", "Scapia VISA Credit Card (XX0863)", "CREDIT_CARD", "0863", None, False, True),
            ("Credit Card 1221", "Scapia RuPay Credit Card (XX1221)", "CREDIT_CARD", "1221", None, False, True),
            ("Credit Card 1323", "Credit Card (XX1323)", "CREDIT_CARD", "1323", None, False, True),
            ("FASTag Wallet", "FASTag Wallet", "WALLET", None, None, True, False),
            ("Default Cash Account", "Default Cash Account", "CASH", None, None, True, False),
        ]

        canonical_accounts: dict[str, Account] = {}

        for old_key, new_name, acc_type, card4, num_masked, is_asset, is_liab in target_mappings:
            acc = acc_by_name.get(old_key) or acc_by_name.get(new_name)
            if not acc:
                acc = Account(
                    name=new_name,
                    account_type=acc_type,
                    account_number_masked=num_masked,
                    card_last4=card4,
                    is_asset=is_asset,
                    is_liability=is_liab,
                    currency="INR",
                )
                if apply:
                    session.add(acc)
                    session.flush()
            else:
                if apply:
                    acc.name = new_name
                    acc.account_type = acc_type
                    acc.account_number_masked = num_masked
                    acc.card_last4 = card4
                    acc.is_asset = is_asset
                    acc.is_liability = is_liab
            canonical_accounts[new_name] = acc

        canonical_ids = {a.id for a in canonical_accounts.values()}

        # 2. Relink transactions
        all_txs = session.scalars(select(Transaction)).all()
        relinked_tx_count = 0

        for tx in all_txs:
            old_acc = tx.account
            old_card = tx.card
            desc = tx.description or ""

            # Axis Bank (XX1022)
            if (
                old_acc in ["****1022", "XX1022", "Axis Bank", "****6299", "XXXX424", "XXXX838", "****9718", "Axis Bank (XX1022)"]
                or "A/c no. XX1022" in desc
                or "Axis Bank A/c" in desc
            ):
                new_acc = "Axis Bank (XX1022)"
                if tx.account != new_acc:
                    if apply:
                        tx.account = new_acc
                    relinked_tx_count += 1

            # Standard Chartered Bank (XX1456)
            elif (
                old_acc in ["****1456", "Standard Chartered", "Standard Chartered Bank", "Standard Chartered Bank (XX1456)"]
                or "Standard Chartered" in desc
            ):
                new_acc = "Standard Chartered Bank (XX1456)"
                if tx.account != new_acc:
                    if apply:
                        tx.account = new_acc
                    relinked_tx_count += 1

            # ICICI Bank (XX0143)
            elif (
                old_acc in ["XXXX43", "XX143", "****0143", "0143", "ICICI Bank (XX0143)"]
                or "ICICI Bank account" in desc
                or "ICICI Bank debit card" in desc
                or "Account XX143" in desc
            ):
                new_acc = "ICICI Bank (XX0143)"
                if tx.account != new_acc:
                    if apply:
                        tx.account = new_acc
                    relinked_tx_count += 1

            # Axis Bank Credit Card (XX4951)
            if (
                old_card in ["4951", "XX4951", "1234", "1391"]
                or "XX4951" in desc
                or "Rewards Credit Card ending XX51" in desc
                or (old_acc == "****1234")
            ):
                if apply:
                    tx.card = "4951"
                    tx.account = "Axis Bank Credit Card (XX4951)"
                relinked_tx_count += 1

            # Scapia VISA Credit Card (XX0863)
            elif old_card in ["0863", "XX0863"] or "ending in 0863" in desc or "XX0863" in desc:
                if apply:
                    tx.card = "0863"
                    tx.account = "Scapia VISA Credit Card (XX0863)"
                relinked_tx_count += 1

            # Scapia RuPay Credit Card (XX1221)
            elif old_card in ["1221", "XX1221"] or "ending in 1221" in desc or "XX1221" in desc:
                if apply:
                    tx.card = "1221"
                    tx.account = "Scapia RuPay Credit Card (XX1221)"
                relinked_tx_count += 1

            # Credit Card (XX1323)
            elif old_card in ["1323", "XX1323"] or "XX1323" in desc:
                if apply:
                    tx.card = "1323"
                    tx.account = "Credit Card (XX1323)"
                relinked_tx_count += 1

            # FASTag
            elif "FASTag" in desc:
                if apply:
                    tx.account = "FASTag Wallet"
                relinked_tx_count += 1

        # 3. Re-map Postings & Recurring Transactions pointing to non-canonical accounts
        axis_acc = canonical_accounts["Axis Bank (XX1022)"]
        axis_card = canonical_accounts["Axis Bank Credit Card (XX4951)"]

        # Default non-canonical postings to primary Axis account
        if apply:
            session.execute(
                update(Posting)
                .where(Posting.account_id.notin_(canonical_ids))
                .values(account_id=axis_acc.id)
            )
            session.execute(
                update(RecurringTransaction)
                .where(RecurringTransaction.account_id.notin_(canonical_ids))
                .values(account_id=axis_acc.id)
            )

        # 4. Safely delete orphan non-canonical accounts
        purged_count = 0
        for acc in all_accounts:
            if acc.id not in canonical_ids:
                purged_count += 1
                if apply:
                    session.delete(acc)

        if apply:
            session.commit()
            print(f"Successfully consolidated accounts!")
            print(f"  - Canonical accounts active (9): {list(canonical_accounts.keys())}")
            print(f"  - Purged junk/artifact accounts: {purged_count}")
            print(f"  - Relinked transactions: {relinked_tx_count}")
        else:
            print(f"[DRY-RUN] Consolidation Plan:")
            print(f"  - Canonical accounts to keep/rename (9): {list(canonical_accounts.keys())}")
            print(f"  - Junk accounts to purge: {purged_count}")
            print(f"  - Transactions to relink: {relinked_tx_count}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Consolidate accounts safely.")
    parser.add_argument("--apply", action="store_true", help="Apply consolidation.")
    args = parser.parse_args()
    consolidate_accounts(apply=args.apply)
