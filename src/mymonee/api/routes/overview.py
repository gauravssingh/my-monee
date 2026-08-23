from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from mymonee.api.deps import db_session
from mymonee.services.dashboard import (
    financial_trends,
    get_overview,
    income_trend,
    spending_by_category,
)

router = APIRouter(prefix="/api/overview", tags=["overview"])


@router.get("")
def overview(
    year: int | None = None,
    month: int | None = None,
    session: Session = Depends(db_session)
) -> dict[str, Any]:
    return get_overview(session, year=year, month=month)


@router.get("/trends")
def financial_trends_route(
    months: int = 6,
    year: int | None = None,
    month: int | None = None,
    session: Session = Depends(db_session),
) -> dict[str, Any]:
    return financial_trends(session, months=months, year=year, month=month)


@router.get("/income-trend")
def income_trend_route(
    months: int = 6,
    session: Session = Depends(db_session),
) -> dict[str, Any]:
    return income_trend(session, months=months)


@router.get("/by-category")
def by_category(
    year: int | None = None,
    month: int | None = None,
    session: Session = Depends(db_session)
) -> dict[str, Any]:
    return {"items": spending_by_category(session, year=year, month=month)}
