"""Onboarding API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from expense_tracker.api.deps import db_session
from expense_tracker.services.onboarding import (
    complete_onboarding,
    discover_onboarding_entities,
    get_onboarding_status,
    reset_onboarding,
)

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


class CompleteOnboardingBody(BaseModel):
    primary_salary: dict[str, Any] | None = None
    recurring_items: list[dict[str, Any]] = []


@router.get("/status")
def get_status_route(session: Session = Depends(db_session)) -> dict[str, Any]:
    return get_onboarding_status(session)


@router.get("/discover")
def get_discover_route(session: Session = Depends(db_session)) -> dict[str, Any]:
    return discover_onboarding_entities(session)


@router.post("/complete")
def post_complete_route(
    body: CompleteOnboardingBody,
    session: Session = Depends(db_session),
) -> dict[str, Any]:
    return complete_onboarding(session, body.model_dump())


@router.post("/reset")
def post_reset_route(session: Session = Depends(db_session)) -> dict[str, Any]:
    return reset_onboarding(session)
