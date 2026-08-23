from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from expense_tracker.config import AppConfig, DatabaseConfig, LoggingConfig, Settings
from expense_tracker.db.models import Category, Subcategory, Transaction, new_id
from expense_tracker.db.session import get_session_factory, init_db
from expense_tracker.services.dashboard import get_overview


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        app=AppConfig(data_dir=tmp_path),
        database=DatabaseConfig(filename="test_cc_exclude.db"),
        logging=LoggingConfig(file=tmp_path / "test.log"),
    )


def test_overview_excludes_credit_card_bills_and_includes_purchases(tmp_path: Path) -> None:
    """
    Ensure credit card purchases are counted in overview spend, but credit card
    bill payments (settlement transfers) are excluded to prevent double-counting.
    """
    settings = _settings(tmp_path)
    init_db(settings)
    session = get_session_factory()()
    try:
        food_cat = session.scalar(select(Category).where(Category.slug == "food"))
        groceries_sub = session.scalar(select(Subcategory).where(Subcategory.slug == "groceries"))
        transfers_cat = session.scalar(select(Category).where(Category.slug == "transfers"))
        cc_sub = session.scalar(select(Subcategory).where(Subcategory.slug == "credit-card-payment"))

        # 1. Individual purchase on Credit Card: ₹2,000 BigBasket -> EXPENSE (included)
        session.add(
            Transaction(
                id=new_id(),
                source="test",
                fingerprint="cc-purchase-1",
                transaction_date=datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc),
                amount=Decimal("2000.00"),
                currency="INR",
                direction="debit",
                transaction_type="purchase",
                merchant_raw="BigBasket",
                merchant_normalized="BigBasket",
                account="Scapia VISA Credit Card (XX0863)",
                card="0863",
                is_transfer=False,
                is_refund=False,
                excludes_from_spending=False,
                category_id=food_cat.id,
                subcategory_id=groceries_sub.id,
            )
        )

        # 2. Another purchase on Credit Card: ₹3,000 Amazon -> EXPENSE (included)
        session.add(
            Transaction(
                id=new_id(),
                source="test",
                fingerprint="cc-purchase-2",
                transaction_date=datetime(2026, 8, 12, 14, 0, tzinfo=timezone.utc),
                amount=Decimal("3000.00"),
                currency="INR",
                direction="debit",
                transaction_type="purchase",
                merchant_raw="Amazon",
                merchant_normalized="Amazon",
                account="Scapia VISA Credit Card (XX0863)",
                card="0863",
                is_transfer=False,
                is_refund=False,
                excludes_from_spending=False,
                category_id=food_cat.id,
                subcategory_id=groceries_sub.id,
            )
        )

        # 3. Credit card bill payment from savings account: ₹5,000 Axis Bank -> TRANSFER (excluded)
        session.add(
            Transaction(
                id=new_id(),
                source="test",
                fingerprint="cc-bill-pay-bank",
                transaction_date=datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc),
                amount=Decimal("5000.00"),
                currency="INR",
                direction="debit",
                transaction_type="transfer",
                merchant_raw="Scapia",
                merchant_normalized="Scapia",
                account="Axis Bank (XX1022)",
                is_transfer=True,
                is_refund=False,
                excludes_from_spending=True,
                category_id=transfers_cat.id,
                subcategory_id=cc_sub.id,
            )
        )

        # 4. Credit card bill payment receipt on card side: ₹5,000 Scapia -> TRANSFER (excluded)
        session.add(
            Transaction(
                id=new_id(),
                source="test",
                fingerprint="cc-bill-pay-card",
                transaction_date=datetime(2026, 8, 20, 10, 1, tzinfo=timezone.utc),
                amount=Decimal("5000.00"),
                currency="INR",
                direction="credit",
                transaction_type="transfer",
                merchant_raw="Credit card payment",
                account="Scapia VISA Credit Card (XX0863)",
                card="0863",
                is_transfer=True,
                is_refund=False,
                excludes_from_spending=True,
                category_id=transfers_cat.id,
                subcategory_id=cc_sub.id,
            )
        )

        # 5. Non-transaction statement notice: ₹5,000 Scapia Statement -> NOT_A_TX (excluded)
        session.add(
            Transaction(
                id=new_id(),
                source="test",
                fingerprint="cc-stmt-notice",
                transaction_date=datetime(2026, 8, 1, 9, 0, tzinfo=timezone.utc),
                amount=Decimal("5000.00"),
                currency="INR",
                direction="debit",
                transaction_type="not_a_transaction",
                is_transfer=False,
                is_refund=False,
                excludes_from_spending=True,
            )
        )

        session.commit()

        # Fetch overview for August 2026
        ov = get_overview(session, year=2026, month=8)

        # Total spend should be ₹5,000 (2000 + 3000), NOT ₹10,000 or ₹15,000
        assert ov["summary"]["spent"] == 5000.0
        assert ov["summary"]["transaction_count"] == 2
        assert ov["summary"]["debit_count"] == 2

        # Verify largest transactions only have the purchases
        largest_amounts = [t["amount"] for t in ov["largest_transactions"]]
        assert largest_amounts == [3000.0, 2000.0]

    finally:
        session.close()
