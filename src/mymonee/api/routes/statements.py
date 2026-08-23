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

from mymonee.api.deps import db_session
from mymonee.config import get_settings
from mymonee.db.models import (
    Account,
    CreditCardStatement,
    PasswordProfile,
    StatementProcessingEvent,
    StatementTransaction,
    utcnow,
)
from mymonee.ingestion.gmail.client import GmailApiSource
from mymonee.statements.discovery import DiscoveredStatementCandidate
from mymonee.statements.password_engine import ALL_STRATEGIES
from mymonee.statements.service import (
    discover_statements_from_source,
    find_matching_account,
    ingest_candidate,
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


from mymonee.ingestion.gmail.links import gmail_web_url


def _format_statement(
    stmt: CreditCardStatement,
    include_events: bool = False,
    include_transactions: bool = True,
) -> dict[str, Any]:
    accounts_data = [
        {
            "id": a.id,
            "account_type": a.account_type,
            "institution": a.institution,
            "account_identifier": a.account_identifier,
            "masked_identifier": a.masked_identifier,
            "card_network": a.card_network,
            "account_name": a.account_name,
            "currency": a.currency,
            "opening_balance": float(a.opening_balance) if a.opening_balance is not None else None,
            "closing_balance": float(a.closing_balance) if a.closing_balance is not None else None,
            "credit_limit": float(a.credit_limit) if a.credit_limit is not None else None,
            "available_limit": float(a.available_limit) if a.available_limit is not None else None,
            "cash_withdrawal_limit": float(a.cash_withdrawal_limit) if a.cash_withdrawal_limit is not None else None,
            "attribution_confidence": a.attribution_confidence,
        }
        for a in stmt.statement_accounts
    ]

    summary_data = None
    if stmt.summary:
        s = stmt.summary
        summary_data = {
            "previous_balance": float(s.previous_balance) if s.previous_balance is not None else None,
            "payments": float(s.payments) if s.payments is not None else None,
            "refunds": float(s.refunds) if s.refunds is not None else None,
            "purchases": float(s.purchases) if s.purchases is not None else None,
            "cash_withdrawals": float(s.cash_withdrawals) if s.cash_withdrawals is not None else None,
            "fees": float(s.fees) if s.fees is not None else None,
            "interest": float(s.interest) if s.interest is not None else None,
            "other_charges": float(s.other_charges) if s.other_charges is not None else None,
            "total_due": float(s.total_due) if s.total_due is not None else None,
            "minimum_due": float(s.minimum_due) if s.minimum_due is not None else None,
            "statement_date": s.statement_date.isoformat() if s.statement_date else None,
            "due_date": s.due_date.isoformat() if s.due_date else None,
            "currency": s.currency,
            "extra_json": s.extra_json or {},
        }

    sections_data = [
        {
            "id": sec.id,
            "section_type": sec.section_type,
            "page_start": sec.page_start,
            "page_end": sec.page_end,
        }
        for sec in stmt.sections
    ]

    transactions_data = []
    if include_transactions:
        transactions_data = [
            {
                "id": tx.id,
                "statement_account_id": tx.statement_account_id,
                "transaction_date": tx.transaction_date.isoformat() if tx.transaction_date else None,
                "transaction_time": tx.transaction_time,
                "value_date": tx.value_date.isoformat() if tx.value_date else None,
                "description": tx.description,
                "reference_number": tx.reference_number,
                "transaction_type": tx.transaction_type,
                "amount": float(tx.amount),
                "debit_amount": float(tx.debit_amount) if tx.debit_amount is not None else None,
                "credit_amount": float(tx.credit_amount) if tx.credit_amount is not None else None,
                "currency": tx.currency,
                "running_balance": float(tx.running_balance) if tx.running_balance is not None else None,
                "source_page": tx.source_page,
                "source_row": tx.source_row,
                "raw_text": tx.raw_text,
                "attribution_status": tx.attribution_status,
                "match_status": tx.match_status,
                "match_confidence": tx.match_confidence,
                "match_reason": tx.match_reason,
                "matched_transaction_id": tx.matched_transaction_id,
                "matched_transaction": {
                    "id": tx.matched_transaction.id,
                    "transaction_date": tx.matched_transaction.transaction_date.isoformat() if tx.matched_transaction.transaction_date else None,
                    "amount": float(tx.matched_transaction.amount),
                    "currency": tx.matched_transaction.currency,
                    "direction": tx.matched_transaction.direction,
                    "merchant_raw": tx.matched_transaction.merchant_raw,
                    "merchant_normalized": tx.matched_transaction.merchant_normalized,
                    "category": tx.matched_transaction.category.name if tx.matched_transaction.category else None,
                    "account": tx.matched_transaction.account,
                    "card": tx.matched_transaction.card,
                    "source": tx.matched_transaction.source,
                } if tx.matched_transaction else None,
            }
            for tx in sorted(stmt.transactions, key=lambda x: (x.transaction_date, x.source_page, x.source_row or 0))
        ]

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
        "validation_status": stmt.validation_status or "PENDING",
        "validation_details": stmt.validation_details_json or {},
        "parser_name": stmt.parser_name,
        "parser_version": stmt.parser_version,
        "discovered_at": stmt.discovered_at.isoformat() if stmt.discovered_at else None,
        "downloaded_at": stmt.downloaded_at.isoformat() if stmt.downloaded_at else None,
        "unlocked_at": stmt.unlocked_at.isoformat() if stmt.unlocked_at else None,
        "created_at": stmt.created_at.isoformat() if stmt.created_at else None,
        "updated_at": stmt.updated_at.isoformat() if stmt.updated_at else None,
        "error_code": stmt.error_code,
        "error_message": stmt.error_message,
        "event_count": len(stmt.events) if stmt.events else 0,
        "transaction_count": len(stmt.transactions) if stmt.transactions else 0,
        "statement_accounts": accounts_data,
        "summary": summary_data,
        "sections": sections_data,
    }
    if include_transactions:
        data["transactions"] = transactions_data
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

    from mymonee.statements.service import reprocess_locked_statements_for_account

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


