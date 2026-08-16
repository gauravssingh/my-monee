"""Identify and flag non-transaction emails/alerts in SQLite ledger."""

from __future__ import annotations

import argparse
import re
import warnings
from bs4 import XMLParsedAsHTMLWarning
from sqlalchemy import select
from sqlalchemy.orm import Session

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

from expense_tracker.db.session import get_session_factory
from expense_tracker.db.models import Transaction, Email, DataIssueFlag, new_id, utcnow
from expense_tracker.parsers.extract import html_to_text


NON_TX_PATTERNS = [
    # Declined alerts
    (re.compile(r"\bdeclined\b|transaction attempt.{0,100}declined|has been declined|payment declined", re.I), "Declined payment attempt"),
    # Payment failure intimations & loan payment requests
    (re.compile(r"could not realise|payment request intimation|non-realisation of your payment|we refer to your payment", re.I), "Payment failure / loan intimation notice"),
    # Circulars, insurance updates, and building notices
    (re.compile(r"move in move out|notice - maintenance payment — bank transfer|what the budget means for financial markets|claim status update for your claim no", re.I), "Community circular / insurance claim update without transaction"),
    # Delivery notices without payment charge
    (re.compile(r"out for delivery|rate your amazon fresh delivery|order is out for delivery", re.I), "Delivery arrival notice (separate from payment charge)"),
    # Promotional emails and marketing offers / webinars
    (re.compile(r"unlock zype loan|dhurandhar cashback|live webinar|how zenoti simplifies|see same-day tips in action|national day plans|2 days to reduce your card bill|plan rs \d+.*expired for jio|current plan rs \d+.*is about to expire|first recharge successful", re.I), "Marketing / promotional notification"),
    # Title company info requests
    (re.compile(r"arch city title|information requested from arch city|only \d+ days left to complete your information|today is the last day to complete your information", re.I), "Information request notice without transaction"),
    # Account statement PDF notices / newsletters
    (re.compile(r"your axis rewards credit card ending xx51 - [a-z]+ 2026|axis bank statement : money quotient", re.I), "Monthly statement notice / newsletter"),
    # AutoPay advance reminder (future scheduled, not yet debited)
    (re.compile(r"your autopay will be debited as scheduled|auto-debit will be scheduled", re.I), "AutoPay advance schedule notice"),
    # iCloud advance renewal reminder
    (re.compile(r"you will be charged for your icloud\+ plan in \d+ days", re.I), "Advance billing reminder"),
]


def identify_non_transactions(session: Session) -> list[tuple[Transaction, str, str]]:
    txs = session.scalars(
        select(Transaction).where(
            Transaction.transaction_type != "not_a_transaction"
        )
    ).all()

    flag_candidates = []

    for tx in txs:
        email = session.get(Email, tx.source_email_id) if tx.source_email_id else None
        subj = email.subject if email else ""
        body = html_to_text(email.body_html or email.body_text or "")[:800] if email else ""
        desc = tx.description or ""
        raw_m = tx.merchant_raw or ""
        blob = f"{desc} {subj} {body} {raw_m}"

        for pattern, reason in NON_TX_PATTERNS:
            if pattern.search(blob):
                flag_candidates.append((tx, reason, subj))
                break

    return flag_candidates


def flag_non_transactions(*, apply: bool = False) -> None:
    SessionLocal = get_session_factory()
    with SessionLocal() as session:
        candidates = identify_non_transactions(session)
        print(f"Total Non-Transaction Candidates Found: {len(candidates)}\n")

        # Group by reason for summary
        by_reason: dict[str, list[tuple[Transaction, str]]] = {}
        for tx, reason, subj in candidates:
            by_reason.setdefault(reason, []).append((tx, subj))

        for reason, items in by_reason.items():
            print(f"[{reason}] — {len(items)} items:")
            for tx, subj in items[:3]:
                print(f"   - Tx {tx.id[:8]} | ₹{tx.amount:8.2f} | {tx.transaction_date.strftime('%Y-%m-%d')} | Subj: {subj[:60]}")
            if len(items) > 3:
                print(f"     ... and {len(items) - 3} more")
            print()

        if apply:
            flagged_count = 0
            for tx, reason, subj in candidates:
                # 1. Update Transaction fields
                tx.transaction_type = "not_a_transaction"
                tx.excludes_from_spending = True
                tx.needs_review = False
                tx.merchant_entity_id = None

                # 2. Check if DataIssueFlag already exists
                existing_flag = session.scalar(
                    select(DataIssueFlag).where(
                        DataIssueFlag.transaction_id == tx.id,
                        DataIssueFlag.issue_type == "not_a_transaction",
                    ).limit(1)
                )
                if not existing_flag:
                    flag = DataIssueFlag(
                        id=new_id(),
                        transaction_id=tx.id,
                        issue_type="not_a_transaction",
                        note=f"Automated classification: {reason}",
                        status="resolved",
                        resolved_at=utcnow(),
                        resolved_note=reason,
                        source="ai_audit",
                        merchant_normalized=tx.merchant_normalized,
                    )
                    session.add(flag)
                flagged_count += 1

            session.commit()
            print(f"Successfully flagged and excluded {flagged_count} non-transaction emails from spending and ledger.")
        else:
            print(f"[DRY-RUN] Pass --apply to flag and exclude these {len(candidates)} records.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Flag non-transaction emails.")
    parser.add_argument("--apply", action="store_true", help="Apply flags in database.")
    args = parser.parse_args()
    flag_non_transactions(apply=args.apply)
