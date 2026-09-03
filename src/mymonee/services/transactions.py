"""Transaction list / filter helpers."""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session, joinedload

from mymonee.db.models import (
    Category,
    ClassificationCorrection,
    DataIssueFlag,
    Email,
    Subcategory,
    Transaction,
    utcnow,
)

logger = logging.getLogger(__name__)
from mymonee.domain.enums import DataIssueStatus, EmailParseStatus, TransactionType
from mymonee.ingestion.gmail.links import gmail_web_url
from mymonee.services.ledger import sync_transaction_postings


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def serialize_transaction(tx: Transaction) -> dict[str, Any]:
    return {
        "id": tx.id,
        "source": tx.source,
        "source_email_id": tx.source_email_id,
        "source_thread_id": tx.source_thread_id,
        "gmail_url": gmail_web_url(
            thread_id=tx.source_thread_id,
            message_id=tx.source_email_id,
        ),
        "transaction_date": tx.transaction_date.isoformat() if tx.transaction_date else None,
        "posted_date": tx.posted_date.isoformat() if tx.posted_date else None,
        "amount": _as_float(tx.amount),
        "currency": tx.currency,
        "direction": tx.direction,
        "transaction_type": tx.transaction_type,
        "merchant_raw": tx.merchant_raw,
        "merchant_normalized": tx.merchant_normalized,
        "payment_method": tx.payment_method,
        "account": tx.account,
        "card": tx.card,
        "upi_id": tx.upi_id,
        "reference_number": tx.reference_number,
        "description": tx.description,
        "category_id": tx.category_id,
        "subcategory_id": tx.subcategory_id,
        "category": tx.category.name if tx.category else None,
        "subcategory": tx.subcategory.name if tx.subcategory else None,
        "classification_confidence": tx.classification_confidence,
        "classification_source": tx.classification_source,
        "user_verified": tx.user_verified,
        "is_duplicate": tx.is_duplicate,
        "is_refund": tx.is_refund,
        "is_transfer": tx.is_transfer,
        "excludes_from_spending": tx.excludes_from_spending,
        "needs_review": tx.needs_review,
        "classification_signals": tx.classification_signals or {},
        "created_at": tx.created_at.isoformat() if tx.created_at else None,
    }


SORTABLE_COLUMNS = {"date", "amount", "merchant", "category", "source", "status"}


def _apply_sort(stmt: Any, sort_by: str | None, sort_dir: str | None) -> Any:
    sort_by = sort_by if sort_by in SORTABLE_COLUMNS else "date"
    descending = sort_dir != "asc"

    if sort_by == "amount":
        column = Transaction.amount
    elif sort_by == "merchant":
        column = func.coalesce(Transaction.merchant_normalized, Transaction.merchant_raw)
    elif sort_by == "category":
        stmt = stmt.outerjoin(Category, Transaction.category_id == Category.id)
        column = Category.name
    elif sort_by == "source":
        column = Transaction.classification_source
    elif sort_by == "status":
        column = Transaction.needs_review
    else:
        column = Transaction.transaction_date

    primary = column.desc() if descending else column.asc()
    # Stable tiebreak so pagination doesn't reshuffle rows that share a sort value.
    return stmt.order_by(primary, Transaction.id.asc())


