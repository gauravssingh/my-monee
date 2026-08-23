"""Gmail OAuth + sync API."""

from __future__ import annotations

import json
import logging
import shutil
import html
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from mymonee.api.deps import db_session, settings_dep
from mymonee.config import Settings
from mymonee.db.models import CreditCardStatement, Email

from mymonee.ingestion.gmail.client import GmailApiSource
from mymonee.ingestion.gmail.links import gmail_web_url
from mymonee.ingestion.gmail.oauth import (
    GmailAuthError,
    clear_credentials,
    complete_oauth,
    is_connected,
    start_oauth,
)
from mymonee.ingestion.pipeline import run_ingestion_pipeline, run_ingestion_result_dict

logger = logging.getLogger(__name__)
router = APIRouter(tags=["gmail"])


class CredentialsPayload(BaseModel):
    """Google OAuth client secrets JSON (Desktop or Web client)."""

    installed: dict[str, Any] | None = None
    web: dict[str, Any] | None = None


class CredentialsInstallBody(BaseModel):
    client_secrets: dict[str, Any] = Field(
        ...,
        description="Full Google OAuth client JSON (with installed or web key)",
    )


def _validate_client_secrets(payload: dict[str, Any]) -> dict[str, Any]:
    if "installed" not in payload and "web" not in payload:
        raise HTTPException(
            status_code=400,
            detail="JSON must contain an 'installed' or 'web' OAuth client block",
        )
    block = payload.get("installed") or payload.get("web") or {}
    if not block.get("client_id") or not block.get("client_secret"):
        raise HTTPException(status_code=400, detail="client_id and client_secret are required")
    return payload


@router.get("/api/gmail/status")
def gmail_status(settings: Settings = Depends(settings_dep)) -> dict[str, Any]:
    creds_path = settings.gmail_credentials_path()
    return {
        "enabled": settings.gmail.enabled,
        "connected": is_connected(settings),
        "credentials_file": str(creds_path),
        "credentials_file_present": creds_path.exists(),
        "redirect_uri": settings.oauth_redirect_uri(),
        "scopes": settings.gmail.scopes,
        "sync_after_date": settings.gmail.sync_after_date,
        "initial_lookback_days": settings.gmail.initial_lookback_days,
        "max_messages_per_sync": settings.gmail.max_messages_per_sync,
    }


@router.post("/api/gmail/credentials")
def install_credentials(
    body: CredentialsInstallBody,
    settings: Settings = Depends(settings_dep),
) -> dict[str, Any]:
    payload = _validate_client_secrets(body.client_secrets)
    path = settings.gmail_credentials_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_suffix(".json.bak")
        shutil.copy2(path, backup)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    path.chmod(0o600)
    logger.info("Installed Gmail OAuth client secrets at %s", path)
    return {
        "installed": True,
        "credentials_file": str(path),
        "credentials_file_present": True,
        "redirect_uri": settings.oauth_redirect_uri(),
    }


@router.post("/api/gmail/credentials/from-path")
def install_credentials_from_path(
    path: str = Query(..., description="Absolute path to downloaded client_secret JSON"),
    settings: Settings = Depends(settings_dep),
) -> dict[str, Any]:
    src = Path(path).expanduser()
    if not src.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {src}")
    try:
        payload = json.loads(src.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}") from exc
    return install_credentials(CredentialsInstallBody(client_secrets=payload), settings)


@router.post("/api/gmail/auth/start")
def gmail_auth_start(settings: Settings = Depends(settings_dep)) -> dict[str, str]:
    if not settings.gmail.enabled:
        raise HTTPException(status_code=400, detail="Gmail integration is disabled in config")
    try:
        started = start_oauth(settings)
    except GmailAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"authorization_url": started.authorization_url, "state": started.state}


