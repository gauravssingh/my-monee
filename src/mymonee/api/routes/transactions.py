from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from mymonee.api.deps import db_session
from mymonee.services.data_issues import (
    flag_transaction_issue,
    flag_transactions_bulk,
    serialize_issue,
)
from mymonee.services.transactions import (
    classify_transaction,
    classify_transactions_bulk,
    exclude_transactions_bulk,
    list_transactions,
    mark_reimbursed_bulk,
    serialize_transaction,
)

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


class ClassifyBody(BaseModel):
    category_id: str = Field(min_length=1)
    subcategory_id: str | None = None
    create_rule: bool = True
    apply_to_past: bool = False


class BulkClassifyBody(BaseModel):
    transaction_ids: list[str] = Field(min_length=1)
    category_id: str = Field(min_length=1)
    subcategory_id: str | None = None
    create_rule: bool = True


class ExcludeBody(BaseModel):
    transaction_ids: list[str] = Field(min_length=1)


class ReimbursedBody(BaseModel):
    transaction_ids: list[str] = Field(min_length=1)


class FlagIssueBody(BaseModel):
    issue_type: str = Field(min_length=1)
    field_name: str | None = None
    suggested_value: str | None = None
    note: str | None = None


class BulkFlagIssueBody(BaseModel):
    transaction_ids: list[str] = Field(min_length=1)
    issue_type: str = Field(min_length=1)
    field_name: str | None = None
    suggested_value: str | None = None
    note: str | None = None


@router.get("")
def get_transactions(
    session: Session = Depends(db_session),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    needs_review: bool | None = None,
    direction: str | None = Query(None, pattern="^(debit|credit)$"),
    q: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    sort_by: str | None = Query(None, pattern="^(date|amount|merchant|category|source|status)$"),
    sort_dir: str | None = Query(None, pattern="^(asc|desc)$"),
    merchant_id: str | None = None,
    account: str | None = None,
    status: str | None = None,
    category_id: str | None = None,
    category_ids: list[str] | None = Query(None),
    subcategory_id: str | None = None,
) -> dict[str, Any]:
    return list_transactions(
        session,
        limit=limit,
        offset=offset,
        needs_review=needs_review,
        direction=direction,
        q=q,
        date_from=date_from,
        date_to=date_to,
        sort_by=sort_by,
        sort_dir=sort_dir,
        merchant_id=merchant_id,
        account=account,
        status=status,
        category_id=category_id,
        category_ids=category_ids,
        subcategory_id=subcategory_id,
    )


@router.post("/sample")
def post_sample(
    session: Session = Depends(db_session),
) -> dict[str, Any]:
    from datetime import datetime, timezone
    from mymonee.db.models import Transaction, new_id
    tx = Transaction(
        id=new_id(),
        source="sample",
        transaction_date=datetime.now(timezone.utc),
        amount=500.0,
        currency="INR",
        direction="debit",
        merchant_raw="Sample Merchant",
        merchant_normalized="Sample",
        description="Sample transaction",
        needs_review=True,
    )
    session.add(tx)
    session.commit()
    session.refresh(tx)
    return serialize_transaction(tx)


@router.post("/classify-bulk")
def post_classify_bulk(
    body: BulkClassifyBody,
    session: Session = Depends(db_session),
) -> dict[str, Any]:
    rows = classify_transactions_bulk(
        session,
        transaction_ids=body.transaction_ids,
        category_id=body.category_id,
        subcategory_id=body.subcategory_id,
        create_rule=body.create_rule,
    )
    return {
        "updated": len(rows),
        "items": [serialize_transaction(tx) for tx in rows],
    }


@router.post("/exclude")
def post_exclude(
    body: ExcludeBody,
    session: Session = Depends(db_session),
) -> dict[str, Any]:
    rows = exclude_transactions_bulk(session, transaction_ids=body.transaction_ids)
    return {
        "updated": len(rows),
        "items": [serialize_transaction(tx) for tx in rows],
    }


@router.post("/reimbursed")
def post_reimbursed(
    body: ReimbursedBody,
    session: Session = Depends(db_session),
) -> dict[str, Any]:
    rows = mark_reimbursed_bulk(session, transaction_ids=body.transaction_ids)
    return {
        "updated": len(rows),
        "items": [serialize_transaction(tx) for tx in rows],
    }



@router.patch("/{transaction_id}/classify")
def patch_classify(
    transaction_id: str,
    body: ClassifyBody,
    session: Session = Depends(db_session),
) -> dict[str, Any]:
    tx = classify_transaction(
        session,
        transaction_id,
        category_id=body.category_id,
        subcategory_id=body.subcategory_id,
        create_rule=body.create_rule,
        apply_to_past=body.apply_to_past,
    )
    return serialize_transaction(tx)


@router.post("/{transaction_id}/flag-issue")
def post_flag_issue(
    transaction_id: str,
    body: FlagIssueBody,
    session: Session = Depends(db_session),
) -> dict[str, Any]:
    issue = flag_transaction_issue(
        session,
        transaction_id,
        issue_type=body.issue_type,
        field_name=body.field_name,
        suggested_value=body.suggested_value,
        note=body.note,
    )
    return serialize_issue(issue)


@router.post("/flag-issue-bulk")
def post_flag_issue_bulk(
    body: BulkFlagIssueBody,
    session: Session = Depends(db_session),
) -> dict[str, Any]:
    issues = flag_transactions_bulk(
        session,
        transaction_ids=body.transaction_ids,
        issue_type=body.issue_type,
        field_name=body.field_name,
        suggested_value=body.suggested_value,
        note=body.note,
    )
    return {"created": len(issues), "items": [serialize_issue(i) for i in issues]}


@router.post("/reconcile-all")
def post_reconcile_all(
    session: Session = Depends(db_session),
) -> dict[str, Any]:
    from mymonee.services.reconciliation import run_full_reconciliation
    return run_full_reconciliation(session)


@router.get("/{transaction_id}/links")
def get_transaction_links_route(
    transaction_id: str,
    session: Session = Depends(db_session),
) -> dict[str, Any]:
    from mymonee.db.models import TransactionLink, Transaction
    links_out = session.scalars(
        select(TransactionLink).where(TransactionLink.from_transaction_id == transaction_id)
    ).all()
    links_in = session.scalars(
        select(TransactionLink).where(TransactionLink.to_transaction_id == transaction_id)
    ).all()

    items = []
    for l in links_out:
        target = session.get(Transaction, l.to_transaction_id)
        items.append({
            "id": l.id,
            "direction": "out",
            "kind": l.kind,
            "confidence": l.confidence,
            "notes": l.notes,
            "related_transaction": serialize_transaction(target) if target else None,
        })
    for l in links_in:
        source = session.get(Transaction, l.from_transaction_id)
        items.append({
            "id": l.id,
            "direction": "in",
            "kind": l.kind,
            "confidence": l.confidence,
            "notes": l.notes,
            "related_transaction": serialize_transaction(source) if source else None,
        })

    return {"transaction_id": transaction_id, "links": items}