def list_transactions(
    session: Session,
    *,
    limit: int = 50,
    offset: int = 0,
    needs_review: bool | None = None,
    direction: str | None = None,
    q: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    sort_by: str | None = None,
    sort_dir: str | None = None,
    merchant_id: str | None = None,
    account: str | None = None,
    status: str | None = None,
    category_id: str | None = None,
    category_ids: list[str] | None = None,
    subcategory_id: str | None = None,
) -> dict[str, Any]:
    stmt = (
        select(Transaction)
        .options(joinedload(Transaction.category), joinedload(Transaction.subcategory))
        .where(Transaction.transaction_type != "not_a_transaction")
        .where(
            ~exists(
                select(DataIssueFlag.id).where(
                    DataIssueFlag.transaction_id == Transaction.id,
                    DataIssueFlag.status == DataIssueStatus.OPEN,
                )
            )
        )
    )
    if needs_review is not None:
        stmt = stmt.where(Transaction.needs_review.is_(needs_review))
    if status:
        if status.lower() in ("review", "needs_review", "needs review"):
            stmt = stmt.where(Transaction.needs_review.is_(True))
        elif status.lower() in ("ok", "verified"):
            stmt = stmt.where(Transaction.needs_review.is_(False))
    if direction in {"debit", "credit"}:
        stmt = stmt.where(Transaction.direction == direction)
    if account:
        if account.lower() in ("unlinked", "unknown", "none"):
            stmt = stmt.where(Transaction.account.is_(None) | (Transaction.account == ""))
        else:
            stmt = stmt.where(Transaction.account.ilike(f"%{account}%"))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            (Transaction.merchant_raw.ilike(like))
            | (Transaction.merchant_normalized.ilike(like))
            | (Transaction.description.ilike(like))
            | (Transaction.account.ilike(like))
        )
    if date_from:
        start = datetime.combine(date_from, time.min, tzinfo=timezone.utc)
        stmt = stmt.where(Transaction.transaction_date >= start)
    if date_to:
        end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=timezone.utc)
        stmt = stmt.where(Transaction.transaction_date < end)
    if merchant_id:
        stmt = (
            stmt.where(Transaction.merchant_entity_id == merchant_id)
            .where(Transaction.is_transfer.is_(False))
            .where(Transaction.excludes_from_spending.is_(False))
            .where(Transaction.transaction_type.notin_(["not_a_transaction", "declined", "transfer"]))
        )

    cats = list(category_ids or [])
    if category_id:
        if "," in category_id:
            cats.extend([c.strip() for c in category_id.split(",") if c.strip()])
        else:
            cats.append(category_id)

    if cats:
        has_uncat = "uncategorized" in cats
        specific_cats = [c for c in cats if c != "uncategorized"]
        resolved_category_ids: set[str] = set()

        if specific_cats:
            matched_db_ids = session.scalars(
                select(Category.id).where(
                    (Category.id.in_(specific_cats))
                    | (func.lower(Category.slug).in_([c.lower() for c in specific_cats]))
                    | (func.lower(Category.name).in_([c.lower() for c in specific_cats]))
                )
            ).all()
            resolved_category_ids.update(matched_db_ids)
            if not matched_db_ids:
                resolved_category_ids.update(specific_cats)

        if has_uncat and resolved_category_ids:
            stmt = stmt.where(
                (Transaction.category_id.is_(None)) | (Transaction.category_id.in_(resolved_category_ids))
            )
        elif has_uncat:
            stmt = stmt.where(Transaction.category_id.is_(None))
        elif resolved_category_ids:
            if len(resolved_category_ids) == 1 and subcategory_id:
                single_cat_id = next(iter(resolved_category_ids))
                subcat_id_resolved = session.scalar(
                    select(Subcategory.id).where(
                        (Subcategory.id == subcategory_id)
                        | (
                            (Subcategory.category_id == single_cat_id)
                            & (
                                (func.lower(Subcategory.slug) == subcategory_id.lower())
                                | (func.lower(Subcategory.name) == subcategory_id.lower())
                            )
                        )
                    )
                ) or subcategory_id
                stmt = stmt.where(
                    (Transaction.category_id == single_cat_id)
                    & (Transaction.subcategory_id == subcat_id_resolved)
                )
            else:
                stmt = stmt.where(Transaction.category_id.in_(resolved_category_ids))

    base_filtered_stmt = stmt
    stmt = _apply_sort(base_filtered_stmt, sort_by, sort_dir)

    subq = base_filtered_stmt.subquery()
    total = session.scalar(select(func.count()).select_from(subq)) or 0
    total_amount = session.scalar(select(func.coalesce(func.sum(subq.c.amount), 0))) or 0
    total_debit = session.scalar(
        select(func.coalesce(func.sum(subq.c.amount), 0)).where(subq.c.direction == "debit")
    ) or 0
    total_credit = session.scalar(
        select(func.coalesce(func.sum(subq.c.amount), 0)).where(subq.c.direction == "credit")
    ) or 0

    rows = session.execute(stmt.limit(limit).offset(offset)).unique().scalars().all()
    return {
        "total": int(total),
        "total_amount": _as_float(total_amount),
        "total_debit": _as_float(total_debit),
        "total_credit": _as_float(total_credit),
        "limit": limit,
        "offset": offset,
        "items": [serialize_transaction(tx) for tx in rows],
    }


def _apply_category_side_effects(
    tx: Transaction,
    category: Category,
    subcategory: Subcategory | None,
) -> None:
    slug = category.slug
    sub_slug = subcategory.slug if subcategory else None
    if slug == "transfers" or sub_slug == "credit-card-payment":
        tx.is_transfer = True
        tx.is_refund = False
        tx.excludes_from_spending = True
        tx.merchant_entity_id = None
        if tx.transaction_type not in {"income", "refund"}:
            tx.transaction_type = "transfer"
    elif slug == "income":
        tx.is_transfer = False
        tx.excludes_from_spending = True
        if sub_slug == "refund":
            tx.is_refund = True
            tx.transaction_type = "refund"
        else:
            tx.is_refund = False
            tx.transaction_type = "income"
    else:
        tx.is_transfer = False
        if tx.direction == "debit":
            tx.excludes_from_spending = False
            if tx.transaction_type in {"transfer", "other", "unknown", "income"}:
                tx.transaction_type = "purchase"


