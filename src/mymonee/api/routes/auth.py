"""Authentication API endpoints for local & Wi-Fi PIN lock."""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from mymonee.api.deps import DbSession
from mymonee.services.auth import (
    change_master_pin,
    is_auth_configured,
    set_master_pin,
    verify_master_pin,
    verify_session_token,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

COOKIE_NAME = "mymonee_session"
COOKIE_MAX_AGE = 30 * 24 * 60 * 60  # 30 days


class PinRequest(BaseModel):
    pin: str


class ChangePinRequest(BaseModel):
    old_pin: str
    new_pin: str


def _get_token_from_request(
    authorization: str | None = Header(default=None),
    mymonee_session: str | None = Cookie(default=None),
) -> str | None:
    if authorization and authorization.startswith("Bearer "):
        return authorization.removeprefix("Bearer ").strip()
    return mymonee_session


@router.get("/status")
def auth_status(
    session: Session = DbSession,
    token: str | None = Depends(_get_token_from_request),
) -> dict[str, Any]:
    configured = is_auth_configured(session)
    authenticated = verify_session_token(session, token) if configured else True
    return {
        "configured": configured,
        "authenticated": authenticated,
    }


@router.post("/setup")
def auth_setup(
    payload: PinRequest,
    response: Response,
    session: Session = DbSession,
) -> dict[str, Any]:
    if is_auth_configured(session):
        raise HTTPException(status_code=400, detail="Master PIN is already configured")

    token = set_master_pin(session, payload.pin)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
    )
    return {
        "success": True,
        "token": token,
        "message": "Master PIN successfully configured",
    }


@router.post("/login")
def auth_login(
    payload: PinRequest,
    response: Response,
    session: Session = DbSession,
) -> dict[str, Any]:
    token = verify_master_pin(session, payload.pin)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
    )
    return {
        "success": True,
        "token": token,
        "expires_in_days": 30,
    }


@router.post("/logout")
def auth_logout(response: Response) -> dict[str, Any]:
    response.delete_cookie(key=COOKIE_NAME)
    return {"success": True}


@router.post("/change-pin")
def auth_change_pin(
    payload: ChangePinRequest,
    response: Response,
    session: Session = DbSession,
) -> dict[str, Any]:
    token = change_master_pin(session, payload.old_pin, payload.new_pin)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
    )
    return {
        "success": True,
        "token": token,
        "message": "PIN changed successfully",
    }
