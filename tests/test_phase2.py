from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from google.oauth2.credentials import Credentials
from keyring.errors import KeyringError

from mymonee.app import create_app
from mymonee.config import AppConfig, DatabaseConfig, LoggingConfig, Settings
from mymonee.ingestion.gmail.oauth import is_connected
from mymonee.parsers.base import EmailContext
from mymonee.parsers.bootstrap import bootstrap_parsers
from mymonee.parsers.extract import infer_direction, parse_amount
from mymonee.parsers.generic import GenericHeuristicParser


def _test_settings(tmp_path: Path) -> Settings:
    return Settings(
        app=AppConfig(data_dir=tmp_path),
        database=DatabaseConfig(filename="test.db"),
        logging=LoggingConfig(file=tmp_path / "test.log"),
    )


def test_gmail_status_disconnected(tmp_path: Path) -> None:
    app = create_app(_test_settings(tmp_path))
    client = TestClient(app)
    with patch("mymonee.ingestion.gmail.oauth.keyring.get_password", return_value=None):
        status = client.get("/api/gmail/status")
    assert status.status_code == 200
    body = status.json()
    assert body["connected"] is False
    assert "redirect_uri" in body


def test_connection_check_refreshes_expired_access_token(tmp_path: Path) -> None:
    settings = _test_settings(tmp_path)
    refreshed = Credentials(token="new-access-token", refresh_token="refresh-token")
    with patch(
        "mymonee.ingestion.gmail.oauth.get_valid_credentials",
        return_value=refreshed,
    ) as get_valid:
        assert is_connected(settings) is True
    get_valid.assert_called_once_with(settings, refresh=True)


def test_gmail_status_handles_unavailable_keychain(tmp_path: Path) -> None:
    app = create_app(_test_settings(tmp_path))
    client = TestClient(app)
    with patch(
        "mymonee.ingestion.gmail.oauth.keyring.get_password",
        side_effect=KeyringError("unavailable"),
    ):
        response = client.get("/api/gmail/status")
    assert response.status_code == 200
    assert response.json()["connected"] is False


def test_demo_ingestion_idempotent(tmp_path: Path) -> None:
    app = create_app(_test_settings(tmp_path))
    client = TestClient(app)

    first = client.post("/api/ingestion/demo")
    assert first.status_code == 200
    body = first.json()
    assert body["status"] in {"success", "partial"}
    assert body["transactions_extracted"] >= 3
    assert body["emails_discovered"] == 4

    txs = client.get("/api/transactions")
    assert txs.json()["total"] >= 3

    second = client.post("/api/ingestion/demo")
    assert second.status_code == 200
    assert second.json()["transactions_extracted"] == 0
    assert second.json()["transactions_duplicated"] >= 3

    overview = client.get("/api/overview").json()
    assert overview["transaction_count"] >= 3
    assert overview["needs_review_count"] >= 3


def test_generic_parser_indian_formats() -> None:
    bootstrap_parsers()
    parser = GenericHeuristicParser()
    email = EmailContext(
        message_id="m1",
        thread_id="t1",
        sender="alerts@hdfcbank.net",
        subject="Rs.2,499.50 debited",
        received_at=datetime(2026, 8, 1, tzinfo=UTC),
        body_text=(
            "INR 2,499.50 debited from A/c XX8899 on 01-08-2026 "
            "towards RAZ*SWIGGY. UPI Ref: 9988776655"
        ),
    )
    assert parser.can_parse(email) > 0.5
    parsed = parser.parse(email)
    assert len(parsed) == 1
    assert parsed[0].amount == parse_amount("₹2,499.50")
    assert parsed[0].direction == "debit"
    assert parsed[0].upi_id is None
    assert parsed[0].reference_number == "9988776655"
    assert parsed[0].merchant_raw is not None


def test_infer_credit_refund() -> None:
    assert infer_direction("Refund of INR 100 credited to your account") == "credit"


def test_sync_requires_connection(tmp_path: Path) -> None:
    app = create_app(_test_settings(tmp_path))
    client = TestClient(app)
    with patch("mymonee.ingestion.gmail.oauth.keyring.get_password", return_value=None):
        response = client.post("/api/gmail/sync")
    assert response.status_code == 400


def test_merchants_exclude_transfers(tmp_path: Path) -> None:
    app = create_app(_test_settings(tmp_path))
    client = TestClient(app)

    # Ingest demo data
    client.post("/api/ingestion/demo")

    # Fetch merchants
    merchants_resp = client.get("/api/merchants")
    assert merchants_resp.status_code == 200
    items = merchants_resp.json()["items"]

    # Verify no negative or transfer amounts are counted as spend
    for m in items:
        assert m["total_spent"] >= 0
        assert m["spent_last_30d"] >= 0


def test_get_or_create_account_matches_existing_identifiers(tmp_path: Path) -> None:
    from mymonee.db.models import Account, Institution
    from mymonee.db.session import init_db, get_session_factory
    from mymonee.ingestion.pipeline import _get_or_create_account
    from mymonee.parsers.base import ParsedTransaction

    settings = _test_settings(tmp_path)
    init_db(settings)
    session_factory = get_session_factory()
    with session_factory() as session:
        inst = Institution(name="Axis Bank", institution_type="BANK")
        session.add(inst)
        session.flush()

        # Existing user-configured accounts
        cc = Account(
            name="Axis Bank Credit Card",
            institution_id=inst.id,
            account_type="CREDIT_CARD",
            card_last4="4951",
            account_number_masked="1022",
            is_liability=True,
            is_asset=False,
        )
        bank = Account(
            name="Axis Bank Savings",
            institution_id=inst.id,
            account_type="BANK",
            account_number_masked="1022",
            is_liability=False,
            is_asset=True,
        )
        session.add_all([cc, bank])
        session.commit()

        # 1. ParsedTransaction with card="4951" should match cc
        parsed_card = ParsedTransaction(
            amount=500.0,
            currency="INR",
            transaction_date=datetime(2026, 8, 1, tzinfo=UTC),
            direction="debit",
            card="4951",
            merchant_raw="SWIGGY",
        )
        resolved_cc = _get_or_create_account(session, parsed_card)
        assert resolved_cc.id == cc.id

        # 2. ParsedTransaction with account="****1022" should match existing account
        parsed_bank = ParsedTransaction(
            amount=1000.0,
            currency="INR",
            transaction_date=datetime(2026, 8, 1, tzinfo=UTC),
            direction="debit",
            account="****1022",
            merchant_raw="ZEPTO",
        )
        resolved_bank = _get_or_create_account(session, parsed_bank)
        assert resolved_bank.id in {cc.id, bank.id}

        # 3. Verify total accounts count has NOT increased
        total_accounts = session.query(Account).count()
        assert total_accounts == 2


