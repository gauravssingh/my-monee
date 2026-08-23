from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from mymonee.app import create_app
from mymonee.config import AppConfig, DatabaseConfig, LoggingConfig, Settings
from mymonee.db.models import Transaction, new_id
from mymonee.db.session import get_session_factory


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        app=AppConfig(data_dir=tmp_path),
        database=DatabaseConfig(filename="test.db"),
        logging=LoggingConfig(file=tmp_path / "test.log"),
    )


def test_transactions_can_be_filtered_by_inclusive_date_range(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    with get_session_factory()() as session:
        for day in (5, 10, 15):
            session.add(
                Transaction(
                    id=new_id(),
                    source="test",
                    fingerprint=f"date-filter-{day}",
                    transaction_date=datetime(2026, 8, day, 12, tzinfo=timezone.utc),
                    amount=Decimal("100"),
                    currency="INR",
                    direction="debit",
                    classification_source="test",
                    needs_review=True,
                )
            )
        session.commit()

    client = TestClient(app)
    response = client.get(
        "/api/transactions",
        params={"needs_review": True, "date_from": "2026-08-10", "date_to": "2026-08-15"},
    )

    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert [item["transaction_date"][:10] for item in response.json()["items"]] == [
        "2026-08-15",
        "2026-08-10",
    ]
