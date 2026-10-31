"""Tests for Phase 2 Reliability Remediation.

Covers:
1. Doctor uses load_credentials(settings) so Keychain OAuth credentials are recognized.
2. In-memory caching of auth configuration and secret key avoids redundant SQLite queries.
3. Dashboard _income_candidates_around eager-loads subcategory using joinedload.
4. SQLite sessions do not compete for a fixed connection pool, so slow work cannot
   starve ordinary API requests.
5. Gmail throttling (403 quota / 429) is counted separately from parser failures.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

from googleapiclient.errors import HttpError
from sqlalchemy import select, text

from mymonee.app import create_app
from mymonee.config import Settings
from mymonee.db.models import (
    Account,
    Category,
    IngestionEvent,
    IngestionRun,
    Subcategory,
    SyncState,
    Transaction,
    new_id,
)
from mymonee.db.session import get_session_factory
from mymonee.domain.enums import IngestionRunStatus
from mymonee.ingestion.gmail import oauth
from mymonee.ingestion.gmail.client import GmailMessage, MessageSource
from mymonee.ingestion.pipeline import run_ingestion_pipeline
from mymonee.services.auth import (
    invalidate_auth_cache,
    is_auth_configured,
    set_master_pin,
    verify_session_token,
)
from mymonee.services.dashboard import _income_candidates_around
from mymonee.services.doctor import get_operational_status, run_diagnostics


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        app={"data_dir": tmp_path, "name": "test-mymonee"},
        database={"filename": "test.db", "echo": False},
        privacy={"allow_external_ai": False},
    )


def test_doctor_detects_credentials_via_load_credentials(tmp_path: Path) -> None:
    """Doctor must report Gmail as connected when load_credentials returns credentials,
    even if the fallback file gmail_token.json does not exist (e.g. macOS Keychain)."""
    settings = _settings(tmp_path)
    _ = create_app(settings)

    # Ensure fallback file definitely does not exist
    fallback_file = settings.resolved_data_dir() / "gmail_token.json"
    if fallback_file.exists():
        fallback_file.unlink()

    fake_creds = MagicMock()

    with patch("mymonee.ingestion.gmail.oauth.load_credentials", return_value=fake_creds):
        status = get_operational_status(settings)
        assert status["gmail_connected"] is True

        diag = run_diagnostics(settings)
        gmail_check = next((c for c in diag["checks"] if c["category"] == "Gmail"), None)
        assert gmail_check is not None
        assert gmail_check["status"] == "PASS"
        assert "OAuth credentials present" in gmail_check["detail"]


def test_auth_in_memory_caching(tmp_path: Path) -> None:
    """Auth configuration and secret key must be cached in memory to eliminate
    per-request SQLite connection churn."""
    settings = _settings(tmp_path)
    _ = create_app(settings)
    session_factory = get_session_factory()

    invalidate_auth_cache()

    # 1. Unconfigured initially -> cached as False
    with session_factory() as session:
        assert is_auth_configured(session) is False

    # Calling without session should return cached False without opening DB session
    assert is_auth_configured() is False

    # 2. Configure master PIN
    with session_factory() as session:
        token = set_master_pin(session, "987654")
        session.commit()

    # Cache should immediately reflect True
    assert is_auth_configured() is True
    assert is_auth_configured(None) is True

    # 3. Verify session token without providing a DB session (in-memory HMAC verification)
    assert verify_session_token(None, token) is True
    assert verify_session_token(None, "session:123:badhmac") is False
    assert verify_session_token(None, "invalid-token") is False

    # 4. Invalidate cache -> reloads on next call
    invalidate_auth_cache()
    with session_factory() as session:
        assert is_auth_configured(session) is True
    assert verify_session_token(None, token) is True


def test_dashboard_income_candidates_eager_loads_subcategory(tmp_path: Path) -> None:
    """_income_candidates_around must eager load subcategory to avoid N+1 queries."""
    settings = _settings(tmp_path)
    _ = create_app(settings)
    session_factory = get_session_factory()

    with session_factory() as session:
        acc = Account(
            id=new_id(), name="Axis Bank", account_type="BANK", is_asset=True, is_liability=False
        )
        income_cat = session.scalar(select(Category).where(Category.slug == "income"))
        assert income_cat is not None
        salary_sub = session.scalar(select(Subcategory).where(Subcategory.slug == "salary"))
        assert salary_sub is not None

        session.add(acc)
        session.flush()

        tx = Transaction(
            id=new_id(),
            source="test",
            amount=Decimal("150000.00"),
            currency="INR",
            direction="credit",
            transaction_type="income",
            category_id=income_cat.id,
            subcategory_id=salary_sub.id,
            transaction_date=datetime(2026, 8, 31, 10, 0, tzinfo=UTC),
            needs_review=False,
            is_duplicate=False,
        )
        session.add(tx)
        tx_id = tx.id
        session.commit()

    # Query in a fresh session to test eager loading
    with session_factory() as session:
        candidates = _income_candidates_around(session, year=2026, month=8)
        assert len(candidates) >= 1
        found_tx = next(t for t in candidates if t.id == tx_id)
        # Accessing .subcategory should already be populated without lazy-load
        assert found_tx.subcategory is not None
        assert found_tx.subcategory.slug == "salary"


def test_sqlite_sessions_do_not_starve_under_concurrent_work(tmp_path: Path) -> None:
    """Ordinary requests must not wait on a fixed connection pool.

    Classification and Gmail fetches hold a session for tens of seconds; with the
    default QueuePool (5 + 10 overflow, 30s timeout) the rest of the API turned into
    500s. SQLite is a local file, so sessions must not queue behind each other.
    """
    settings = _settings(tmp_path)
    _ = create_app(settings)
    session_factory = get_session_factory()

    started = time.monotonic()
    sessions = [session_factory() for _ in range(25)]
    try:
        for session in sessions:
            assert session.execute(text("select 1")).scalar() == 1
    finally:
        for session in sessions:
            session.close()

    assert time.monotonic() - started < 5.0


class _ThrottledMessageSource(MessageSource):
    """One message is served normally, one is throttled by a Gmail 403 quota error."""

    def list_message_ids(self, query: str, max_results: int = 500) -> list[str]:
        return ["msg-ok", "msg-throttled"]

    def get_message(self, message_id: str) -> GmailMessage:
        if message_id == "msg-throttled":
            raise HttpError(
                resp=MagicMock(status=403, reason="Forbidden"),
                content=(
                    b'{"error": {"code": 403, "message": "Quota exceeded for quota metric '
                    b"'Total Query Cost' and limit 'Units per minute per user'\", "
                    b'"errors": [{"reason": "rateLimitExceeded", "domain": "usageLimits"}]}}'
                ),
            )
        return GmailMessage(
            id=message_id,
            thread_id="thread-msg-ok",
            sender="alerts@axis.bank.in",
            subject="Transaction alert for Axis Bank A/c msg-ok",
            snippet="Your A/c was debited with INR 500.00 for msg-ok",
            received_at=datetime(2026, 8, 20, 10, 0, tzinfo=UTC),
            internal_date_ms=1787220000000,
            headers={
                "from": "alerts@axis.bank.in",
                "subject": "Transaction alert for Axis Bank A/c msg-ok",
            },
            label_ids=["INBOX"],
            body_text=(
                "Your A/c no. XX1022 is debited with INR 500.00 on 20-08-2026 at "
                "MERCHANT_OK. Ref: REF_OK"
            ),
            body_html=None,
        )

    def get_profile_history_id(self) -> str | None:
        return "12345"

    def get_attachment(self, message_id: str, attachment_id: str) -> bytes:
        return b""


def test_gmail_throttling_is_not_reported_as_a_parse_error(tmp_path: Path) -> None:
    """A throttled fetch must land in its own bucket, with the run still marked partial."""
    settings = _settings(tmp_path)
    _ = create_app(settings)
    session_factory = get_session_factory()

    with session_factory() as session:
        result = run_ingestion_pipeline(
            session=session,
            settings=settings,
            source=_ThrottledMessageSource(),
            ignore_watermark=True,
        )
        session.commit()

        assert result.rate_limited == 1
        assert result.parsing_errors == 0
        assert result.transactions_extracted == 1
        assert result.status == IngestionRunStatus.PARTIAL

        run = session.get(IngestionRun, result.run_id)
        assert run is not None
        assert run.parsing_errors == 0
        assert (run.extra_json or {}).get("rate_limited") == 1

        events = session.scalars(
            select(IngestionEvent).where(
                IngestionEvent.run_id == result.run_id,
                IngestionEvent.event_type == "message_rate_limited",
            )
        ).all()
        assert len(events) == 1


# --- watermark safety ---------------------------------------------------------------------


def _watermark(session) -> str | None:
    return session.scalar(
        select(SyncState.value).where(SyncState.key == "gmail.last_internal_date_ms")
    )


def test_throttled_sync_does_not_advance_the_watermark(tmp_path: Path) -> None:
    """A throttled fetch leaves a message behind; moving the watermark would skip it forever."""
    settings = _settings(tmp_path)
    _ = create_app(settings)

    with get_session_factory()() as session:
        result = run_ingestion_pipeline(
            session=session,
            settings=settings,
            source=_ThrottledMessageSource(),
            ignore_watermark=True,
        )
        session.commit()

        assert result.rate_limited == 1
        assert _watermark(session) is None


def test_successful_sync_advances_the_watermark(tmp_path: Path) -> None:
    class _CompleteSource(_ThrottledMessageSource):
        def list_message_ids(self, query: str, *, max_results: int = 500) -> list[str]:
            return ["msg-ok"]

    settings = _settings(tmp_path)
    _ = create_app(settings)

    with get_session_factory()() as session:
        result = run_ingestion_pipeline(
            session=session,
            settings=settings,
            source=_CompleteSource(),
            ignore_watermark=True,
        )
        session.commit()

        assert result.rate_limited == 0
        assert _watermark(session) == "1787220000000"


# --- revoked OAuth token ------------------------------------------------------------------


class _RefreshRejected(Exception):
    """Stands in for google.auth.exceptions.RefreshError."""


class _RevokedCredentials:
    """An expired credential whose refresh token Google has revoked."""

    valid = False
    expired = True
    refresh_token = "refresh-token"

    def __init__(self) -> None:
        self.refresh_calls = 0

    def refresh(self, request) -> None:
        self.refresh_calls += 1
        raise _RefreshRejected(
            "('invalid_grant: Token has been expired or revoked.', {'error': 'invalid_grant'})"
        )


def test_revoked_gmail_token_logs_once_and_backs_off(tmp_path: Path, monkeypatch, caplog) -> None:
    """One actionable ERROR, and no repeated network attempts or tracebacks within the window."""
    settings = _settings(tmp_path)
    creds = _RevokedCredentials()
    monkeypatch.setattr(oauth, "load_credentials", lambda _settings: creds)
    oauth._clear_refresh_failure()
    try:
        with caplog.at_level(logging.ERROR, logger="mymonee.ingestion.gmail.oauth"):
            assert oauth.get_valid_credentials(settings) is None
            assert oauth.get_valid_credentials(settings) is None

        assert creds.refresh_calls == 1  # the second lookup is served from the failure cache
        errors = [record for record in caplog.records if record.levelno == logging.ERROR]
        assert len(errors) == 1
        assert "reconnect" in errors[0].getMessage().lower()
        assert not any(record.exc_info for record in errors)
    finally:
        oauth._clear_refresh_failure()


def test_oauth_failure_cache_clears_after_reconnect(tmp_path: Path, monkeypatch) -> None:
    settings = _settings(tmp_path)
    creds = _RevokedCredentials()
    monkeypatch.setattr(oauth, "load_credentials", lambda _settings: creds)
    oauth._clear_refresh_failure()
    try:
        assert oauth.get_valid_credentials(settings) is None
        assert creds.refresh_calls == 1

        oauth._clear_refresh_failure()  # save_credentials() does this when the user reconnects
        assert oauth.get_valid_credentials(settings) is None
        assert creds.refresh_calls == 2
    finally:
        oauth._clear_refresh_failure()
