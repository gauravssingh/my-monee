"""Tests for fuzzy deduplication and spending anomaly detection engines."""

from __future__ import annotations

from datetime import timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from expense_tracker.app import create_app
from expense_tracker.config import Settings
from expense_tracker.db.models import (
    Category,
    RecurringTransaction,
    Transaction,
    utcnow,
)
from expense_tracker.services.anomalies import detect_spending_anomalies
from expense_tracker.services.deduplication import (
    find_duplicate_candidates,
    merge_duplicate_transactions,
    unmark_duplicate_transaction,
)


def test_fuzzy_duplicate_detection(db_session: Session):
    now = utcnow()
    # 1. Primary transaction from Bank SMS email
    t1 = Transaction(
        source="axis_bank_email",
        amount=1499.0,
        currency="INR",
        direction="debit",
        merchant_raw="SWIGGY BANGALORE IN",
        merchant_normalized="Swiggy",
        description="Debit alert for Swiggy",
        reference_number="AX1234567890",
        transaction_date=now,
    )
    # 2. Duplicate transaction from PhonePe confirmation email (arrived 30 seconds later)
    t2 = Transaction(
        source="phonepe_email",
        amount=1499.0,
        currency="INR",
        direction="debit",
        merchant_raw="Swiggy Delivery Order",
        merchant_normalized="Swiggy",
        description="Paid on Swiggy via PhonePe UPI",
        reference_number="UPI-AX1234567890",
        transaction_date=now + timedelta(seconds=30),
    )
    db_session.add_all([t1, t2])
    db_session.commit()

    candidates = find_duplicate_candidates(db_session, lookback_days=30)
    assert len(candidates) >= 1
    dup_pair = next(c for c in candidates if c.amount == 1499.0)
    assert dup_pair.confidence >= 0.70
    assert "Swiggy" in str(dup_pair.primary_merchant)


def test_merge_and_unmark_duplicate(db_session: Session):
    now = utcnow()
    t1 = Transaction(
        source="bank",
        amount=500.0,
        currency="INR",
        direction="debit",
        merchant_raw="Uber Rides",
        transaction_date=now,
    )
    t2 = Transaction(
        source="upi",
        amount=500.0,
        currency="INR",
        direction="debit",
        merchant_raw="Uber India",
        transaction_date=now + timedelta(minutes=1),
    )
    db_session.add_all([t1, t2])
    db_session.commit()

    # Merge t2 into t1
    merge_res = merge_duplicate_transactions(db_session, t1.id, t2.id)
    assert merge_res["success"] is True

    # Check t2 state
    db_session.refresh(t2)
    assert t2.is_duplicate is True
    assert t2.parent_transaction_id == t1.id
    assert t2.excludes_from_spending is True

    # Unmark t2
    unmark_res = unmark_duplicate_transaction(db_session, t2.id)
    assert unmark_res["success"] is True
    db_session.refresh(t2)
    assert t2.is_duplicate is False
    assert t2.excludes_from_spending is False


def test_spending_anomalies_detection(db_session: Session):
    now = utcnow()
    # 1. Setup category and normal transactions
    cat = Category(name="Dining & Food", slug="dining_food", sort_order=1)
    db_session.add(cat)
    db_session.commit()

    # Add historical food debits with average ₹400
    for i in range(10):
        db_session.add(
            Transaction(
                source="test",
                amount=400.0,
                currency="INR",
                direction="debit",
                category_id=cat.id,
                merchant_raw=f"Cafe {i}",
                transaction_date=now - timedelta(days=i * 2 + 5),
            )
        )

    # 2. Add an outlier spike (₹8,500 restaurant dinner > 4x average)
    spike_tx = Transaction(
        source="test",
        amount=8500.0,
        currency="INR",
        direction="debit",
        category_id=cat.id,
        merchant_raw="Fine Dining Luxury Restaurant",
        transaction_date=now - timedelta(days=1),
    )
    db_session.add(spike_tx)

    # 3. Add a subscription price surge
    rec = RecurringTransaction(
        name="Netflix Subscription",
        expected_amount=649.0,
        frequency="monthly",
        expected_day=15,
        status="active",
    )
    db_session.add(rec)
    db_session.commit()

    # Billed ₹799 (+23% hike)
    hike_tx = Transaction(
        source="card",
        amount=799.0,
        currency="INR",
        direction="debit",
        merchant_raw="NETFLIX MUMBAI",
        merchant_normalized="Netflix",
        transaction_date=now - timedelta(days=2),
    )
    db_session.add(hike_tx)
    db_session.commit()

    alerts = detect_spending_anomalies(db_session, lookback_days=30)
    assert len(alerts) >= 2
    types = {a.anomaly_type for a in alerts}
    assert "SPENDING_SPIKE" in types
    assert "SUBSCRIPTION_HIKE" in types


def test_intelligence_api_routes(test_settings: Settings, db_session: Session):
    app = create_app(test_settings)
    client = TestClient(app)

    now = utcnow()
    t1 = Transaction(
        source="bank",
        amount=250.0,
        currency="INR",
        direction="debit",
        merchant_raw="Coffee Shop",
        merchant_normalized="Coffee Shop",
        transaction_date=now,
    )
    t2 = Transaction(
        source="upi",
        amount=250.0,
        currency="INR",
        direction="debit",
        merchant_raw="Coffee Shop",
        merchant_normalized="Coffee Shop",
        transaction_date=now + timedelta(seconds=10),
    )
    db_session.add_all([t1, t2])
    db_session.commit()

    # 1. GET /api/intelligence/duplicates
    resp = client.get("/api/intelligence/duplicates")
    assert resp.status_code == 200
    dups = resp.json()
    assert len(dups) >= 1

    # 2. POST /api/intelligence/duplicates/merge
    resp = client.post(
        "/api/intelligence/duplicates/merge",
        json={"primary_id": t1.id, "duplicate_id": t2.id},
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # 3. GET /api/intelligence/anomalies
    resp = client.get("/api/intelligence/anomalies")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
