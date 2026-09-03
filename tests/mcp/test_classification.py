"""Tests for unclassified spends retrieval, reversible IDs, and transaction classification."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from mymonee.config import get_settings
from mymonee.db.models import (
    Category,
    ClassificationRule,
    Subcategory,
    Transaction,
    new_id,
    utcnow,
)
from mymonee.db.session import get_session_factory
from mymonee.mcp.errors import AgentServiceError, ErrorCode
from mymonee.mcp.models import from_public_id, to_public_id
from mymonee.mcp.principal import create_agent_principal
from mymonee.mcp.service import AgentService


@pytest.fixture
def agent_service() -> AgentService:
    settings = get_settings()
    principal = create_agent_principal(actor="pytest")
    return AgentService(principal=principal, settings=settings)


def test_public_id_reversible_roundtrip():
    uuid_str = "550e8400-e29b-41d4-a716-446655440000"
    pub_id = to_public_id("txn", uuid_str)
    assert pub_id.startswith("txn_")

    recovered = from_public_id("txn", pub_id)
    assert recovered == uuid_str


def test_public_id_tamper_detection():
    uuid_str = "550e8400-e29b-41d4-a716-446655440000"
    pub_id = to_public_id("txn", uuid_str)

    # Tamper with the token body
    tampered = pub_id[:-4] + "AAAA"
    with pytest.raises(ValueError, match="Invalid or tampered"):
        from_public_id("txn", tampered)

    # Invalid prefix
    with pytest.raises(ValueError, match="Invalid identifier"):
        from_public_id("acc", pub_id)


def test_get_unclassified_spends(agent_service: AgentService):
    res = agent_service.get_unclassified_spends(limit=5)
    assert hasattr(res, "items")
    assert hasattr(res, "total_count")
    assert res.total_count >= 0

    for item in res.items:
        assert item.public_id.startswith("txn_")
        assert item.merchant
        assert item.amount.amount
        assert item.direction in ("debit", "credit")
        if item.account_masked:
            assert "••••" in item.account_masked or "(" not in item.account_masked


def test_classify_transaction_flow(agent_service: AgentService):
    SessionFactory = get_session_factory()
    with SessionFactory() as session:
        # Create a fresh test category, subcategory, account, and unreviewed transaction
        cat = session.scalar(select(Category).where(Category.slug == "food-dining"))
        if not cat:
            cat = Category(id=new_id(), name="Food & Dining", slug="food-dining", sort_order=1)
            session.add(cat)
            session.flush()

        sub = session.scalar(
            select(Subcategory).where(
                Subcategory.category_id == cat.id, Subcategory.slug == "groceries"
            )
        )
        if not sub:
            sub = Subcategory(
                id=new_id(), name="Groceries", slug="groceries", category_id=cat.id, sort_order=1
            )
            session.add(sub)
            session.flush()

        cat_id = cat.id
        sub_id = sub.id

        test_tx = Transaction(
            id=new_id(),
            account="HDFC Bank",
            source="test",
            fingerprint=f"test-unclassified-{new_id()}",
            transaction_date=utcnow(),
            amount=450.00,
            currency="INR",
            direction="debit",
            merchant_raw="Quick Mart Organic Store",
            merchant_normalized="quick mart organic",
            needs_review=True,
            user_verified=False,
        )
        session.add(test_tx)
        session.commit()
        tx_id = test_tx.id

    public_id = to_public_id("txn", tx_id)

    # 1. Execute classification via AgentService
    result = agent_service.classify_transaction(
        transaction_id=public_id,
        category="Food & Dining",
        subcategory="Groceries",
        create_rule=True,
        apply_to_past=False,
    )

    assert result.status == "classified"
    assert result.category == "Food & Dining"
    assert result.subcategory == "Groceries"
    assert result.rule_created is True
    assert "Successfully classified" in result.message

    # 2. Verify database state
    with SessionFactory() as session:
        updated = session.get(Transaction, tx_id)
        assert updated is not None
        assert updated.needs_review is False
        assert updated.user_verified is True
        assert updated.category_id == cat_id
        assert updated.subcategory_id == sub_id

        # Verify persistent merchant rule was created
        rule = session.scalar(
            select(ClassificationRule).where(
                ClassificationRule.category_id == cat_id,
                ClassificationRule.merchant_normalized == "quick mart organic",
            )
        )
        assert rule is not None


def test_classify_transaction_invalid_category(agent_service: AgentService):
    uuid_str = "550e8400-e29b-41d4-a716-446655440000"
    public_id = to_public_id("txn", uuid_str)

    with pytest.raises(AgentServiceError) as exc_info:
        agent_service.classify_transaction(
            transaction_id=public_id,
            category="NonExistentCategory999",
        )
    assert exc_info.value.code == ErrorCode.INVALID_ARGUMENT
    assert "Unknown category" in str(exc_info.value)


def test_classify_transaction_invalid_token(agent_service: AgentService):
    with pytest.raises(AgentServiceError) as exc_info:
        agent_service.classify_transaction(
            transaction_id="txn_tampered_bad_token",
            category="Food",
        )
    assert exc_info.value.code == ErrorCode.INVALID_ARGUMENT
    assert "Invalid transaction identifier" in str(exc_info.value)
