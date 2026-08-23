from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from mymonee.app import create_app
from mymonee.config import AppConfig, DatabaseConfig, LoggingConfig, Settings


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        app=AppConfig(data_dir=tmp_path),
        database=DatabaseConfig(filename="test.db"),
        logging=LoggingConfig(file=tmp_path / "test.log"),
    )


def test_classify_marks_verified_and_clears_review(tmp_path: Path) -> None:
    client = TestClient(create_app(_settings(tmp_path)))

    sample = client.post("/api/transactions/sample")
    assert sample.status_code == 200
    tx_id = sample.json()["id"]
    assert sample.json()["needs_review"] is True

    cats = client.get("/api/categories").json()["items"]
    food = next(c for c in cats if c["slug"] == "food")
    cafe = next(s for s in food["subcategories"] if s["slug"] == "cafe")

    classified = client.patch(
        f"/api/transactions/{tx_id}/classify",
        json={"category_id": food["id"], "subcategory_id": cafe["id"]},
    )
    assert classified.status_code == 200
    body = classified.json()
    assert body["category"] == "Food"
    assert body["subcategory"] == "Cafe"
    assert body["needs_review"] is False
    assert body["user_verified"] is True
    assert body["classification_source"] == "user"
    assert body["classification_confidence"] == 1.0

    review = client.get("/api/transactions", params={"needs_review": True})
    assert review.json()["total"] == 0


def test_classify_transfer_sets_flags(tmp_path: Path) -> None:
    client = TestClient(create_app(_settings(tmp_path)))
    tx_id = client.post("/api/transactions/sample").json()["id"]
    cats = client.get("/api/categories").json()["items"]
    transfers = next(c for c in cats if c["slug"] == "transfers")
    own = next(s for s in transfers["subcategories"] if s["slug"] == "own-account")

    body = client.patch(
        f"/api/transactions/{tx_id}/classify",
        json={"category_id": transfers["id"], "subcategory_id": own["id"]},
    ).json()
    assert body["is_transfer"] is True
    assert body["excludes_from_spending"] is True
    assert body["transaction_type"] == "transfer"


def test_classify_bulk(tmp_path: Path) -> None:
    client = TestClient(create_app(_settings(tmp_path)))
    ids = [client.post("/api/transactions/sample").json()["id"] for _ in range(3)]
    cats = client.get("/api/categories").json()["items"]
    food = next(c for c in cats if c["slug"] == "food")

    result = client.post(
        "/api/transactions/classify-bulk",
        json={"transaction_ids": ids, "category_id": food["id"]},
    )
    assert result.status_code == 200
    assert result.json()["updated"] == 3
    review = client.get("/api/transactions", params={"needs_review": True})
    assert review.json()["total"] == 0


def test_exclude_not_a_transaction(tmp_path: Path) -> None:
    client = TestClient(create_app(_settings(tmp_path)))
    tx_id = client.post("/api/transactions/sample").json()["id"]

    result = client.post(
        "/api/transactions/exclude",
        json={"transaction_ids": [tx_id]},
    )
    assert result.status_code == 200
    assert result.json()["updated"] == 1
    body = result.json()["items"][0]
    assert body["transaction_type"] == "not_a_transaction"
    assert body["excludes_from_spending"] is True
    assert body["needs_review"] is False
    assert body["user_verified"] is True
    assert body["category"] is None
    assert body["classification_source"] == "user"

    review = client.get("/api/transactions", params={"needs_review": True})
    assert review.json()["total"] == 0

    overview = client.get("/api/overview").json()
    assert overview["current_month_spending"] == 0
    assert overview["needs_review_count"] == 0


def test_direction_filter(tmp_path: Path) -> None:
    client = TestClient(create_app(_settings(tmp_path)))
    debit_id = client.post("/api/transactions/sample").json()["id"]

    debit_only = client.get(
        "/api/transactions",
        params={"needs_review": True, "direction": "debit"},
    )
    assert debit_only.status_code == 200
    assert debit_only.json()["total"] >= 1
    assert all(item["direction"] == "debit" for item in debit_only.json()["items"])
    assert any(item["id"] == debit_id for item in debit_only.json()["items"])

    credit_only = client.get(
        "/api/transactions",
        params={"needs_review": True, "direction": "credit"},
    )
    assert credit_only.status_code == 200
    assert all(item["direction"] == "credit" for item in credit_only.json()["items"])
    assert debit_id not in {item["id"] for item in credit_only.json()["items"]}