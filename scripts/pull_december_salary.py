"""Pull December 2025 salary email from Gmail and ingest into ledger.

Usage:
    python scripts/pull_december_salary.py --dry-run
    python scripts/pull_december_salary.py --apply
"""

from __future__ import annotations

import argparse
import sys
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
from mymonee.ingestion.gmail.client import GmailApiSource
from mymonee.parsers.axis import AxisBankParser
from mymonee.parsers.base import EmailContext
from mymonee.services.dashboard import get_overview, income_for_pay_period


def main() -> None:
    parser = argparse.ArgumentParser(description="Pull and ingest December salary email from Gmail")
    parser.add_argument("--apply", action="store_true", help="Apply changes to database")
    parser.add_argument("--dry-run", action="store_true", help="Dry run without committing changes")
    args = parser.parse_args()

    if not args.apply and not args.dry_run:
        print("Please specify either --dry-run or --apply")
        sys.exit(1)

    settings = get_settings()
    engine = init_engine(settings)
    print(f"Connecting to database: {settings.database_path()}")

    gmail_src = GmailApiSource(settings)
    msg_id = "19b719d38a50251d"
    print(f"Fetching message {msg_id} from Gmail...")
    msg = gmail_src.get_message(msg_id)

    print(f"Fetched: {msg.subject} from {msg.sender} on {msg.received_at}")

    # Parse with AxisParser
    ctx = EmailContext(
        message_id=msg.id,
        thread_id=msg.thread_id,
        sender=msg.sender or "",
        subject=msg.subject or "",
        received_at=msg.received_at,
        body_text=msg.body_text,
        body_html=msg.body_html,
    )
    axis_parser = AxisBankParser()
    parsed_txs = axis_parser.parse(ctx)
    print(f"Parsed {len(parsed_txs)} transaction(s) from email:")
    for pt in parsed_txs:
        print(f"  - Date: {pt.transaction_date} | Amount: {pt.amount} {pt.currency} | Type: {pt.transaction_type} | Merchant: {pt.merchant_raw} | Extra: {pt.extra}")

    if not parsed_txs:
        print("Error: AxisParser could not parse transaction from email.")
        sys.exit(1)

    with Session(engine) as session:
        # Find Income -> Salary category and subcategory
        income_cat = session.scalar(select(Category).where(Category.slug == "income"))
        salary_sub = session.scalar(
            select(Subcategory).where(
                Subcategory.category_id == income_cat.id,
                Subcategory.slug == "salary",
            )
        )

        pt = parsed_txs[0]

        # Check if email already exists
        db_email = session.get(Email, msg.id)
        if not db_email:
            db_email = Email(
                id=msg.id,
                thread_id=msg.thread_id,
                sender=msg.sender,
                subject=msg.subject,
                snippet=msg.snippet,
                received_at=msg.received_at,
                label_ids_json=msg.label_ids,
                parse_status="parsed",
                body_text=msg.body_text,
                body_html=msg.body_html,
            )
            session.add(db_email)

        # Check if transaction already exists
        db_tx = session.scalar(select(Transaction).where(Transaction.source_email_id == msg.id))
        if not db_tx:
            db_tx = Transaction(
                id=new_id(),
                source_email_id=msg.id,
                account=pt.account or "Axis Bank",
                transaction_date=pt.transaction_date,
                amount=Decimal(str(pt.amount)),
                currency=pt.currency,
                direction=pt.direction,
                transaction_type="income",
                merchant_raw=pt.merchant_raw or "Salary",
                merchant_normalized="Salary",
                description=pt.description,
                category_id=income_cat.id,
                subcategory_id=salary_sub.id,
                classification_confidence=1.0,
                classification_source="rule",
                classification_signals={"rule": "axis_salary", "channel_ref": "NEFT/CHASH00009051105/Sala"},
                user_verified=True,
                needs_review=False,
                is_transfer=False,
                is_refund=False,
                excludes_from_spending=False,
            )
            session.add(db_tx)
        else:
            db_tx.category_id = income_cat.id
            db_tx.subcategory_id = salary_sub.id
            db_tx.transaction_type = "income"
            db_tx.merchant_normalized = "Salary"
            db_tx.needs_review = False
            db_tx.user_verified = True

        if args.dry_run:
            print("\n[DRY RUN] Would ingest December 31, 2025 Salary (265,681.00 INR) into Income -> Salary.")
            print("Run with --apply to commit.")
            return

        session.commit()
        print("\nSuccessfully ingested December salary email and created transaction!")

        # Verify January 2026 income
        jan_income = income_for_pay_period(session, 2026, 1)
        print(f"Verified January 2026 Pay-Period Income: {jan_income:,.2f} INR")


if __name__ == "__main__":
    main()
