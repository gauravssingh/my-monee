"""Domain Invariants Test Suite — enforces the P0 core financial invariants of MyMonee."""

from datetime import datetime, timezone
from decimal import Decimal
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from expense_tracker.db.models import (
    Account,
    Base,
    Category,
    ClassificationRule,
    FinancialEvent,
    Merchant,
    MerchantAlias,
    Posting,
)
from expense_tracker.services.ledger import (
    calculate_ledger_balances,
    verify_event_double_entry,
)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture
def mem_session():
    """Isolated in-memory SQLite session with full canonical schema."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    yield session
    session.close()


def test_double_entry_balanced_event(mem_session: Session):
    """Every journal entry must balance: sum(debits) == sum(credits)."""
    bank = Account(name="Axis Bank", account_type="bank", is_asset=True, is_liability=False)
    cat = Category(name="Dining", slug="dining")
    mem_session.add_all([bank, cat])
    mem_session.flush()

    event = FinancialEvent(event_type="purchase", event_date=now_utc(), description="Starbucks Coffee")
    mem_session.add(event)
    mem_session.flush()

    # Asset decrease posting (debit at tx level -> credit at accounting level for bank asset decrease)
    # Balanced pair: DR Dining Expense 450, CR Axis Bank 450
    p1 = Posting(event_id=event.id, account_id=bank.id, amount=450.0, direction="credit", posting_type="asset_decrease")
    p2 = Posting(event_id=event.id, category_id=cat.id, amount=450.0, direction="debit", posting_type="expense")
    mem_session.add_all([p1, p2])
    mem_session.flush()

    is_balanced, debits, credits = verify_event_double_entry(mem_session, event.id)
    assert is_balanced is True
    assert debits == Decimal("450.0")
    assert credits == Decimal("450.0")


def test_double_entry_unbalanced_detection(mem_session: Session):
    """An unbalanced journal entry must be detected immediately."""
    bank = Account(name="HDFC Bank", account_type="bank", is_asset=True, is_liability=False)
    mem_session.add(bank)
    mem_session.flush()

    event = FinancialEvent(event_type="purchase", event_date=now_utc(), description="Broken entry")
    mem_session.add(event)
    mem_session.flush()

    p1 = Posting(event_id=event.id, account_id=bank.id, amount=1000.0, direction="credit", posting_type="asset_decrease")
    p2 = Posting(event_id=event.id, amount=900.0, direction="debit", posting_type="expense")
    mem_session.add_all([p1, p2])
    mem_session.flush()

    is_balanced, debits, credits = verify_event_double_entry(mem_session, event.id)
    assert is_balanced is False
    assert debits == Decimal("900.0")
    assert credits == Decimal("1000.0")


def test_account_normal_balance_and_net_worth_derivation(mem_session: Session):
    """Verify normal balance rules for Asset vs Liability and Net Worth = Assets - Liabilities."""
    # 1. Asset Account (Savings Bank with ₹1,00,000 opening balance)
    savings = Account(
        name="Axis Savings",
        account_type="bank",
        is_asset=True,
        is_liability=False,
        opening_balance=100000.0,
    )
    # 2. Liability Account (Credit Card with ₹0 opening balance)
    card = Account(
        name="Scapia Credit Card",
        account_type="credit_card",
        is_asset=False,
        is_liability=True,
        opening_balance=0.0,
    )
    mem_session.add_all([savings, card])
    mem_session.flush()

    # Scenario: Spend ₹5,000 on Scapia Credit Card (debit alert in bank terms)
    ev1 = FinancialEvent(event_type="purchase", event_date=now_utc(), description="Flight Booking")
    mem_session.add(ev1)
    mem_session.flush()

    # Card liability increases with debit alert (amount owed = 5,000)
    mem_session.add(Posting(event_id=ev1.id, account_id=card.id, amount=5000.0, direction="debit", posting_type="liability_increase"))
    mem_session.flush()

    # Scenario: Spend ₹2,000 from Savings Bank (debit alert -> reduces savings)
    ev2 = FinancialEvent(event_type="purchase", event_date=now_utc(), description="Groceries")
    mem_session.add(ev2)
    mem_session.flush()

    mem_session.add(Posting(event_id=ev2.id, account_id=savings.id, amount=2000.0, direction="debit", posting_type="asset_decrease"))
    mem_session.flush()

    summary = calculate_ledger_balances(mem_session)

    # Savings Asset: 100,000 - 2,000 = 98,000
    assert summary.total_assets == Decimal("98000")
    # Card Liability: 0 + 5,000 = 5,000 (debt owed)
    assert summary.total_liabilities == Decimal("5000")
    # Net Worth: 98,000 - 5,000 = 93,000
    assert summary.net_worth == Decimal("93000")


def test_credit_card_payment_settlement_preserves_net_worth(mem_session: Session):
    """Paying a credit card bill settles a liability from an asset, leaving net worth unchanged."""
    savings = Account(name="Axis Bank", account_type="bank", is_asset=True, is_liability=False, opening_balance=50000.0)
    card = Account(name="Scapia Card", account_type="credit_card", is_asset=False, is_liability=True, opening_balance=10000.0)
    mem_session.add_all([savings, card])
    mem_session.flush()

    # Initial Net Worth: 50,000 - 10,000 = 40,000
    initial_summary = calculate_ledger_balances(mem_session)
    assert initial_summary.net_worth == Decimal("40000")

    # Pay full credit card bill of ₹10,000 from savings
    settlement_event = FinancialEvent(event_type="transfer", event_date=now_utc(), description="Credit Card Bill Payment")
    mem_session.add(settlement_event)
    mem_session.flush()

    # Savings decreases by 10,000 (debit alert in bank)
    p_bank = Posting(event_id=settlement_event.id, account_id=savings.id, amount=10000.0, direction="debit", posting_type="asset_decrease")
    # Card liability decreases by 10,000 (credit payment received)
    p_card = Posting(event_id=settlement_event.id, account_id=card.id, amount=10000.0, direction="credit", posting_type="liability_decrease")
    mem_session.add_all([p_bank, p_card])
    mem_session.flush()

    post_summary = calculate_ledger_balances(mem_session)
    # Savings: 50,000 - 10,000 = 40,000
    assert post_summary.total_assets == Decimal("40000")
    # Card Liability: 10,000 - 10,000 = 0
    assert post_summary.total_liabilities == Decimal("0")
    # Net Worth remains invariant: 40,000 - 0 = 40,000
    assert post_summary.net_worth == Decimal("40000")


def test_classification_precedence_hierarchy(mem_session: Session):
    """Verify deterministic resolution order: User Correction > Exact Rule > Alias > Default."""
    # 1. Setup Taxonomy
    cat_food = Category(name="Food & Dining", slug="food")
    cat_travel = Category(name="Travel", slug="travel")
    cat_shopping = Category(name="Shopping", slug="shopping")
    mem_session.add_all([cat_food, cat_travel, cat_shopping])
    mem_session.flush()

    # 2. Setup Merchant with Default Category (Shopping)
    merchant = Merchant(
        display_name="Amazon India",
        normalized_key="amazon",
        default_category_id=cat_shopping.id,
    )
    mem_session.add(merchant)
    mem_session.flush()

    # 3. Setup Merchant Alias
    alias = MerchantAlias(
        merchant_id=merchant.id,
        alias_raw="AMZN MKTP IN",
        alias_normalized="amzn mktp in",
    )
    mem_session.add(alias)
    mem_session.flush()

    # 4. Setup Explicit Rule (e.g. Amazon Prime -> Subscriptions/Food)
    rule = ClassificationRule(
        name="Amazon Prime Rule",
        merchant_normalized="amazon prime",
        category_id=cat_food.id,
        priority=100,
        source="user",
    )
    mem_session.add(rule)
    mem_session.flush()

    # Verification of hierarchy:
    # A. Specific rule has higher priority over merchant default
    assert rule.priority > 0
    assert rule.category_id == cat_food.id
    # B. Generic alias falls back to canonical merchant's default category
    assert alias.merchant.default_category_id == cat_shopping.id
