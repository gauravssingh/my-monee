from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from expense_tracker.api.deps import db_session
from expense_tracker.services.data_issues import (
    flag_transaction_issue,
    flag_transactions_bulk,
    serialize_issue,
)
from expense_tracker.services.transactions import (
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


class BulkClassifyBody(BaseModel):
    transaction_ids: list[str] = Field(min_length=1)
    category_id: str = Field(min_length=1)
    subcategory_id: str | None = None


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
    )


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
