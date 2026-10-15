"""Session-level integration between ledger changes and the embedding job queue.

Every ORM flush that inserts, updates, or deletes a `Transaction` — ingestion, manual and rule
classification, exclusion/reimbursement, reconciliation, deduplication, statement/EMI import, API
routes and the MCP classification tool — re-evaluates the durable embedding job for the affected
transaction. Opening or resolving a `DataIssueFlag` does the same, because it changes eligibility.

The work happens inside the same SQLite transaction as the ledger change, so job state can never
drift from the ledger. It never calls embedding-g2 and never inspects service availability: ledger
writes stay independent of the embedding service. Redundant jobs are avoided by comparing the
transaction's current content hash against the stored vector.
"""

from __future__ import annotations

import logging

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from mymonee.db.models import DataIssueFlag, Transaction, new_id
from mymonee.domain.enums import DataIssueStatus
from mymonee.services.embeddings.service import (
    _open_flag_tx_ids,
    cancel_transaction_embedding,
    enqueue_transaction_embedding,
)

logger = logging.getLogger(__name__)

# Fields whose change alters the composed embedding text (see text.transaction_embedding_text).
RELEVANT_FIELDS = (
    "amount",
    "direction",
    "currency",
    "transaction_type",
    "merchant_raw",
    "merchant_normalized",
    "description",
    "account",
    "payment_method",
    "location",
    "category_id",
    "subcategory_id",
)


def _has_relevant_change(transaction: Transaction) -> bool:
    """True when a dirty transaction changed a field that feeds the embedding text."""
    state = inspect(transaction)
    for field in RELEVANT_FIELDS:
        attribute = state.attrs.get(field)
        if attribute is not None and attribute.history.has_changes():
            return True
    return False


def _effective_open_flag_ids(session: Session, tx_ids: set[str]) -> set[str]:
    """Open-flag transaction ids after applying this flush's pending flag changes.

    The database still holds the pre-flush flag rows, so pending inserts/resolutions/deletions are
    folded in by hand; otherwise a transaction being un-flagged would look ineligible (or vice
    versa) until the next flush.
    """
    open_ids = _open_flag_tx_ids(session, tx_ids)

    for flag in session.deleted:
        if isinstance(flag, DataIssueFlag) and flag.transaction_id in tx_ids:
            open_ids.discard(flag.transaction_id)
    for flag in session.dirty:
        if not isinstance(flag, DataIssueFlag) or flag.transaction_id not in tx_ids:
            continue
        status_attr = inspect(flag).attrs.get("status")
        if (
            status_attr is not None
            and status_attr.history.has_changes()
            and str(flag.status) != DataIssueStatus.OPEN.value
        ):
            open_ids.discard(flag.transaction_id)
    for flag in session.new:
        if not isinstance(flag, DataIssueFlag):
            continue
        if str(flag.status or DataIssueStatus.OPEN.value) == DataIssueStatus.OPEN.value:
            open_ids.add(flag.transaction_id)
    return open_ids


def sync_embedding_jobs_on_flush(session: Session) -> None:
    """Bring `embedding_jobs` in line with the transactions and flags touched by this flush."""
    transactions: dict[str, Transaction] = {}

    for obj in session.new:
        if isinstance(obj, Transaction):
            # `Transaction.id` uses a client-side default applied at flush time; assign it now so
            # the queued job can reference the transaction within this same flush.
            if obj.id is None:
                obj.id = new_id()
            transactions[obj.id] = obj
    for obj in session.dirty:
        if isinstance(obj, Transaction) and _has_relevant_change(obj):
            transactions[obj.id] = obj

    deleted_ids = {obj.id for obj in session.deleted if isinstance(obj, Transaction)}
    for transaction_id in deleted_ids:
        cancel_transaction_embedding(session, transaction_id)

    touched_flag_ids = {
        obj.transaction_id
        for obj in (*session.new, *session.dirty, *session.deleted)
        if isinstance(obj, DataIssueFlag) and obj.transaction_id
    }
    for transaction_id in touched_flag_ids:
        if transaction_id in deleted_ids or transaction_id in transactions:
            continue
        transaction = session.get(Transaction, transaction_id)
        if transaction is not None:
            transactions[transaction_id] = transaction

    if not transactions:
        return

    open_ids = _effective_open_flag_ids(session, set(transactions))
    for transaction in transactions.values():
        enqueue_transaction_embedding(session, transaction, flagged_ids=open_ids)
