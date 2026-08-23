"""User-reported data-extraction issue flags.

Flagging is purely additive — it never mutates the transaction. The point is
to let a data-quality problem (wrong amount, wrong date, an email parsed as a
transaction when it isn't, ...) be recorded in a few seconds without stopping
to fix it, then triaged later in bulk once the same root cause (a parser bug
for one bank, a bad merchant match) has been found across many flags.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mymonee.db.models import DataIssueFlag, Email, Transaction, utcnow
from mymonee.domain.enums import DataIssueStatus, DataIssueType, EmailParseStatus, TransactionType

VALID_ISSUE_TYPES = {member.value for member in DataIssueType}
VALID_STATUSES = {member.value for member in DataIssueStatus}

# Whitelist of transaction fields that can be pointed at by a flag — keeps
# `reported_value` snapshots meaningful and prevents flagging internal/relationship
# attributes.
FLAGGABLE_FIELDS = {
    "amount",
    "currency",
    "direction",
    "transaction_date",
    "merchant_raw",
    "merchant_normalized",
    "description",
    "account",
    "card",
    "upi_id",
    "reference_number",
    "category_id",
}


def serialize_issue(issue: DataIssueFlag) -> dict[str, Any]:
    tx = issue.transaction
    return {
        "id": issue.id,
        "transaction_id": issue.transaction_id,
        "issue_type": issue.issue_type,
        "field_name": issue.field_name,
        "reported_value": issue.reported_value,
        "suggested_value": issue.suggested_value,
        "note": issue.note,
        "status": issue.status,
        "source": issue.source,
        "merchant_normalized": issue.merchant_normalized,
        "created_at": issue.created_at.isoformat() if issue.created_at else None,
        "resolved_at": issue.resolved_at.isoformat() if issue.resolved_at else None,
        "resolved_note": issue.resolved_note,
        "transaction": None
        if tx is None
        else {
            "id": tx.id,
            "merchant": tx.merchant_normalized or tx.merchant_raw,
            "amount": float(tx.amount) if tx.amount is not None else None,
            "currency": tx.currency,
            "transaction_date": tx.transaction_date.isoformat() if tx.transaction_date else None,
            "source_email_id": tx.source_email_id,
        },
    }


def flag_transaction_issue(
    session: Session,
    transaction_id: str,
    *,
    issue_type: str,
    field_name: str | None = None,
    suggested_value: str | None = None,
    note: str | None = None,
) -> DataIssueFlag:
    if issue_type not in VALID_ISSUE_TYPES:
        raise HTTPException(status_code=400, detail=f"Unknown issue_type: {issue_type}")
    if field_name is not None and field_name not in FLAGGABLE_FIELDS:
        raise HTTPException(status_code=400, detail=f"Unknown field_name: {field_name}")

    tx = session.get(Transaction, transaction_id)
    if tx is None:
        raise HTTPException(status_code=404, detail="Transaction not found")

    reported_value: str | None = None
    if field_name:
        value = getattr(tx, field_name)
        reported_value = None if value is None else str(value)

    issue = DataIssueFlag(
        transaction_id=tx.id,
        issue_type=issue_type,
        field_name=field_name,
        reported_value=reported_value,
        suggested_value=suggested_value,
        note=note,
        status=DataIssueStatus.OPEN,
        source=tx.source,
        merchant_normalized=tx.merchant_normalized,
    )
    session.add(issue)
    session.flush()
    session.refresh(issue, attribute_names=["transaction"])
    return issue


def _normalize_transaction_ids(transaction_ids: list[str]) -> list[str]:
    ids = [tid.strip() for tid in transaction_ids if tid and tid.strip()]
    if not ids:
        raise HTTPException(status_code=400, detail="No transactions selected")
    if len(ids) > 200:
        raise HTTPException(status_code=400, detail="Too many transactions (max 200)")
    return ids


def flag_transactions_bulk(
    session: Session,
    *,
    transaction_ids: list[str],
    issue_type: str,
    field_name: str | None = None,
    suggested_value: str | None = None,
    note: str | None = None,
) -> list[DataIssueFlag]:
    """Flag the same issue on many transactions — each still gets its own live field snapshot."""
    ids = _normalize_transaction_ids(transaction_ids)
    return [
        flag_transaction_issue(
            session,
            tid,
            issue_type=issue_type,
            field_name=field_name,
            suggested_value=suggested_value,
            note=note,
        )
        for tid in ids
    ]


def list_data_issues(
    session: Session,
    *,
    status: str | None = None,
    issue_type: str | None = None,
    source: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    stmt = select(DataIssueFlag).order_by(DataIssueFlag.created_at.desc())
    if status:
        stmt = stmt.where(DataIssueFlag.status == status)
    if issue_type:
        stmt = stmt.where(DataIssueFlag.issue_type == issue_type)
    if source:
        stmt = stmt.where(DataIssueFlag.source == source)

    total = len(session.execute(stmt).unique().scalars().all())
    rows = session.execute(stmt.limit(limit).offset(offset)).unique().scalars().all()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [serialize_issue(row) for row in rows],
    }


def summarize_data_issues(session: Session, *, status: str | None = "open") -> list[dict[str, Any]]:
    """Group flags by (issue_type, source) so a shared root cause reads as one row."""
    stmt = (
        select(
            DataIssueFlag.issue_type,
            DataIssueFlag.source,
            func.count(DataIssueFlag.id).label("count"),
            func.max(DataIssueFlag.created_at).label("latest"),
        )
        .group_by(DataIssueFlag.issue_type, DataIssueFlag.source)
        .order_by(func.count(DataIssueFlag.id).desc())
    )
    if status:
        stmt = stmt.where(DataIssueFlag.status == status)
    rows = session.execute(stmt).all()
    return [
        {
            "issue_type": row.issue_type,
            "source": row.source,
            "count": row.count,
            "latest": row.latest.isoformat() if row.latest else None,
        }
        for row in rows
    ]


def _normalize_issue_ids(issue_ids: list[str]) -> list[str]:
    ids = [iid.strip() for iid in issue_ids if iid and iid.strip()]
    if not ids:
        raise HTTPException(status_code=400, detail="No issues selected")
    if len(ids) > 500:
        raise HTTPException(status_code=400, detail="Too many issues (max 500)")
    return ids


def resolve_data_issues_bulk(
    session: Session,
    *,
    issue_ids: list[str],
    status: str = DataIssueStatus.RESOLVED,
    resolved_note: str | None = None,
) -> list[DataIssueFlag]:
    if status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Unknown status: {status}")
    ids = _normalize_issue_ids(issue_ids)

    updated: list[DataIssueFlag] = []
    for iid in ids:
        issue = session.get(DataIssueFlag, iid)
        if issue is None:
            continue
        issue.status = status
        issue.resolved_at = utcnow() if status != DataIssueStatus.OPEN else None
        if resolved_note is not None:
            issue.resolved_note = resolved_note

        # When resolving, ensure the underlying transaction reflects the confirmed status
        if status == DataIssueStatus.RESOLVED:
            tx = session.get(Transaction, issue.transaction_id)
            if tx is not None:
                if issue.issue_type == DataIssueType.NOT_A_TRANSACTION.value:
                    tx.transaction_type = TransactionType.NOT_A_TRANSACTION
                    tx.excludes_from_spending = True
                    tx.needs_review = False
                    tx.user_verified = True
                    tx.classification_source = "user"
                    tx.updated_at = utcnow()
                    if tx.source_email_id:
                        email = session.get(Email, tx.source_email_id)
                        if email is not None:
                            email.parse_status = EmailParseStatus.SKIPPED
                            email.parse_error = "Marked by user as not a transaction email"
                            email.updated_at = utcnow()
                elif issue.issue_type == DataIssueType.DUPLICATE.value:
                    tx.is_duplicate = True
                    tx.excludes_from_spending = True
                    tx.needs_review = False
                    tx.user_verified = True
                    tx.updated_at = utcnow()

        updated.append(issue)

    session.flush()
    for issue in updated:
        session.refresh(issue, attribute_names=["transaction"])
    return updated