@router.post("/api/statements/{statement_id}/re-extract")
def re_extract_statement_route(
    statement_id: str,
    session: Session = Depends(db_session),
) -> dict[str, Any]:
    statement = session.get(CreditCardStatement, statement_id)
    if not statement:
        raise HTTPException(status_code=404, detail="Statement not found")

    from mymonee.statements.service import extract_and_validate_statement

    statement = extract_and_validate_statement(session, statement)
    return _format_statement(statement, include_events=True, include_transactions=True)


@router.post("/api/statements/batch-extract")
def batch_extract_statements_route(
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(db_session),
) -> dict[str, Any]:
    from mymonee.statements.service import extract_and_validate_statement

    stmts = session.scalars(
        select(CreditCardStatement).where(
            CreditCardStatement.unlocked_file_path.isnot(None),
            CreditCardStatement.status.in_(["READY_FOR_EXTRACTION", "UNLOCKED", "VALIDATED", "REVIEW_REQUIRED"]),
        ).limit(limit)
    ).all()

    processed = 0
    validated = 0
    review_required = 0
    failed = 0

    for s in stmts:
        try:
            res = extract_and_validate_statement(session, s)
            processed += 1
            if res.validation_status == "VALIDATED":
                validated += 1
            elif res.validation_status == "REVIEW_REQUIRED":
                review_required += 1
            elif res.status.endswith("_FAILED") or res.validation_status == "VALIDATION_FAILED":
                failed += 1
        except Exception as exc:
            logger.error(f"Failed extracting statement {s.id}: {exc}")
            failed += 1

    return {
        "success": True,
        "total_processed": processed,
        "validated_count": validated,
        "review_count": review_required,
        "failed_count": failed,
    }


@router.post("/api/statements/{statement_id}/reconcile")
def reconcile_statement_route(
    statement_id: str,
    session: Session = Depends(db_session),
) -> dict[str, Any]:
    statement = session.get(CreditCardStatement, statement_id)
    if not statement:
        raise HTTPException(status_code=404, detail="Statement not found")

    from mymonee.statements.reconciliation import reconcile_statement_in_db

    res = reconcile_statement_in_db(session, statement_id)
    return {
        "success": True,
        "statement_id": statement_id,
        "reconciliation": res,
        "statement": _format_statement(statement, include_events=True, include_transactions=True),
    }