def _record_correction(
    tx: Transaction,
    *,
    new_category_id: str | None,
    new_subcategory_id: str | None,
) -> ClassificationCorrection | None:
    """Snapshot the pre-correction label so it survives as a supervised training pair.

    Skips rows where the label isn't actually changing (e.g. re-saving the
    same category), so the history only holds real corrections.
    """
    if (
        tx.category_id == new_category_id
        and tx.subcategory_id == new_subcategory_id
        and tx.classification_source == "user"
    ):
        return None
    return ClassificationCorrection(
        transaction_id=tx.id,
        previous_category_id=tx.category_id,
        previous_subcategory_id=tx.subcategory_id,
        previous_classification_source=tx.classification_source,
        previous_classification_confidence=tx.classification_confidence,
        previous_classification_signals=dict(tx.classification_signals or {}),
        new_category_id=new_category_id,
        new_subcategory_id=new_subcategory_id,
    )


def classify_transaction(
    session: Session,
    transaction_id: str,
    *,
    category_id: str,
    subcategory_id: str | None = None,
    create_rule: bool = True,
    apply_to_past: bool = False,
) -> Transaction:
    tx = session.get(Transaction, transaction_id)
    if tx is None:
        raise HTTPException(status_code=404, detail="Transaction not found")

    category = session.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=400, detail="Category not found")

    subcategory: Subcategory | None = None
    if subcategory_id:
        subcategory = session.get(Subcategory, subcategory_id)
        if subcategory is None:
            raise HTTPException(status_code=400, detail="Subcategory not found")
        if subcategory.category_id != category.id:
            raise HTTPException(status_code=400, detail="Subcategory does not belong to category")

    correction = _record_correction(
        tx,
        new_category_id=category.id,
        new_subcategory_id=subcategory.id if subcategory else None,
    )
    if correction is not None:
        session.add(correction)

    tx.category_id = category.id
    tx.subcategory_id = subcategory.id if subcategory else None
    tx.user_verified = True
    tx.needs_review = False
    tx.classification_source = "user"
    tx.classification_confidence = 1.0

    signals = dict(tx.classification_signals or {})
    signals.update(
        {
            "rule": "user_correction",
            "category_slug": category.slug,
            "subcategory_slug": subcategory.slug if subcategory else None,
            "user_verified": True,
        }
    )

    # 1. Deterministic User Rule Persistence
    if create_rule:
        from mymonee.classification.rules import upsert_user_classification_rule
        rule = upsert_user_classification_rule(
            session,
            tx,
            category_id=category.id,
            subcategory_id=subcategory.id if subcategory else None,
        )
        signals.update(
            {
                "rule": "user_rule",
                "rule_id": rule.id,
                "rule_name": rule.name,
                "priority": rule.priority,
            }
        )

    tx.classification_signals = signals
    _apply_category_side_effects(tx, category, subcategory)
    sync_transaction_postings(session, tx)
    tx.updated_at = utcnow()
    
    from mymonee.services.ai import track_user_classification_feedback
    track_user_classification_feedback(
        session,
        transaction_id=tx.id,
        chosen_category_id=category.id,
        chosen_subcategory_id=subcategory.id if subcategory else None,
    )

    # 2. Optionally backfill all past unreviewed transactions for this merchant
    if apply_to_past:
        merchant_name = (tx.merchant_normalized or tx.merchant_raw or "").strip()
        if merchant_name:
            past_txs = session.scalars(
                select(Transaction).where(
                    Transaction.id != tx.id,
                    Transaction.user_verified == False,
                    or_(
                        Transaction.merchant_entity_id == tx.merchant_entity_id if tx.merchant_entity_id else False,
                        Transaction.merchant_normalized.ilike(merchant_name),
                        Transaction.merchant_raw.ilike(merchant_name),
                    ),
                )
            ).all()
            for ptx in past_txs:
                ptx.category_id = category.id
                ptx.subcategory_id = subcategory.id if subcategory else None
                ptx.user_verified = True
                ptx.needs_review = False
                ptx.classification_source = "user"
                ptx.classification_confidence = 1.0
                ptx_signals = dict(ptx.classification_signals or {})
                ptx_signals.update(signals)
                ptx.classification_signals = ptx_signals
                _apply_category_side_effects(ptx, category, subcategory)
                sync_transaction_postings(session, ptx)
                ptx.updated_at = utcnow()
            logger.info("Backfilled %d historical transactions for merchant %s", len(past_txs), merchant_name)

    session.flush()
    session.refresh(tx, attribute_names=["category", "subcategory"])
    logger.info(
        "Classified transaction %s -> %s (sub: %s, rule_created: %s)",
        tx.id,
        category.name,
        subcategory.name if subcategory else "none",
        "yes" if create_rule else "no",
    )
    return tx


