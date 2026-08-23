from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from expense_tracker.app import create_app
from expense_tracker.config import AppConfig, DatabaseConfig, LoggingConfig, Settings
from expense_tracker.db.models import (
    Account,
    Category,
    IncomeSource,
    Institution,
    RecurringTransaction,
    Transaction,
)
from expense_tracker.db.session import get_session_factory
from expense_tracker.services.onboarding import (
    complete_onboarding,
    discover_onboarding_entities,
    get_onboarding_status,
    reset_onboarding,
)


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        app=AppConfig(data_dir=tmp_path),
        database=DatabaseConfig(filename="test_onboarding.db"),
        logging=LoggingConfig(file=tmp_path / "test.log"),
    )


def test_onboarding_discovery_and_completion_flow(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)
    session_factory = get_session_factory()

    with session_factory() as session:
        # Seed test institution and account
        inst = Institution(name="HDFC Bank", institution_type="BANK")
        session.add(inst)
        session.flush()

        acc = Account(
            name="HDFC Salary Account",
            institution_id=inst.id,
            account_type="BANK",
            is_asset=True,
            is_liability=False,
            account_number_masked="XX1234",
        )
        session.add(acc)

        # Seed salary transaction
        tx_salary = Transaction(
            source="gmail:hdfc",
            amount=Decimal("175000.00"),
            currency="INR",
            direction="credit",
            merchant_raw="ACME Corp Salary Deposit",
            merchant_normalized="ACME Corp",
            transaction_date=datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc),
            excludes_from_spending=True,
        )

        # Seed recurring transaction
        rec = RecurringTransaction(
            name="ACT Broadband",
            expected_amount=Decimal("2948.82"),
            frequency="monthly",
            expected_day=5,
            status="active",
        )
        session.add_all([tx_salary, rec])
        session.commit()

    # 1. Initial Status check
    status_resp = client.get("/api/onboarding/status")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["completed"] is False
    assert status_data["accounts_configured"] >= 1

    # 2. Discover endpoint
    disc_resp = client.get("/api/onboarding/discover")
    assert disc_resp.status_code == 200
    disc_data = disc_resp.json()
    assert len(disc_data["accounts"]) >= 1
    assert len(disc_data["income_sources"]) >= 1
    assert disc_data["income_sources"][0]["amount"] == 175000.0
    assert len(disc_data["recurring"]) >= 1
    assert disc_data["recurring"][0]["name"] == "ACT Broadband"

    # 3. Complete Onboarding
    complete_resp = client.post(
        "/api/onboarding/complete",
        json={
            "primary_salary": {
                "name": "ACME Corp Salary",
                "expected_amount": 175000.0,
                "frequency": "monthly",
            },
            "recurring_items": [
                {
                    "name": "ACT Broadband",
                    "expected_amount": 2948.82,
                    "frequency": "monthly",
                    "expected_day": 5,
                },
                {
                    "name": "House Maintenance",
                    "expected_amount": 7080.0,
                    "frequency": "monthly",
                    "expected_day": 1,
                },
            ],
        },
    )
    assert complete_resp.status_code == 200
    comp_data = complete_resp.json()
    assert comp_data["completed"] is True

    # Verify status is now completed
    status_after = client.get("/api/onboarding/status").json()
    assert status_after["completed"] is True
    assert status_after["income_sources_configured"] >= 1

    # Verify House Maintenance was created
    with session_factory() as session:
        maint = session.scalar(
            select(RecurringTransaction).where(RecurringTransaction.name == "House Maintenance")
        )
        assert maint is not None
        assert float(maint.expected_amount) == 7080.0

    # 4. Test Reset endpoint
    reset_resp = client.post("/api/onboarding/reset")
    assert reset_resp.status_code == 200
    assert reset_resp.json()["completed"] is False
