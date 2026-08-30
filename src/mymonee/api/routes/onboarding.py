"""Onboarding API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from mymonee.api.deps import db_session, settings_dep
from mymonee.config import Settings
from mymonee.services.onboarding import (
    complete_onboarding,
    discover_onboarding_entities,
    fast_discovery_scan,
    get_onboarding_state,
    get_onboarding_status,
    reset_onboarding,
    save_onboarding_step,
)

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


class StepPayloadBody(BaseModel):
    payload: dict[str, Any] = {}


class CompleteOnboardingBody(BaseModel):
    primary_salary: dict[str, Any] | None = None
    recurring_items: list[dict[str, Any]] = []


@router.get("/state")
def get_state_route(
    session: Session = Depends(db_session),
    settings: Settings = Depends(settings_dep),
) -> dict[str, Any]:
    return get_onboarding_state(session, settings)


@router.get("/status")
def get_status_route(session: Session = Depends(db_session)) -> dict[str, Any]:
    return get_onboarding_status(session)


@router.get("/fast-scan")
def get_fast_scan_route(session: Session = Depends(db_session)) -> dict[str, Any]:
    return fast_discovery_scan(session)


@router.get("/discover")
def get_discover_route(session: Session = Depends(db_session)) -> dict[str, Any]:
    return discover_onboarding_entities(session)


@router.post("/step/{step_num}")
def post_step_route(
    step_num: int,
    body: StepPayloadBody,
    session: Session = Depends(db_session),
) -> dict[str, Any]:
    return save_onboarding_step(session, step_num, body.payload)


@router.post("/complete")
def post_complete_route(
    body: CompleteOnboardingBody,
    session: Session = Depends(db_session),
) -> dict[str, Any]:
    return complete_onboarding(session, body.model_dump())


@router.post("/reset")
def post_reset_route(session: Session = Depends(db_session)) -> dict[str, Any]:
    return reset_onboarding(session)