def _normalize_transaction_ids(transaction_ids: list[str]) -> list[str]:
    ids = [tid.strip() for tid in transaction_ids if tid and tid.strip()]
    if not ids:
        raise HTTPException(status_code=400, detail="No transactions selected")
    if len(ids) > 200:
        raise HTTPException(status_code=400, detail="Too many transactions (max 200)")
    return ids


def classify_transactions_bulk(
    session: Session,
    *,
    transaction_ids: list[str],
    category_id: str,
    subcategory_id: str | None = None,
    create_rule: bool = True,
) -> list[Transaction]:
    ids = _normalize_transaction_ids(transaction_ids)

    # Validate category once up front
    category = session.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=400, detail="Category not found")
    if subcategory_id:
        subcategory = session.get(Subcategory, subcategory_id)
        if subcategory is None:
            raise HTTPException(status_code=400, detail="Subcategory not found")
        if subcategory.category_id != category.id:
            raise HTTPException(status_code=400, detail="Subcategory does not belong to category")

    logger.info(
        "Bulk classifying %d transactions -> category %s (sub: %s)",
        len(ids),
        category.name,
        subcategory.name if subcategory_id and subcategory else "none",
    )

    updated: list[Transaction] = []
    for tid in ids:
        updated.append(
            classify_transaction(
                session,
                tid,
                category_id=category_id,
                subcategory_id=subcategory_id,
                create_rule=create_rule,
            )
        )
    return updated


def exclude_as_non_transaction(session: Session, transaction_id: str) -> Transaction:
    """Mark a parsed row as not a real transaction email and drop it from spending/review."""
    tx = session.get(Transaction, transaction_id)
    if tx is None:
        raise HTTPException(status_code=404, detail="Transaction not found")

    correction = _record_correction(tx, new_category_id=None, new_subcategory_id=None)
    if correction is not None:
        session.add(correction)

    tx.category_id = None
    tx.subcategory_id = None
    tx.transaction_type = TransactionType.NOT_A_TRANSACTION
    tx.is_transfer = False
    tx.is_refund = False
    tx.excludes_from_spending = True
    tx.needs_review = False
    tx.user_verified = True
    tx.classification_source = "user"
    tx.classification_confidence = 1.0
    signals = dict(tx.classification_signals or {})
    signals.update(
        {
            "rule": "not_a_transaction_email",
            "category_slug": None,
            "subcategory_slug": None,
        }
    )
    tx.classification_signals = signals
    extra = dict(tx.extra_json or {})
    extra["not_a_transaction"] = True
    tx.extra_json = extra
    sync_transaction_postings(session, tx)
    tx.updated_at = utcnow()

    if tx.source_email_id:
        email = session.get(Email, tx.source_email_id)
        if email is not None:
            email.parse_status = EmailParseStatus.SKIPPED
            email.parse_error = "Marked by user as not a transaction email"
            email.updated_at = utcnow()

    session.flush()
    session.refresh(tx, attribute_names=["category", "subcategory"])
    logger.info("Excluded transaction %s as non-transaction email", tx.id)
    return tx


def exclude_transactions_bulk(session: Session, *, transaction_ids: list[str]) -> list[Transaction]:
    ids = _normalize_transaction_ids(transaction_ids)
    return [exclude_as_non_transaction(session, tid) for tid in ids]


def mark_reimbursed(session: Session, transaction_id: str) -> Transaction:
    """Mark a genuine transaction as paid on someone else's behalf and reimbursed.

    Unlike `exclude_as_non_transaction`, the row is real money movement and stays
    in the ledger for the record — it's just excluded from spending totals and
    cleared from Needs Review. Category is left untouched (no label actually
    changed), so this doesn't write a classification_corrections row.
    """
    tx = session.get(Transaction, transaction_id)
    if tx is None:
        raise HTTPException(status_code=404, detail="Transaction not found")

    tx.transaction_type = TransactionType.REIMBURSED
    tx.is_transfer = False
    tx.is_refund = False
    tx.excludes_from_spending = True
    tx.needs_review = False
    tx.user_verified = True
    tx.classification_source = "user"
    tx.classification_confidence = 1.0
    signals = dict(tx.classification_signals or {})
    signals.update({"rule": "reimbursed_by_other"})
    tx.classification_signals = signals
    tx.updated_at = utcnow()
    session.flush()
    session.refresh(tx, attribute_names=["category", "subcategory"])
    return tx


def mark_reimbursed_bulk(session: Session, *, transaction_ids: list[str]) -> list[Transaction]:
    ids = _normalize_transaction_ids(transaction_ids)
    return [mark_reimbursed(session, tid) for tid in ids]
