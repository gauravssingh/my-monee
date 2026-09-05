"""Comprehensive domain tests for MyMonee Agent Service capabilities."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from mymonee.config import Settings
from mymonee.db.models import Category, Subcategory, Transaction, new_id, utcnow
from mymonee.mcp.principal import create_agent_principal
from mymonee.mcp.service import AgentService


@pytest.fixture
def agent_service(db_session: Session, test_settings: Settings) -> AgentService:
    # Seed isolated sample data into test database
    food_cat = db_session.scalar(select(Category).where(Category.slug == "food"))
    groceries_sub = db_session.scalar(select(Subcategory).where(Subcategory.slug == "groceries"))
    income_cat = db_session.scalar(select(Category).where(Category.slug == "income"))

    tx_zepto = Transaction(
        id=new_id(),
        account="HDFC Bank XX1234",
        source="test",
        fingerprint=f"test-zepto-{new_id()}",
        transaction_date=utcnow(),
        amount=540.00,
        currency="INR",
        direction="debit",
        transaction_type="DEBIT",
        merchant_raw="Zepto Quick Commerce",
        merchant_normalized="Zepto",
        category_id=food_cat.id if food_cat else None,
        subcategory_id=groceries_sub.id if groceries_sub else None,
        is_duplicate=False,
        is_transfer=False,
        excludes_from_spending=False,
        needs_review=False,
        user_verified=True,
    )
    tx_salary = Transaction(
        id=new_id(),
        account="Salary Account XX5678",
        source="test",
        fingerprint=f"test-salary-{new_id()}",
        transaction_date=utcnow(),
        amount=150000.00,
        currency="INR",
        direction="credit",
        transaction_type="CREDIT",
        merchant_raw="ACME Corp",
        merchant_normalized="acme corp",
        category_id=income_cat.id if income_cat else None,
        description="Salary credit /Sala/2026",
        is_duplicate=False,
        is_transfer=False,
        excludes_from_spending=False,
        needs_review=False,
        user_verified=True,
    )
    db_session.add_all([tx_zepto, tx_salary])
    db_session.commit()

    principal = create_agent_principal(actor="pytest")
    return AgentService(principal=principal, settings=test_settings)


def test_get_financial_summary(agent_service: AgentService):
    res = agent_service.get_financial_summary(month="current")
    assert res.period is not None
    assert res.currency == "INR"
    assert isinstance(res.total_spent.amount, str)
    assert "." in res.total_spent.amount
    assert isinstance(res.consumer_spent.amount, str)
    assert isinstance(res.income.amount, str)
    assert isinstance(res.top_categories, list)
    assert isinstance(res.top_merchants, list)


def test_get_category_spending_cross(agent_service: AgentService):
    res = agent_service.get_category_spending(category=None, month="current", range_str="1m")
    assert hasattr(res, "categories")
    assert len(res.categories) > 0
    first = res.categories[0]
    assert first.category
    assert isinstance(first.total.amount, str)


def test_get_category_spending_deep_dive(agent_service: AgentService):
    res = agent_service.get_category_spending(category="Food", month="current", range_str="3m")
    assert hasattr(res, "subcategories")
    assert res.category == "Food"
    assert isinstance(res.total_spent.amount, str)
    assert isinstance(res.subcategories, list)
    assert isinstance(res.top_merchants, list)


def test_get_merchant_history(agent_service: AgentService):
    # Search for an existing merchant
    res = agent_service.get_merchant_history(merchant_name="Zepto", months=6, limit=5)
    assert res.merchant_name == "Zepto"
    assert res.public_id.startswith("merch_")
    assert isinstance(res.total_spent.amount, str)
    assert res.transaction_count > 0
    assert len(res.recent_transactions) > 0
    for tx in res.recent_transactions:
        assert tx.public_id.startswith("txn_")
        if tx.account_masked:
            assert tx.account_masked.startswith("••••")


def test_search_transactions(agent_service: AgentService):
    res = agent_service.search_transactions(direction="debit", limit=5)
    assert len(res.items) <= 5
    for item in res.items:
        assert item.public_id.startswith("txn_")
        assert not hasattr(item, "id")
        assert not hasattr(item, "raw_email")
        if item.account_masked:
            assert item.account_masked.startswith("••••")


def test_get_recurring_expenses(agent_service: AgentService):
    res = agent_service.get_recurring_expenses()
    assert hasattr(res, "subscriptions")
    assert hasattr(res, "bills")
    assert isinstance(res.total_monthly_burn.amount, str)


def test_get_income_and_salary(agent_service: AgentService):
    res = agent_service.get_income_and_salary(months=3)
    assert res.months_count == 3
    assert len(res.monthly_totals) == 3
    for m in res.monthly_totals:
        assert m.month
        assert isinstance(m.salary_income.amount, str)
        assert isinstance(m.total_income.amount, str)


def test_get_cash_flow_trends(agent_service: AgentService):
    res = agent_service.get_cash_flow_trends(months=6)
    assert res.currency == "INR"
    assert len(res.points) <= 6
    for pt in res.points:
        assert pt.month
        assert isinstance(pt.spent.amount, str)
        assert isinstance(pt.income.amount, str)


def test_list_budget_categories(agent_service: AgentService):
    res = agent_service.list_budget_categories()
    assert len(res.categories) > 0
    cat_names = [c.name for c in res.categories]
    assert "Food" in cat_names


def test_get_agent_capabilities(agent_service: AgentService):
    res = agent_service.get_agent_capabilities()
    assert res.agent_api_version == "1.0"
    assert len(res.capabilities) == 11
    assert "get_financial_summary" in res.capabilities
    assert "get_unclassified_spends" in res.capabilities
    assert "classify_transaction" in res.capabilities
