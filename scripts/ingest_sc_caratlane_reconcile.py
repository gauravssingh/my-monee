"""Ingest Standard Chartered Caratlane 55k debit and reconcile with Ruheena 55k credit.

Usage:
    python scripts/ingest_sc_caratlane_reconcile.py --dry-run
    python scripts/ingest_sc_caratlane_reconcile.py --apply
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parents[1]
src_dir = root_dir / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from sqlalchemy import select
from sqlalchemy.orm import Session

from mymonee.config import get_settings
from mymonee.db.models import Category, Email, Subcategory, Transaction, new_id
from mymonee.db.session import init_engine
from mymonee.services.transactions import classify_transaction, mark_reimbursed


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest SC Caratlane debit and reconcile with Ruheena")
    parser.add_argument("--apply", action="store_true", help="Apply changes to database")
    parser.add_argument("--dry-run", action="store_true", help="Dry run without committing changes")
    args = parser.parse_args()

    if not args.apply and not args.dry_run:
        print("Please specify either --dry-run or --apply")
        sys.exit(1)

    settings = get_settings()
    engine = init_engine(settings)
    print(f"Connecting to database: {settings.database_path()}")

    email_id = "19c1eeb389524609"
    ruheena_credit_id = "6306ce84-546a-414b-b16a-40e011741d14"
    sc_account_id = "5871bacf-59ef-4333-8f61-a62baa11b19b"

    with Session(engine) as session:
        # Find Transfers -> Ruheena
        transfers_cat = session.scalar(select(Category).where(Category.slug == "transfers"))
        ruheena_sub = session.scalar(
            select(Subcategory).where(
                Subcategory.category_id == transfers_cat.id,
                Subcategory.slug == "ruheena",
            )
        )

        email = session.get(Email, email_id)
        if not email:
            print(f"Error: Email {email_id} not found.")
            sys.exit(1)

        ruheena_credit = session.get(Transaction, ruheena_credit_id)
        if not ruheena_credit:
            print(f"Error: Transaction {ruheena_credit_id} not found.")
            sys.exit(1)

        print(f"Found source email: {email.subject} ({email.received_at})")
        print(f"Found credit transaction: [{ruheena_credit.id}] {ruheena_credit.amount} {ruheena_credit.currency}")

        # Check if tx already exists for this email
        existing_tx = session.scalar(select(Transaction).where(Transaction.source_email_id == email_id))
        if existing_tx:
            print(f"Transaction already exists for email {email_id}: [{existing_tx.id}]")
            tx = existing_tx
        else:
            tx = Transaction(
                id=new_id(),
                source_email_id=email_id,
                account="Standard Chartered",
                transaction_date=datetime(2026, 2, 2, 15, 13, 49, tzinfo=timezone.utc),
                amount=Decimal("55000.00"),
                currency="INR",
                direction="debit",
                transaction_type="purchase",
                merchant_raw="caratlane",
                merchant_normalized="Caratlane",
                payment_method="upi",
                upi_id="caratlane.payu@axisbank",
                reference_number="977062877786",
                description="UPI payment to caratlane.payu@axisbank",
                is_transfer=False,
                is_refund=False,
                excludes_from_spending=True,
                needs_review=False,
                user_verified=True,
                classification_source="user",
                classification_confidence=1.0,
                classification_signals={
                    "rule": "user_reimbursed_caratlane",
                    "note": "Reimbursed by Ruheena S on 03 Feb 2026",
                },
                extra_json={"reimbursed": True},
            )
            session.add(tx)

        if args.dry_run:
            print("\n[DRY RUN] Would:")
            print("  - Create/Update 55,000 INR Caratlane debit transaction from Standard Chartered UPI alert")
            print("  - Mark Caratlane debit as reimbursed (excludes_from_spending=True, needs_review=False)")
            print("  - Classify 55,000 INR credit as Transfers -> Ruheena (is_transfer=True, excludes_from_spending=True, needs_review=False)")
            print("Run with --apply to commit.")
            return

        print("\nApplying updates...")
        tx.excludes_from_spending = True
        tx.needs_review = False
        tx.user_verified = True

        email.parse_status = "parsed"
        email.parse_error = None

        # Reconcile Ruheena credit
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

        session.commit()
        print("Successfully ingested 55,000 INR Caratlane debit and reconciled with Ruheena credit.")


if __name__ == "__main__":
    main()
