"""Tests for Classification Rules Management API (/api/rules)."""

from __future__ import annotations

from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy import select

from mymonee.app import create_app
from mymonee.config import Settings
from mymonee.db.models import Category, ClassificationRule, Subcategory, new_id
from mymonee.db.session import get_session_factory


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        app={"data_dir": tmp_path, "name": "test-mymonee"},
        database={"filename": "test.db", "echo": False},
        privacy={"allow_external_ai": False},
    )


def test_rules_api_crud(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)
    session_factory = get_session_factory()

    # 1. Initially empty
    res = client.get("/api/rules")
    assert res.status_code == 200
    data = res.json()
    assert data["count"] == 0
    assert data["rules"] == []

    # 2. Seed a category and rule in database
    with session_factory() as session:
        food = session.scalar(select(Category).where(Category.slug == "food"))
        assert food is not None
        groceries = session.scalar(select(Subcategory).where(Subcategory.slug == "groceries"))
        assert groceries is not None

        rule = ClassificationRule(
            id=new_id(),
            name="Swiggy Instamart Rule",
            merchant_normalized="Swiggy Instamart",
            category_id=food.id,
            subcategory_id=groceries.id,
            priority=150,
            is_active=True,
            hit_count=8,
            source="user",
        )
        session.add(rule)
        session.commit()
        rule_id = rule.id

    # 3. GET /api/rules returns the rule
    res = client.get("/api/rules")
    assert res.status_code == 200
    data = res.json()
    assert data["count"] == 1
    item = data["rules"][0]
    assert item["id"] == rule_id
    assert item["merchant_normalized"] == "Swiggy Instamart"
    assert item["category_name"] == "Food"
    assert item["subcategory_name"] == "Groceries"
    assert item["hit_count"] == 8
    assert item["is_active"] is True

    # 4. PATCH /api/rules/{rule_id} -> toggle active
    res = client.patch(f"/api/rules/{rule_id}", json={"is_active": False})
    assert res.status_code == 200
    assert res.json()["is_active"] is False

    # Check updated state
    res = client.get("/api/rules")
    assert res.json()["rules"][0]["is_active"] is False

    # 5. DELETE /api/rules/{rule_id}
    res = client.delete(f"/api/rules/{rule_id}")
    assert res.status_code == 200
    assert res.json()["ok"] is True

    # Verify deleted
    res = client.get("/api/rules")
    assert res.json()["count"] == 0
