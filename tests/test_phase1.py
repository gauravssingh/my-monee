from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from expense_tracker.app import create_app
from expense_tracker.config import Settings, AppConfig, DatabaseConfig, LoggingConfig


def _test_settings(tmp_path: Path) -> Settings:
    return Settings(
        app=AppConfig(data_dir=tmp_path),
        database=DatabaseConfig(filename="test.db"),
        logging=LoggingConfig(file=tmp_path / "test.log"),
    )


def test_health_and_overview(tmp_path: Path) -> None:
    settings = _test_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    overview = client.get("/api/overview")
    assert overview.status_code == 200
    body = overview.json()
    assert body["current_month_spending"] == 0
    assert body["transaction_count"] == 0


def test_sample_transaction_and_system(tmp_path: Path) -> None:
    settings = _test_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    sample = client.post("/api/transactions/sample")
    assert sample.status_code == 200
    assert sample.json()["merchant_normalized"] == "Sample Coffee Shop"

    txs = client.get("/api/transactions")
    assert txs.status_code == 200
    assert txs.json()["total"] == 1

    review = client.get("/api/transactions", params={"needs_review": True})
    assert review.json()["total"] == 1

    system = client.get("/api/system/status")
    assert system.status_code == 200
    assert system.json()["database"]["transaction_count"] == 1
    assert system.json()["app"]["allow_external_ai"] is False


def test_categories_seeded(tmp_path: Path) -> None:
    settings = _test_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)
    cats = client.get("/api/overview/by-category")
    assert cats.status_code == 200
    names = {item["category"] for item in cats.json()["items"]}
    assert "Food" in names
    assert "Shopping" in names
