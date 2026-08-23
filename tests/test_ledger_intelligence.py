from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from expense_tracker.app import create_app
from expense_tracker.classification.enrichment import apply_parsed_enrichment
from expense_tracker.classification.rules import (
    apply_classification_rule_to_transaction,
    find_matching_rule,
    upsert_user_classification_rule,
)
from expense_tracker.config import AppConfig, DatabaseConfig, LoggingConfig, Settings
from expense_tracker.db.models import (
    Account,
    Category,
    ClassificationRule,
    Institution,
    Subcategory,
    Transaction,
    TransactionLink,
    utcnow,
)
from expense_tracker.db.session import get_session_factory, init_db
from expense_tracker.parsers.base import ParsedTransaction
from expense_tracker.services.reconciliation import (
    pair_cross_account_transfers,
    pair_refunds,
    run_full_reconciliation,
)
from expense_tracker.services.transactions import classify_transaction


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        app=AppConfig(data_dir=tmp_path),
        database=DatabaseConfig(filename="test_intelligence.db"),
        logging=LoggingConfig(file=tmp_path / "test.log"),
    )


def test_user_rule_persistence_and_enrichment_precedence(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)
    session_factory = get_session_factory()

    # 1. Create a transaction for a merchant "Swiggy"
    with session_factory() as session:
        food_cat = session.scalar(select(Category).where(Category.slug == "food"))
        restaurant_sub = session.scalar(
            select(Subcategory).where(Subcategory.slug == "restaurants", Subcategory.category_id == food_cat.id)
        )
        food_id = str(food_cat.id)
        sub_id = str(restaurant_sub.id)

        tx1 = Transaction(
            source="gmail:hdfc",
            amount=Decimal("450.00"),
            currency="INR",
            direction="debit",
            merchant_raw="Swiggy Bangalore",
            merchant_normalized="Swiggy",
            transaction_date=datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc),
            needs_review=True,
        )
        session.add(tx1)
        session.commit()
        tx1_id = tx1.id

    # 2. User classifies tx1 with create_rule=True
    resp = client.patch(
        f"/api/transactions/{tx1_id}/classify",
        json={
            "category_id": food_id,
            "subcategory_id": sub_id,
            "create_rule": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["category"] == "Food"
    assert data["subcategory"] == "Restaurants"
    assert data["needs_review"] is False
    assert data["classification_source"] == "user"
    assert "user_rule" in data["classification_signals"]["rule"]

    # 3. Ingest a NEW transaction for "Swiggy" without explicit category
    with session_factory() as session:
        tx2 = Transaction(
            source="gmail:axis",
            amount=Decimal("720.00"),
            currency="INR",
            direction="debit",
            merchant_raw="Swiggy Koramangala",
            merchant_normalized="Swiggy",
            transaction_date=datetime(2026, 8, 12, 14, 0, tzinfo=timezone.utc),
            needs_review=True,
        )
        session.add(tx2)
        session.flush()

        parsed = ParsedTransaction(
            transaction_date=datetime(2026, 8, 12, 14, 0, tzinfo=timezone.utc),
            amount=Decimal("720.00"),
            currency="INR",
            direction="debit",
            merchant_raw="Swiggy Koramangala",
        )

        # Apply enrichment
        apply_parsed_enrichment(session, tx2, parsed)
        session.commit()

        # tx2 should have matched the persistent user rule with 100% confidence!
        assert tx2.category_id == food_id
        assert tx2.subcategory_id == sub_id
        assert tx2.classification_source == "user"
        assert tx2.classification_confidence == 1.0
        assert tx2.needs_review is False
        assert tx2.classification_signals["rule"] == "user_rule"


def test_refund_pairing_engine(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)
    session_factory = get_session_factory()

    with session_factory() as session:
        # Original purchase: ₹1,500 Amazon
        orig = Transaction(
            source="gmail:scapia",
            amount=Decimal("1500.00"),
            currency="INR",
            direction="debit",
            merchant_raw="Amazon India",
            merchant_normalized="Amazon",
            description="Amazon shopping purchase",
            transaction_date=datetime(2026, 8, 5, 10, 0, tzinfo=timezone.utc),
            needs_review=False,
        )
        session.add(orig)
        session.flush()

        # Refund credit: ₹1,500 Amazon
        ref = Transaction(
            source="gmail:scapia",
            amount=Decimal("1500.00"),
            currency="INR",
            direction="credit",
            merchant_raw="Amazon India Refund",
            merchant_normalized="Amazon",
            description="Refund credited for Amazon purchase",
            transaction_date=datetime(2026, 8, 7, 11, 0, tzinfo=timezone.utc),
            is_refund=True,
            needs_review=True,
        )
        session.add(ref)
        session.commit()

        orig_id = orig.id
        ref_id = ref.id

        # Run refund pairing
        paired = pair_refunds(session)
        session.commit()

        assert len(paired) == 1
        link = paired[0]
        assert link.from_transaction_id == ref_id
        assert link.to_transaction_id == orig_id
        assert link.kind == "refund_of"

        # Verify refund properties
        ref_tx = session.get(Transaction, ref_id)
        assert ref_tx.is_refund is True
        assert ref_tx.excludes_from_spending is True

    # Check links API route
    resp = client.get(f"/api/transactions/{ref_id}/links")
    assert resp.status_code == 200
    links_data = resp.json()["links"]
    assert len(links_data) == 1
    assert links_data[0]["kind"] == "refund_of"
    assert links_data[0]["related_transaction"]["id"] == orig_id


def test_cross_account_transfer_matching(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)
    session_factory = get_session_factory()

    with session_factory() as session:
        inst = Institution(name="Axis Bank", institution_type="BANK")
        session.add(inst)
        session.flush()

        bank_acc = Account(
            name="Axis Bank Account",
            institution_id=inst.id,
            account_type="BANK",
            is_asset=True,
            is_liability=False,
        )
        cc_acc = Account(
            name="Scapia Credit Card",
            institution_id=inst.id,
            account_type="CREDIT_CARD",
            is_asset=False,
            is_liability=True,
        )
        session.add_all([bank_acc, cc_acc])
        session.flush()

        # Bank Debit: Paid Credit Card Bill
        bank_debit = Transaction(
            source="gmail:axis",
            amount=Decimal("35000.00"),
            currency="INR",
            direction="debit",
            account="Axis Bank Account",
            merchant_raw="CRED Card Payment",
            description="Payment towards Credit Card bill",
            transaction_date=datetime(2026, 8, 15, 10, 0, tzinfo=timezone.utc),
            needs_review=True,
        )

        # CC Credit: Payment Received
        cc_credit = Transaction(
            source="gmail:scapia",
            amount=Decimal("35000.00"),
            currency="INR",
            direction="credit",
            account="Scapia Credit Card",
            merchant_raw="Credit Card Payment Received",
            description="Thank you for your payment of Rs 35000",
            transaction_date=datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc),
            needs_review=True,
        )
        session.add_all([bank_debit, cc_credit])
        session.commit()

        bank_id = bank_debit.id
        cc_id = cc_credit.id

        # Run reconciliation
        res = run_full_reconciliation(session)
        assert res["transfers_paired"] >= 1

        db_bank = session.get(Transaction, bank_id)
        db_cc = session.get(Transaction, cc_id)

        assert db_bank.is_transfer is True
        assert db_bank.excludes_from_spending is True
        assert db_cc.is_transfer is True
        assert db_cc.excludes_from_spending is True


def test_classify_apply_to_past_backfill(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)
    session_factory = get_session_factory()

    with session_factory() as session:
        food_cat = session.scalar(select(Category).where(Category.slug == "food"))
        cafe_sub = session.scalar(
            select(Subcategory).where(Subcategory.slug == "cafe", Subcategory.category_id == food_cat.id)
        )
        food_id = str(food_cat.id)
        sub_id = str(cafe_sub.id)

        # Create 3 unreviewed Starbucks transactions
        txs = [
            Transaction(
                source="gmail:hdfc",
                amount=Decimal("350.00"),
                currency="INR",
                direction="debit",
                merchant_raw="Starbucks Coffee Indiranagar",
                merchant_normalized="Starbucks",
                transaction_date=datetime(2026, 8, i, 10, 0, tzinfo=timezone.utc),
                needs_review=True,
                user_verified=False,
            )
            for i in range(1, 4)
        ]
        session.add_all(txs)
        session.commit()

        tx1_id = txs[0].id
        tx2_id = txs[1].id
        tx3_id = txs[2].id

    # Classify the first one and set apply_to_past=True
    resp = client.patch(
        f"/api/transactions/{tx1_id}/classify",
        json={
            "category_id": food_id,
            "subcategory_id": sub_id,
            "create_rule": True,
            "apply_to_past": True,
        },
    )
    assert resp.status_code == 200

    # Verify tx2 and tx3 were backfilled automatically!
    with session_factory() as session:
        t2 = session.get(Transaction, tx2_id)
        t3 = session.get(Transaction, tx3_id)

        assert t2.category_id == food_id
        assert t2.subcategory_id == sub_id
        assert t2.user_verified is True
        assert t2.needs_review is False

        assert t3.category_id == food_id
        assert t3.subcategory_id == sub_id
        assert t3.user_verified is True
        assert t3.needs_review is False
