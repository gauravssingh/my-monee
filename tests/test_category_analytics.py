from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from mymonee.app import create_app
from mymonee.config import AppConfig, DatabaseConfig, LoggingConfig, Settings
from mymonee.db.models import Category, Merchant, MerchantAlias, Subcategory, Transaction
from mymonee.db.session import get_session_factory

IST = ZoneInfo("Asia/Kolkata")


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        app=AppConfig(data_dir=tmp_path),
        database=DatabaseConfig(filename="test.db"),
        logging=LoggingConfig(file=tmp_path / "test.log"),
    )


def test_category_analytics_grounded_in_ledger(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    client = TestClient(app)

    SessionFactory = get_session_factory()
    with SessionFactory() as session:
        # Retrieve seeded categories
        food = session.scalars(select(Category).where(Category.slug == "food")).one()
        other_cat = session.scalars(
            select(Category).where(Category.id != food.id, Category.slug != "transfers")
        ).first()
        if not other_cat:
            other_cat = Category(name="Shopping", slug="shopping_test", expense_type="living")
            session.add(other_cat)
            session.flush()
        transfers = session.scalars(select(Category).where(Category.slug == "transfers")).one()

        groceries = session.scalars(select(Subcategory).where(Subcategory.category_id == food.id, Subcategory.slug == "groceries")).first()
        if not groceries:
            groceries = Subcategory(category_id=food.id, name="Groceries", slug="groceries")
            session.add(groceries)

        delivery = session.scalars(select(Subcategory).where(Subcategory.category_id == food.id, Subcategory.slug == "delivery")).first()
        if not delivery:
            delivery = Subcategory(category_id=food.id, name="Food Delivery", slug="delivery")
            session.add(delivery)

        dining = session.scalars(select(Subcategory).where(Subcategory.category_id == food.id, Subcategory.slug == "dining")).first()
        if not dining:
            dining = Subcategory(category_id=food.id, name="Dining Out", slug="dining")
            session.add(dining)

        cc_payment = session.scalars(select(Subcategory).where(Subcategory.slug == "credit-card-payment")).first()
        if not cc_payment:
            cc_payment = Subcategory(category_id=transfers.id, name="Credit Card Payment", slug="credit-card-payment")
            session.add(cc_payment)
        session.flush()

        # Create canonical merchant
        swiggy = Merchant(display_name="Swiggy", normalized_key="swiggy")
        blinkit = Merchant(display_name="Blinkit", normalized_key="blinkit")
        session.add_all([swiggy, blinkit])
        session.flush()

        # Aug 2026 transactions
        t1 = Transaction(
            category_id=food.id,
            subcategory_id=delivery.id,
            merchant_entity_id=swiggy.id,
            merchant_normalized="Swiggy",
            amount=1200.0,
            direction="debit",
            transaction_date=datetime(2026, 8, 10, 12, 0, tzinfo=IST),
        )
        t2 = Transaction(
            category_id=food.id,
            subcategory_id=delivery.id,
            merchant_entity_id=swiggy.id,
            merchant_normalized="Swiggy Instamart",
            amount=800.0,
            direction="debit",
            transaction_date=datetime(2026, 8, 15, 14, 0, tzinfo=IST),
        )
        t3 = Transaction(
            category_id=food.id,
            subcategory_id=groceries.id,
            merchant_entity_id=blinkit.id,
            merchant_normalized="Blinkit",
            amount=2000.0,
            direction="debit",
            transaction_date=datetime(2026, 8, 20, 16, 0, tzinfo=IST),
        )
        # Excluded transactions that must NOT inflate Food analytics
        t_transfer = Transaction(
            category_id=transfers.id,
            subcategory_id=cc_payment.id,
            amount=50000.0,
            direction="debit",
            is_transfer=True,
            transaction_date=datetime(2026, 8, 5, 10, 0, tzinfo=IST),
        )
        t_duplicate = Transaction(
            category_id=food.id,
            subcategory_id=dining.id,
            amount=9999.0,
            direction="debit",
            is_duplicate=True,
            transaction_date=datetime(2026, 8, 12, 19, 0, tzinfo=IST),
        )
        t_credit = Transaction(
            category_id=food.id,
            subcategory_id=dining.id,
            amount=500.0,
            direction="credit",
            transaction_date=datetime(2026, 8, 18, 11, 0, tzinfo=IST),
        )

        # July 2026 transaction (previous month)
        t_prev = Transaction(
            category_id=food.id,
            subcategory_id=groceries.id,
            merchant_entity_id=blinkit.id,
            merchant_normalized="Blinkit",
            amount=3000.0,
            direction="debit",
            transaction_date=datetime(2026, 7, 10, 10, 0, tzinfo=IST),
        )

        # Non-food living spend in Aug 2026
        t_transport = Transaction(
            category_id=other_cat.id,
            amount=6000.0,
            direction="debit",
            transaction_date=datetime(2026, 8, 2, 9, 0, tzinfo=IST),
        )

        session.add_all([t1, t2, t3, t_transfer, t_duplicate, t_credit, t_prev, t_transport])
        session.commit()
        food_id = food.id

    # Query 1m (Aug 2026)
    res_1m = client.get(f"/api/analytics/category/{food_id}?range=1m&year=2026&month=8")
    assert res_1m.status_code == 200
    data_1m = res_1m.json()

    # Total Food spend in Aug 2026 should be 1200 + 800 + 2000 = 4000
    assert data_1m["summary"]["current_month_spend"] == 4000.0
    assert data_1m["summary"]["period_total_spend"] == 4000.0
    assert data_1m["summary"]["transaction_count"] == 3
    assert data_1m["summary"]["avg_ticket"] == round(4000.0 / 3, 2)
    assert data_1m["summary"]["median_ticket"] == 1200.0

    # Total Living spend in Aug 2026 = 4000 (Food) + 6000 (Transport) = 10000
    assert data_1m["summary"]["share_of_living_spend"] == 0.4  # 40%

    # MoM delta vs July 2026 (3000): (4000 - 3000) / 3000 = +33.3%
    assert data_1m["summary"]["current_month_mom_change_pct"] == 33.3

    # Canonical merchant rollup: Swiggy should combine t1 (1200) + t2 (800) = 2000 (50%)
    merchants = data_1m["merchants"]
    assert len(merchants) == 2
    swiggy_entry = next(m for m in merchants if m["name"] == "Swiggy")
    assert swiggy_entry["spend"] == 2000.0
    assert swiggy_entry["transaction_count"] == 2
    assert swiggy_entry["share_of_category"] == 0.5

    # Subcategories breakdown
    subs = data_1m["subcategories"]
    delivery_sub = next(s for s in subs if s["name"] == "Food Delivery")
    assert delivery_sub["spend"] == 2000.0
    assert delivery_sub["transaction_count"] == 2
    assert delivery_sub["share_of_category"] == 0.5

    # Multi-month trend (6m)
    res_6m = client.get(f"/api/analytics/category/{food_id}?range=6m&year=2026&month=8")
    assert res_6m.status_code == 200
    data_6m = res_6m.json()
    assert data_6m["period"]["months"] == 6
    assert data_6m["summary"]["period_total_spend"] == 7000.0  # 4000 (Aug) + 3000 (Jul)
    assert len(data_6m["trend"]) == 6

    # Insights present
    assert isinstance(data_6m["insights"], list)
