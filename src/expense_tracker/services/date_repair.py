"""Repair transaction dates corrupted by dateutil dayfirst+ISO bug."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from expense_tracker.db.models import Email, Transaction, utcnow
from expense_tracker.parsers.extract import dates_look_day_month_swapped

logger = logging.getLogger(__name__)


def repair_swapped_transaction_dates(session: Session) -> int:
    """
    Fix rows where transaction_date is email.received_at with day/month swapped.

    Caused by parsing ISO dates (YYYY-MM-DD) with dayfirst=True.
    """
    rows = session.execute(
        select(Transaction, Email)
        .join(Email, Email.id == Transaction.source_email_id)
        .where(Transaction.source_email_id.is_not(None))
        .where(Email.received_at.is_not(None))
    ).all()

    fixed = 0
    for tx, email in rows:
        assert email.received_at is not None
        if dates_look_day_month_swapped(tx.transaction_date, email.received_at):
            logger.info(
                "Repairing date %s → %s for tx %s (%s)",
                tx.transaction_date.date(),
                email.received_at.date(),
                tx.id,
                tx.description or tx.merchant_raw,
            )
            # Keep received time-of-day; date from email is the ground truth here
            tx.transaction_date = email.received_at
            tx.updated_at = utcnow()
            fixed += 1
    return fixed
