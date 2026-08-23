"""Ledger transaction reconciliation: refund pairing and cross-account transfer matching."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from expense_tracker.db.models import (
    Transaction,
    TransactionLink,
    utcnow,
)
from expense_tracker.domain.enums import TransactionType

logger = logging.getLogger(__name__)


def pair_refunds(
    session: Session,
    *,
    lookback_days: int = 60,
) -> list[TransactionLink]:
    """Pair refund credit transactions with their original purchase debit transactions.

    Rules:
    1. A refund is a credit transaction on the same merchant where refund amount <= original debit amount.
    2. Date of refund is on or after the original debit, within `lookback_days`.
    3. When paired, creates a TransactionLink(kind="refund_of"), flags `is_refund=True`,
       and ensures the refund offsets spending without inflating income.
    """
    # Fetch existing refund links to avoid duplicates
    existing_links = session.scalars(
        select(TransactionLink).where(TransactionLink.kind == "refund_of")
    ).all()
    paired_refund_ids = {link.from_transaction_id for link in existing_links}

    # Identify candidate refund credits:
    # 1) Already marked is_refund
    # 2) Direction is credit and description / merchant indicates refund/cashback/reversal
    stmt = (
        select(Transaction)
        .where(
            Transaction.direction == "credit",
            Transaction.id.notin_(paired_refund_ids) if paired_refund_ids else True,
            or_(
                Transaction.is_refund == True,
                Transaction.description.ilike("%refund%"),
                Transaction.description.ilike("%cashback%"),
                Transaction.description.ilike("%reversal%"),
                Transaction.merchant_raw.ilike("%refund%"),
            ),
        )
        .order_by(Transaction.transaction_date.asc())
    )
    refund_candidates = session.scalars(stmt).all()

    created_links: list[TransactionLink] = []

    for ref in refund_candidates:
        ref_amt = float(ref.amount)
        ref_merchant = (ref.merchant_normalized or ref.merchant_raw or "").strip().lower()
        earliest_date = ref.transaction_date - timedelta(days=lookback_days)

        # Look for matching debit purchase with same merchant
        debit_candidates = session.scalars(
            select(Transaction)
            .where(
                Transaction.direction == "debit",
                Transaction.transaction_date >= earliest_date,
                Transaction.transaction_date <= ref.transaction_date,
                Transaction.amount >= ref_amt - 0.05,
            )
            .order_by(Transaction.transaction_date.desc())
        ).all()

        best_match: Transaction | None = None
        for debit in debit_candidates:
            deb_merchant = (debit.merchant_normalized or debit.merchant_raw or "").strip().lower()
            if not ref_merchant or not deb_merchant:
                continue
            if ref_merchant in deb_merchant or deb_merchant in ref_merchant:
                best_match = debit
                break

        # Fallback: check matching reference numbers if merchant is ambiguous
        if not best_match and ref.reference_number:
            for debit in debit_candidates:
                if debit.reference_number and debit.reference_number.strip() == ref.reference_number.strip():
                    best_match = debit
                    break

        if best_match:
            link = TransactionLink(
                from_transaction_id=ref.id,
                to_transaction_id=best_match.id,
                kind="refund_of",
                confidence=1.0 if abs(float(best_match.amount) - ref_amt) < 0.05 else 0.85,
                notes=f"Paired refund of ₹{ref_amt:,.2f} with original purchase ₹{float(best_match.amount):,.2f} on {best_match.transaction_date.strftime('%Y-%m-%d')}",
            )
            session.add(link)
            ref.is_refund = True
            ref.excludes_from_spending = True
            ref.transaction_type = TransactionType.REFUND.value if hasattr(TransactionType, "REFUND") else "refund"
            ref.updated_at = utcnow()
            created_links.append(link)
            logger.info("Paired refund %s (₹%s) -> original tx %s", ref.id, ref_amt, best_match.id)

    if created_links:
        session.flush()
    return created_links


def pair_cross_account_transfers(
    session: Session,
    *,
    window_days: int = 4,
) -> list[TransactionLink]:
    """Pair bank debit payments with credit card statement/email credit entries.

    Example:
    Bank Debit (Axis Savings -₹25,000, narration='Credit Card Payment')
      <->
    Credit Card Payment Credit (Scapia CC +₹25,000, narration='Payment Received')

    Creates TransactionLink(kind="transfer_to"), marks both as transfer, and ensures
    neither double-counts as an expense.
    """
    existing_links = session.scalars(
        select(TransactionLink).where(TransactionLink.kind == "transfer_to")
    ).all()
    paired_tx_ids = {link.from_transaction_id for link in existing_links} | {
        link.to_transaction_id for link in existing_links
    }

    # Find candidate bank debit payments
    stmt_debits = (
        select(Transaction)
        .where(
            Transaction.direction == "debit",
            Transaction.id.notin_(paired_tx_ids) if paired_tx_ids else True,
            or_(
                Transaction.is_transfer == True,
                Transaction.description.ilike("%credit card%"),
                Transaction.description.ilike("%card payment%"),
                Transaction.description.ilike("%cc payment%"),
                Transaction.description.ilike("%billdesk%"),
                Transaction.description.ilike("%cred%"),
                Transaction.merchant_raw.ilike("%credit card%"),
                Transaction.merchant_raw.ilike("%cred%"),
            ),
        )
        .order_by(Transaction.transaction_date.asc())
    )
    debit_candidates = session.scalars(stmt_debits).all()

    created_links: list[TransactionLink] = []

    for deb in debit_candidates:
        deb_amt = float(deb.amount)
        min_date = deb.transaction_date - timedelta(days=1)
        max_date = deb.transaction_date + timedelta(days=window_days)

        # Look for matching credit on a credit card or transfer recipient account
        stmt_credits = (
            select(Transaction)
            .where(
                Transaction.direction == "credit",
                Transaction.id.notin_(paired_tx_ids) if paired_tx_ids else True,
                Transaction.transaction_date >= min_date,
                Transaction.transaction_date <= max_date,
            )
            .order_by(Transaction.transaction_date.asc())
        )
        credit_candidates = session.scalars(stmt_credits).all()

        best_credit: Transaction | None = None
        for cred in credit_candidates:
            if abs(float(cred.amount) - deb_amt) < 0.50:
                best_credit = cred
                break

        if best_credit:
            link = TransactionLink(
                from_transaction_id=deb.id,
                to_transaction_id=best_credit.id,
                kind="transfer_to",
                confidence=0.95,
                notes=f"Matched transfer of ₹{deb_amt:,.2f} between bank debit and credit receipt",
            )
            session.add(link)
            paired_tx_ids.add(deb.id)
            paired_tx_ids.add(best_credit.id)

            deb.is_transfer = True
            deb.excludes_from_spending = True
            deb.transaction_type = TransactionType.TRANSFER.value

            best_credit.is_transfer = True
            best_credit.excludes_from_spending = True
            best_credit.transaction_type = TransactionType.TRANSFER.value

            deb.updated_at = utcnow()
            best_credit.updated_at = utcnow()
            created_links.append(link)
            logger.info("Paired cross-account transfer %s -> %s (₹%s)", deb.id, best_credit.id, deb_amt)

    if created_links:
        session.flush()
    return created_links


def run_full_reconciliation(session: Session) -> dict[str, Any]:
    """Execute all reconciliation routines across the ledger."""
    refund_links = pair_refunds(session)
    transfer_links = pair_cross_account_transfers(session)
    session.commit()
    return {
        "refunds_paired": len(refund_links),
        "transfers_paired": len(transfer_links),
        "total_links_created": len(refund_links) + len(transfer_links),
    }