class TransactionMatchPayload(BaseModel):
    match_status: str  # "MATCHED", "UNMATCHED", etc.
    matched_transaction_id: str | None = None
    match_reason: str | None = None


@router.post("/api/statements/{statement_id}/transactions/{transaction_id}/match")
def update_statement_transaction_match(
    statement_id: str,
    transaction_id: str,
    payload: TransactionMatchPayload,
    session: Session = Depends(db_session),
) -> dict[str, Any]:
    statement = session.get(CreditCardStatement, statement_id)
    if not statement:
        raise HTTPException(status_code=404, detail="Statement not found")

    tx = session.get(StatementTransaction, transaction_id)
    if not tx or tx.statement_id != statement_id:
        raise HTTPException(status_code=404, detail="Statement transaction not found")

    if payload.match_status == "MATCHED":
        tx.match_status = "MATCHED"
        tx.match_confidence = 1.0
        tx.match_reason = payload.match_reason or "Manually confirmed by user"
        if payload.matched_transaction_id:
            tx.matched_transaction_id = payload.matched_transaction_id
    elif payload.match_status == "UNMATCHED":
        tx.match_status = "UNMATCHED"
        tx.match_confidence = 0.0
        tx.matched_transaction_id = None
        tx.match_reason = payload.match_reason or "Rejected match by user"
    else:
        tx.match_status = payload.match_status

    session.commit()
    session.refresh(statement)
    return {
        "success": True,
        "transaction_id": transaction_id,
        "statement": _format_statement(statement, include_events=True, include_transactions=True),
    }


@router.post("/api/statements/{statement_id}/transactions/{transaction_id}/import")
def import_statement_transaction_route(
    statement_id: str,
    transaction_id: str,
    session: Session = Depends(db_session),
) -> dict[str, Any]:
    statement = session.get(CreditCardStatement, statement_id)
    if not statement:
        raise HTTPException(status_code=404, detail="Statement not found")

    stmt_tx = session.get(StatementTransaction, transaction_id)
    if not stmt_tx or stmt_tx.statement_id != statement_id:
        raise HTTPException(status_code=404, detail="Statement transaction not found")

    from mymonee.statements.emi import import_statement_transaction_to_ledger

    ledger_tx = import_statement_transaction_to_ledger(session, statement, stmt_tx)
    session.refresh(statement)
    return {
        "success": True,
        "transaction_id": transaction_id,
        "ledger_transaction_id": ledger_tx.id,
        "statement": _format_statement(statement, include_events=True, include_transactions=True),
    }


class ImportBundlePayload(BaseModel):
    transaction_ids: list[str]


@router.post("/api/statements/{statement_id}/import-bundle")
def import_statement_bundle_route(
    statement_id: str,
    payload: ImportBundlePayload,
    session: Session = Depends(db_session),
) -> dict[str, Any]:
    statement = session.get(CreditCardStatement, statement_id)
    if not statement:
        raise HTTPException(status_code=404, detail="Statement not found")

    from mymonee.statements.emi import import_statement_transaction_to_ledger

    imported_ids = []
    for tx_id in payload.transaction_ids:
        stmt_tx = session.get(StatementTransaction, tx_id)
        if stmt_tx and stmt_tx.statement_id == statement_id:
            ledger_tx = import_statement_transaction_to_ledger(session, statement, stmt_tx)
            imported_ids.append(ledger_tx.id)

    session.refresh(statement)
    return {
        "success": True,
        "imported_count": len(imported_ids),
        "ledger_transaction_ids": imported_ids,
        "statement": _format_statement(statement, include_events=True, include_transactions=True),
    }


@router.post("/api/statements/{statement_id}/transactions/{transaction_id}/scan-gmail")
def scan_gmail_transaction_route(
    statement_id: str,
    transaction_id: str,
    session: Session = Depends(db_session),
) -> dict[str, Any]:
    statement = session.get(CreditCardStatement, statement_id)
    if not statement:
        raise HTTPException(status_code=404, detail="Statement not found")

    from mymonee.statements.reconciliation import scan_gmail_for_upi_rrn

    res = scan_gmail_for_upi_rrn(session, statement_id, transaction_id)
    session.refresh(statement)
    return {
        **res,
        "statement": _format_statement(statement, include_events=True, include_transactions=True),
    }





