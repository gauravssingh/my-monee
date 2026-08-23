from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from mymonee.api.deps import db_session
from mymonee.services.data_issues import (
    list_data_issues,
    resolve_data_issues_bulk,
    serialize_issue,
    summarize_data_issues,
)

router = APIRouter(prefix="/api/data-issues", tags=["data-issues"])


class ResolveBulkBody(BaseModel):
    issue_ids: list[str] = Field(min_length=1)
    status: str = Field(default="resolved", pattern="^(resolved|dismissed|open)$")
    resolved_note: str | None = None


@router.get("")
def get_data_issues(
    session: Session = Depends(db_session),
    status: str | None = Query(None, pattern="^(open|resolved|dismissed)$"),
    issue_type: str | None = None,
    source: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    return list_data_issues(
        session,
        status=status,
        issue_type=issue_type,
        source=source,
        limit=limit,
        offset=offset,
    )


@router.get("/summary")
def get_data_issues_summary(
    session: Session = Depends(db_session),
    status: str | None = Query("open", pattern="^(open|resolved|dismissed)$"),
) -> dict[str, Any]:
    return {"groups": summarize_data_issues(session, status=status)}


@router.post("/resolve-bulk")
def post_resolve_bulk(
    body: ResolveBulkBody,
    session: Session = Depends(db_session),
) -> dict[str, Any]:
    rows = resolve_data_issues_bulk(
        session,
        issue_ids=body.issue_ids,
        status=body.status,
        resolved_note=body.resolved_note,
    )
    return {"updated": len(rows), "items": [serialize_issue(row) for row in rows]}
