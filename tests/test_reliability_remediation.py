"""Tests for Phase 2 Reliability Remediation.

Covers:
1. Doctor uses load_credentials(settings) so Keychain OAuth credentials are recognized.
2. In-memory caching of auth configuration and secret key avoids redundant SQLite queries.
3. Dashboard _income_candidates_around eager-loads subcategory using joinedload.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

from sqlalchemy import select

from mymonee.app import create_app
from mymonee.config import Settings
from mymonee.db.models import (
    Account,
    Category,
    Subcategory,
    Transaction,
    new_id,
)
from mymonee.db.session import get_session_factory
from mymonee.services.auth import (
    change_master_pin,
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
        acc = Account(id=new_id(), name="Axis Bank", account_type="BANK", is_asset=True, is_liability=False)
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
            transaction_date=datetime(2026, 8, 31, 10, 0, tzinfo=timezone.utc),
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
