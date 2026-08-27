"""Analytics API routes."""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from mymonee.analytics.category import get_category_analytics
from mymonee.api.deps import db_session

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/category/{category_id}")
def get_category_deep_dive(
    category_id: str,
    range: str = Query("6m", alias="range", description="Range window: 1m, 3m, 6m, 12m, ytd"),
    year: int | None = Query(None, description="Anchor year for calculation"),
    month: int | None = Query(None, ge=1, le=12, description="Anchor month for calculation"),
    session: Session = Depends(db_session),
) -> dict[str, Any]:
    """Retrieve deep dive metrics, multi-month subcategory trends, top counterparties, and insights for a category."""
    return get_category_analytics(
        session,
        category_id=category_id,
        range_str=range,
        year=year,
        month=month,
    )
