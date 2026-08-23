"""API routes for Ledger Intelligence: Deduplication, Anomalies & Statement Reconciliation."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from mymonee.api.deps import db_session
from mymonee.services.anomalies import detect_spending_anomalies
from mymonee.services.deduplication import (
    find_duplicate_candidates,
    merge_duplicate_transactions,
    unmark_duplicate_transaction,
)

router = APIRouter(prefix="/api/intelligence", tags=["intelligence"])


class MergeDuplicateBody(BaseModel):
    primary_id: str
    duplicate_id: str


class UnmarkDuplicateBody(BaseModel):
    transaction_id: str


@router.get("/duplicates")
def list_duplicates(
    lookback_days: int = Query(default=90, ge=1, le=365),
    session: Session = Depends(db_session),
) -> list[dict[str, Any]]:
    candidates = find_duplicate_candidates(session, lookback_days=lookback_days)
    return [
        {
            "primary_id": c.primary_id,
            "duplicate_id": c.duplicate_id,
            "confidence": c.confidence,
            "reason": c.reason,
            "amount": c.amount,
            "currency": c.currency,
            "primary_merchant": c.primary_merchant,
            "duplicate_merchant": c.duplicate_merchant,
            "primary_date": c.primary_date,
            "duplicate_date": c.duplicate_date,
            "primary_source": c.primary_source,
            "duplicate_source": c.duplicate_source,
            "time_diff_seconds": c.time_diff_seconds,
        }
        for c in candidates
    ]


@router.post("/duplicates/merge")
def merge_duplicate(
    body: MergeDuplicateBody,
    session: Session = Depends(db_session),
) -> dict[str, Any]:
    try:
        return merge_duplicate_transactions(session, body.primary_id, body.duplicate_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/duplicates/unmark")
def unmark_duplicate(
    body: UnmarkDuplicateBody,
    session: Session = Depends(db_session),
) -> dict[str, Any]:
    try:
        return unmark_duplicate_transaction(session, body.transaction_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/anomalies")
def list_anomalies(
    lookback_days: int = Query(default=60, ge=1, le=180),
    session: Session = Depends(db_session),
) -> list[dict[str, Any]]:
    alerts = detect_spending_anomalies(session, lookback_days=lookback_days)
    return [
        {
            "id": a.id,
            "anomaly_type": a.anomaly_type,
            "severity": a.severity,
            "title": a.title,
            "description": a.description,
            "amount": a.amount,
            "currency": a.currency,
            "transaction_id": a.transaction_id,
            "date": a.date,
            "merchant": a.merchant,
            "category": a.category,
            "metadata": a.metadata,
        }
        for a in alerts
    ]
