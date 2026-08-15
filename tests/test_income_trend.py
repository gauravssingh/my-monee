from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from expense_tracker.config import AppConfig, DatabaseConfig, LoggingConfig, Settings
from expense_tracker.db.models import Transaction, Category, Subcategory, new_id
from expense_tracker.db.session import get_session_factory, init_db
from sqlalchemy import select
from expense_tracker.services.dashboard import (
    _pct_change,
    get_overview,
    income_trend,
    salary_pay_period,
)


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        app=AppConfig(data_dir=tmp_path),
        database=DatabaseConfig(filename="test.db"),
        logging=LoggingConfig(file=tmp_path / "test.log"),
    )


def test_pct_change() -> None:
    assert _pct_change(110, 100) == 10.0
    assert _pct_change(90, 100) == -10.0
    assert _pct_change(50, 0) is None


def test_salary_pay_period_mapping() -> None:
    # Typical end-of-month credit → next month
    assert salary_pay_period(datetime(2026, 7, 31, tzinfo=timezone.utc)) == (2026, 8)
    assert salary_pay_period(datetime(2026, 2, 27, tzinfo=timezone.utc)) == (2026, 3)
    assert salary_pay_period(datetime(2026, 12, 30, tzinfo=timezone.utc)) == (2027, 1)
    # Delayed early-month credit → current month
    assert salary_pay_period(datetime(2026, 8, 1, tzinfo=timezone.utc)) == (2026, 8)
    assert salary_pay_period(datetime(2026, 8, 2, tzinfo=timezone.utc)) == (2026, 8)


def test_overview_income_uses_pay_period(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    init_db(settings)
    session = get_session_factory()()
    try:
        inc_cat = session.scalar(select(Category).where(Category.slug == "income"))
        sal_subcat = session.scalar(select(Subcategory).where(Subcategory.slug == "salary"))

        # Jun 30 credit → July salary
        session.add(
            Transaction(
                id=new_id(),
                source="test",
                fingerprint="inc-jun",
                transaction_date=datetime(2026, 6, 30, tzinfo=timezone.utc),
                amount=Decimal("100000"),
                currency="INR",
                direction="credit",
                transaction_type="income",
                excludes_from_spending=True,
                is_transfer=False,
                is_refund=False,
                classification_source="rule",
                category_id=inc_cat.id,
                subcategory_id=sal_subcat.id,
            )
        )
        # Jul 31 credit → August salary
        session.add(
            Transaction(
                id=new_id(),
                source="test",
                fingerprint="inc-jul",
                transaction_date=datetime(2026, 7, 31, tzinfo=timezone.utc),
                amount=Decimal("110000"),
                currency="INR",
                direction="credit",
                transaction_type="income",
                excludes_from_spending=True,
                is_transfer=False,
                is_refund=False,
                classification_source="rule",
                category_id=inc_cat.id,
                subcategory_id=sal_subcat.id,
            )
        )
        # Transfer must not count
        session.add(
            Transaction(
                id=new_id(),
                source="test",
                fingerprint="xfer-aug",
                transaction_date=datetime(2026, 8, 6, tzinfo=timezone.utc),
                amount=Decimal("50000"),
                currency="INR",
                direction="credit",
                transaction_type="transfer",
                excludes_from_spending=True,
                is_transfer=True,
                is_refund=False,
                classification_source="rule",
            )
        )
        session.commit()

        overview = get_overview(session, now=datetime(2026, 8, 12, tzinfo=timezone.utc))
        assert overview["summary"]["income"] == 110000.0
        assert overview["month_comparison"]["previous_income"] == 100000.0
        assert overview["month_comparison"]["income_change_pct"] == 10.0

        trend = income_trend(session, months=6, now=datetime(2026, 8, 12, tzinfo=timezone.utc))
        assert len(trend["points"]) == 6
        assert trend["points"][-1]["label"] == "Aug 2026"
        assert trend["points"][-1]["income"] == 110000.0
        assert trend["points"][-2]["income"] == 100000.0
    finally:
        session.close()


def test_delayed_salary_on_second_counts_current_month(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    init_db(settings)
    session = get_session_factory()()
    try:
        session.add(
            Transaction(
                id=new_id(),
                source="test",
                fingerprint="inc-aug2",
                transaction_date=datetime(2026, 8, 2, tzinfo=timezone.utc),
                amount=Decimal("282330"),
                currency="INR",
                direction="credit",
                transaction_type="income",
                excludes_from_spending=True,
                classification_source="rule",
            )
        )
        session.commit()
        overview = get_overview(session, now=datetime(2026, 8, 12, tzinfo=timezone.utc))
        assert overview["summary"]["income"] == 282330.0
    finally:
        session.close()
