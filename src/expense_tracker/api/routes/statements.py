"""API routes for Credit Card Statements and Password Profiles."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from expense_tracker.api.deps import db_session
from expense_tracker.config import get_settings
from expense_tracker.db.models import (
    Account,
    CreditCardStatement,
    PasswordProfile,
    StatementProcessingEvent,
    new_id,
    utcnow,
)
from expense_tracker.ingestion.gmail.client import GmailApiSource
from expense_tracker.statements.discovery import DiscoveredStatementCandidate
from expense_tracker.statements.password_engine import ALL_STRATEGIES
from expense_tracker.statements.service import (
    discover_statements_from_source,
    find_matching_account,
    ingest_candidate,
    process_statement_bytes,
    unlock_statement_manually,
    upsert_password_profile,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["statements"])


class PasswordProfilePayload(BaseModel):
    issuer: str
    strategy: str = "NAME4_DDMM"
    configuration: dict[str, Any] = {}


class UnlockStatementPayload(BaseModel):
    password: str
    save_to_profile: bool = False
    strategy: str = "CUSTOM"


def _format_event(e: StatementProcessingEvent) -> dict[str, Any]:
    return {
        "id": e.id,
        "stage": e.stage,
        "status": e.status,
        "message": e.message,
        "metadata": e.metadata_json or {},
        "started_at": e.started_at.isoformat() if e.started_at else None,
        "completed_at": e.completed_at.isoformat() if e.completed_at else None,
    }


from expense_tracker.ingestion.gmail.links import gmail_web_url


def _format_statement(stmt: CreditCardStatement, include_events: bool = False) -> dict[str, Any]:
    data = {
        "id": stmt.id,
        "account_id": stmt.account_id,
        "account_name": stmt.account.name if stmt.account else None,
        "account_type": stmt.account.account_type if stmt.account else None,
        "account_number_masked": stmt.account.account_number_masked if stmt.account else None,
        "source_email_id": stmt.source_email_id,
        "source_attachment_id": stmt.source_attachment_id,
        "gmail_url": gmail_web_url(message_id=stmt.source_email_id) if stmt.source_email_id else None,
        "issuer": stmt.issuer,
        "statement_type": getattr(stmt, "statement_type", "CREDIT_CARD") or "CREDIT_CARD",
        "card_last4": stmt.card_last4,
        "statement_period_start": stmt.statement_period_start.isoformat()
        if stmt.statement_period_start
        else None,
        "statement_period_end": stmt.statement_period_end.isoformat()
        if stmt.statement_period_end
        else None,
        "statement_date": stmt.statement_date.isoformat() if stmt.statement_date else None,
        "payment_due_date": stmt.payment_due_date.isoformat() if getattr(stmt, "payment_due_date", None) else None,
        "total_amount_due": float(stmt.total_amount_due) if getattr(stmt, "total_amount_due", None) is not None else None,
        "email_received_at": (stmt.email_received_at or stmt.discovered_at or stmt.created_at).isoformat()
        if (getattr(stmt, "email_received_at", None) or stmt.discovered_at or stmt.created_at)
        else None,
        "original_filename": stmt.original_filename,
        "original_sha256": stmt.original_sha256,
        "unlocked_sha256": stmt.unlocked_sha256,
        "has_original_file": bool(stmt.original_file_path and Path(stmt.original_file_path).exists()),
        "has_unlocked_file": bool(stmt.unlocked_file_path and Path(stmt.unlocked_file_path).exists()),
        "is_encrypted": stmt.is_encrypted,
        "password_strategy_id": stmt.password_strategy_id,
        "status": stmt.status,
        "discovered_at": stmt.discovered_at.isoformat() if stmt.discovered_at else None,
        "downloaded_at": stmt.downloaded_at.isoformat() if stmt.downloaded_at else None,
        "unlocked_at": stmt.unlocked_at.isoformat() if stmt.unlocked_at else None,
        "created_at": stmt.created_at.isoformat() if stmt.created_at else None,
        "updated_at": stmt.updated_at.isoformat() if stmt.updated_at else None,
        "error_code": stmt.error_code,
        "error_message": stmt.error_message,
        "event_count": len(stmt.events) if stmt.events else 0,
    }
    if include_events:
        data["events"] = [_format_event(e) for e in stmt.events]
    return data


@router.get("/api/statements")
def list_statements(
    account_id: str | None = Query(None),
    issuer: str | None = Query(None),
    status: str | None = Query(None),
    statement_type: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: Session = Depends(db_session),
) -> dict[str, Any]:
    query = select(CreditCardStatement)
    if account_id:
        query = query.where(CreditCardStatement.account_id == account_id)
    if issuer:
        query = query.where(CreditCardStatement.issuer == issuer)
    if status:
        query = query.where(CreditCardStatement.status == status)
    if statement_type:
        query = query.where(CreditCardStatement.statement_type == statement_type)

    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0

    query = query.order_by(
        desc(func.coalesce(CreditCardStatement.statement_date, CreditCardStatement.created_at)),
        desc(CreditCardStatement.created_at),
    ).offset(offset).limit(limit)

    statements = session.scalars(query).all()
    return {
        "statements": [_format_statement(s) for s in statements],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/api/statements/{statement_id}")
def get_statement(
    statement_id: str,
    session: Session = Depends(db_session),
) -> dict[str, Any]:
    statement = session.get(CreditCardStatement, statement_id)
    if not statement:
        raise HTTPException(status_code=404, detail="Statement not found")
    return _format_statement(statement, include_events=True)


@router.post("/api/statements/discover")
def discover_statements(
    max_messages: int = Query(50, ge=1, le=200),
    session: Session = Depends(db_session),
) -> dict[str, Any]:
    settings = get_settings()
    try:
        source = GmailApiSource(settings)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Cannot connect to Gmail: {exc}")

    results = discover_statements_from_source(session, source, max_messages=max_messages)
    return {
        "discovered_count": len(results),
        "statements": [_format_statement(s) for s in results],
    }


@router.post("/api/statements/upload")
async def upload_statement(
    file: UploadFile = File(...),
    account_id: str | None = Form(None),
    issuer: str | None = Form(None),
    card_last4: str | None = Form(None),
    statement_date: str | None = Form(None),
    session: Session = Depends(db_session),
) -> dict[str, Any]:
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    filename = file.filename or "uploaded_statement.pdf"
    parsed_date: datetime | None = None
    if statement_date:
        try:
            parsed_date = datetime.fromisoformat(statement_date).replace(tzinfo=timezone.utc)
        except Exception:
            parsed_date = None

    # Derive issuer and card_last4 if missing
    resolved_account: Account | None = None
    if account_id:
        resolved_account = session.get(Account, account_id)
    if not resolved_account and (issuer or card_last4):
        resolved_account = find_matching_account(session, issuer or "", card_last4)

    final_issuer = (
        issuer
        or (resolved_account.name.split()[0] if resolved_account else None)
        or "UNKNOWN"
    )
    final_card4 = card_last4 or (resolved_account.card_last4 if resolved_account else None)

    candidate = DiscoveredStatementCandidate(
        source_email_id=None,
        source_attachment_id=None,
        issuer=final_issuer,
        card_last4=final_card4,
        statement_date=parsed_date or utcnow(),
        statement_period_start=None,
        statement_period_end=None,
        original_filename=filename,
        attachment_data=content,
        extra_metadata={"source": "manual_upload", "filename": filename},
    )

    statement = ingest_candidate(session, candidate, attachment_bytes=content)
    if resolved_account and not statement.account_id:
        statement.account_id = resolved_account.id
        session.commit()

    return _format_statement(statement, include_events=True)


@router.post("/api/statements/{statement_id}/unlock")
def unlock_statement(
    statement_id: str,
    payload: UnlockStatementPayload,
    session: Session = Depends(db_session),
) -> dict[str, Any]:
    ok, statement, error = unlock_statement_manually(
        session,
        statement_id=statement_id,
        password=payload.password,
        save_to_profile=payload.save_to_profile,
        strategy=payload.strategy,
    )
    if not ok or not statement:
        raise HTTPException(status_code=400, detail=error or "Failed to unlock statement")
    return _format_statement(statement, include_events=True)


@router.get("/api/statements/{statement_id}/file/original")
def download_original_statement(
    statement_id: str,
    download: bool = Query(False),
    session: Session = Depends(db_session),
):
    statement = session.get(CreditCardStatement, statement_id)
    if not statement:
        raise HTTPException(status_code=404, detail="Statement not found")

    if not statement.original_file_path or not Path(statement.original_file_path).exists():
        raise HTTPException(status_code=404, detail="Original PDF file not found on disk")

    filename = statement.original_filename or f"{statement.issuer}_statement_original.pdf"
    disposition = "attachment" if download else "inline"
    return FileResponse(
        statement.original_file_path,
        media_type="application/pdf",
        filename=filename,
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )


@router.get("/api/statements/{statement_id}/file/unlocked")
def download_unlocked_statement(
    statement_id: str,
    download: bool = Query(False),
    session: Session = Depends(db_session),
):
    statement = session.get(CreditCardStatement, statement_id)
    if not statement:
        raise HTTPException(status_code=404, detail="Statement not found")

    if not statement.unlocked_file_path or not Path(statement.unlocked_file_path).exists():
        raise HTTPException(status_code=404, detail="Unlocked PDF file not found on disk")

    filename = f"{statement.issuer}_statement_{statement.card_last4 or 'card'}_unlocked.pdf"
    disposition = "attachment" if download else "inline"
    return FileResponse(
        statement.unlocked_file_path,
        media_type="application/pdf",
        filename=filename,
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )


def _redact_password_profile_configuration(configuration: dict[str, Any] | None) -> dict[str, Any]:
    """Strip the plaintext PDF password before a profile leaves the server."""
    config = dict(configuration or {})
    has_custom_password = bool(config.get("custom_password"))
    config["custom_password"] = None
    config["has_custom_password"] = has_custom_password
    return config


@router.get("/api/accounts/{account_id}/password-profile")
def get_account_password_profile(
    account_id: str,
    session: Session = Depends(db_session),
) -> dict[str, Any]:
    account = session.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    profile = session.scalars(
        select(PasswordProfile).where(PasswordProfile.account_id == account_id)
    ).first()

    available_strategies = list(ALL_STRATEGIES.keys())

    if not profile:
        return {
            "configured": False,
            "account_id": account_id,
            "account_name": account.name,
            "issuer": account.name.split()[0] if account.name else "GENERIC",
            "strategy": "NAME4_DDMM",
            "configuration": {},
            "available_strategies": available_strategies,
        }

    return {
        "configured": True,
        "id": profile.id,
        "account_id": profile.account_id,
        "account_name": account.name,
        "issuer": profile.issuer,
        "strategy": profile.strategy,
        "configuration": _redact_password_profile_configuration(profile.configuration),
        "available_strategies": available_strategies,
        "created_at": profile.created_at.isoformat() if profile.created_at else None,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }


@router.put("/api/accounts/{account_id}/password-profile")
def update_account_password_profile(
    account_id: str,
    payload: PasswordProfilePayload,
    session: Session = Depends(db_session),
) -> dict[str, Any]:
    account = session.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    from expense_tracker.statements.service import reprocess_locked_statements_for_account

    configuration = dict(payload.configuration)
    if not configuration.get("custom_password"):
        # GET never echoes the stored password back to the client, so a blank
        # field here means "unchanged", not "clear it" — keep the prior value.
        existing = session.scalars(
            select(PasswordProfile).where(PasswordProfile.account_id == account_id)
        ).first()
        if existing and existing.configuration:
            existing_password = existing.configuration.get("custom_password")
            if existing_password:
                configuration["custom_password"] = existing_password

    profile = upsert_password_profile(
        session,
        account_id=account_id,
        issuer=payload.issuer,
        strategy=payload.strategy,
        configuration=configuration,
    )
    unlocked_count = reprocess_locked_statements_for_account(session, account_id)
    return {
        "success": True,
        "id": profile.id,
        "account_id": profile.account_id,
        "issuer": profile.issuer,
        "strategy": profile.strategy,
        "configuration": _redact_password_profile_configuration(profile.configuration),
        "unlocked_statements_count": unlocked_count,
    }


@router.get("/api/accounts/{account_id}/statements")
def get_account_statements(
    account_id: str,
    session: Session = Depends(db_session),
) -> dict[str, Any]:
    account = session.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    statements = session.scalars(
        select(CreditCardStatement)
        .where(CreditCardStatement.account_id == account_id)
        .order_by(
            desc(CreditCardStatement.statement_date), desc(CreditCardStatement.created_at)
        )
    ).all()

    return {
        "account_id": account_id,
        "account_name": account.name,
        "statements": [_format_statement(s) for s in statements],
    }