@router.get("/oauth/callback")
def oauth_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    settings: Settings = Depends(settings_dep),
) -> HTMLResponse:
    def page(title: str, body: str, *, ok: bool) -> HTMLResponse:
        color = "#0c6e5c" if ok else "#9b2c2c"
        escaped_title = html.escape(title)
        escaped_body = html.escape(body)
        html_str = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/><title>{escaped_title}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         margin: 48px auto; max-width: 520px; color: #15202b; line-height: 1.45; }}
  h1 {{ color: {color}; font-size: 1.4rem; }}
  a {{ color: #0c6e5c; }}
</style></head><body>
  <h1>{escaped_title}</h1>
  <p>{escaped_body}</p>
  <p><a href="/settings">Back to Settings</a></p>
  <script>setTimeout(function() {{ window.location = "/settings"; }}, {1800 if ok else 5000});</script>
</body></html>"""
        return HTMLResponse(html_str, status_code=200 if ok else 400)

    if error:
        return page("Gmail connection failed", error, ok=False)
    if not code:
        return page("Gmail connection failed", "Missing OAuth code. Start again from Settings.", ok=False)
    try:
        complete_oauth(settings, code=code, state=state)
    except GmailAuthError as exc:
        return page("Gmail connection failed", str(exc), ok=False)
    except Exception as exc:
        logger.exception("Unexpected OAuth callback failure")
        return page(
            "Gmail connection failed",
            f"Unexpected error: {exc}. Start Connect Gmail again from Settings.",
            ok=False,
        )
    return page(
        "Gmail connected",
        "Tokens are stored in the macOS Keychain. You can sync from Settings.",
        ok=True,
    )


@router.post("/api/ingestion/demo")
def ingestion_demo(
    session: Session = Depends(db_session),
    settings: Settings = Depends(settings_dep),
) -> dict[str, Any]:
    from datetime import datetime, timezone
    from mymonee.ingestion.gmail.client import FixtureMessageSource, GmailMessage
    from mymonee.ingestion.pipeline import run_ingestion_pipeline, run_ingestion_result_dict

    demo_messages = [
        GmailMessage(
            id="demo-1",
            thread_id="t-1",
            sender="alerts@hdfcbank.net",
            subject="INR 2,499.50 debited",
            snippet="INR 2,499.50 debited from A/c XX8899",
            received_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
            label_ids=["INBOX"],
            headers={},
            body_text="INR 2,499.50 debited from A/c XX8899 on 01-08-2026 towards RAZ*SWIGGY. UPI Ref: 9988776655",
            body_html=None,
        ),
        GmailMessage(
            id="demo-2",
            thread_id="t-2",
            sender="alerts@axisbank.com",
            subject="Transaction alert for Axis Bank Card",
            snippet="Your Axis Bank Credit Card ending 1234 was used",
            received_at=datetime(2026, 8, 2, tzinfo=timezone.utc),
            label_ids=["INBOX"],
            headers={},
            body_text="Your Axis Bank Credit Card ending 1234 was used for INR 4,999.00 at AMAZON INDIA on 02-08-2026. Ref: 11223344.",
            body_html=None,
        ),
        GmailMessage(
            id="demo-3",
            thread_id="t-3",
            sender="alerts@scapia.cards",
            subject="Transaction on Scapia Federal Credit Card",
            snippet="Spent INR 1,250.00 on Scapia Card",
            received_at=datetime(2026, 8, 3, tzinfo=timezone.utc),
            label_ids=["INBOX"],
            headers={},
            body_text="Spent INR 1,250.00 on Scapia Card at UBER INDIA on 03-08-2026. Ref: 55667788.",
            body_html=None,
        ),
        GmailMessage(
            id="demo-4",
            thread_id="t-4",
            sender="newsletter@updates.com",
            subject="Your weekly digest",
            snippet="Here is your newsletter update",
            received_at=datetime(2026, 8, 4, tzinfo=timezone.utc),
            label_ids=["INBOX"],
            headers={},
            body_text="Here is your newsletter update.",
            body_html=None,
        ),
    ]

    source = FixtureMessageSource(demo_messages)
    result = run_ingestion_pipeline(
        session,
        settings,
        source=source,
    )
    return run_ingestion_result_dict(result)


@router.post("/api/gmail/disconnect")
def gmail_disconnect(settings: Settings = Depends(settings_dep)) -> dict[str, bool]:
    clear_credentials()
    return {"disconnected": True, "connected": is_connected(settings)}


@router.post("/api/gmail/sync")
def gmail_sync(
    session: Session = Depends(db_session),
    settings: Settings = Depends(settings_dep),
    max_messages: int | None = Query(default=None, ge=1, le=5000),
    force_reparse: bool = False,
    after_date: str | None = Query(
        default=None,
        description="Gmail after: date as YYYY/MM/DD (forces backfill)",
    ),
    full_year: bool = Query(
        default=False,
        description="Sync from configured sync_after_date (default 2026/01/01), ignoring watermark",
    ),
) -> dict[str, Any]:
    if not is_connected(settings):
        raise HTTPException(status_code=400, detail="Gmail is not connected")

    resolved_after = after_date
    ignore_watermark = False
    if full_year:
        resolved_after = after_date or settings.gmail.sync_after_date or "2026/01/01"
        ignore_watermark = True

    result = run_ingestion_pipeline(
        session,
        settings,
        max_messages=max_messages,
        force_reparse=force_reparse,
        after_date=resolved_after,
        ignore_watermark=ignore_watermark or bool(after_date),
    )
    return run_ingestion_result_dict(result)


@router.get("/api/gmail/messages/{message_id}")
def fetch_gmail_message(
    message_id: str,
    session: Session = Depends(db_session),
    settings: Settings = Depends(settings_dep),
) -> dict[str, Any]:
    """Realtime fetch of a known ingested email body (not persisted)."""

    # Only allow messages we already discovered/ingested locally.
    local = session.get(Email, message_id)
    if local is None:
        local_stmt = session.scalars(
            select(CreditCardStatement).where(CreditCardStatement.source_email_id == message_id)
        ).first()
        if local_stmt is None:
            raise HTTPException(status_code=404, detail="Email not found in local index")

    try:
        message = GmailApiSource(settings).get_message(message_id)
    except Exception as exc:
        logger.exception("Failed realtime Gmail fetch for %s", message_id)
        raise HTTPException(status_code=502, detail=f"Gmail fetch failed: {exc}") from exc

    logger.info("Fetched Gmail message %s for local viewing (body not stored)", message_id)
    return {
        "id": message.id,
        "thread_id": message.thread_id,
        "sender": message.sender,
        "subject": message.subject,
        "snippet": message.snippet,
        "received_at": message.received_at.isoformat() if message.received_at else None,
        "body_text": message.body_text,
        "body_html": message.body_html,
        "gmail_url": gmail_web_url(thread_id=message.thread_id, message_id=message.id),
        "stored_locally": False,
    }

