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


def test_categories_list_and_custom_crud(tmp_path: Path) -> None:
    client = TestClient(create_app(_settings(tmp_path)))
    listed = client.get("/api/categories")
    assert listed.status_code == 200
    names = {c["name"] for c in listed.json()["items"]}
    assert "Food" in names

    created = client.post("/api/categories", json={"name": "Pets"})
    assert created.status_code == 200
    cat_id = created.json()["id"]

    sub = client.post(f"/api/categories/{cat_id}/subcategories", json={"name": "Vet"})
    assert sub.status_code == 200

    deleted = client.delete(f"/api/categories/{cat_id}")
    # has subcategory but unused — delete category removes subs
    assert deleted.status_code == 200


def test_transactions_category_filtering_by_name_and_slug(tmp_path: Path) -> None:
    client = TestClient(create_app(_settings(tmp_path)))
    
    # 1. Fetch categories to find Shopping
    cats_resp = client.get("/api/categories")
    assert cats_resp.status_code == 200
    shopping_cat = next((c for c in cats_resp.json()["items"] if c["name"].lower() == "shopping"), None)
    assert shopping_cat is not None
    shopping_id = shopping_cat["id"]

    # 2. Filter transactions by category name "Shopping"
    res_name = client.get("/api/transactions", params={"category_id": "Shopping"})
    assert res_name.status_code == 200

    # 3. Filter transactions by category slug "shopping"
    res_slug = client.get("/api/transactions", params={"category_id": "shopping"})
    assert res_slug.status_code == 200

    # 4. Filter transactions by category UUID
    res_id = client.get("/api/transactions", params={"category_id": shopping_id})
    assert res_id.status_code == 200

    # 5. Filter transactions via category_ids array
    res_multi = client.get("/api/transactions", params={"category_ids": ["Shopping"]})
    assert res_multi.status_code == 200
