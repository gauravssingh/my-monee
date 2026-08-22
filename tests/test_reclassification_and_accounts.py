from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from expense_tracker.db.models import Account, Category, Institution, Subcategory, Transaction
from expense_tracker.ingestion.pipeline import _get_or_create_account
from expense_tracker.parsers.base import ParsedTransaction
from expense_tracker.services.transactions import _apply_category_side_effects, classify_transaction


def test_category_side_effects_transfers() -> None:
    tx = Transaction(
        amount=Decimal("5000.00"),
        direction="debit",
        transaction_type="purchase",
        is_transfer=False,
        excludes_from_spending=False,
    )
    cat_transfers = Category(id="cat-t", name="Transfers", slug="transfers")
    subcat_cc = Subcategory(id="sub-cc", name="Credit Card Payment", slug="credit-card-payment", category_id="cat-t")

    # Moving to transfers
    _apply_category_side_effects(tx, cat_transfers, subcat_cc)
    assert tx.is_transfer is True
    assert tx.excludes_from_spending is True
    assert tx.transaction_type == "transfer"

    # Moving out of transfers to Food & Dining
    cat_food = Category(id="cat-f", name="Food & Dining", slug="food-dining")
    subcat_dining = Subcategory(id="sub-d", name="Restaurants", slug="restaurants", category_id="cat-f")

    _apply_category_side_effects(tx, cat_food, subcat_dining)
    assert tx.is_transfer is False
    assert tx.excludes_from_spending is False
    assert tx.transaction_type == "purchase"


def test_category_side_effects_income_and_refund() -> None:
    tx = Transaction(
        amount=Decimal("250.00"),
        direction="credit",
        transaction_type="income",
        is_transfer=False,
        is_refund=False,
        excludes_from_spending=True,
    )
    cat_income = Category(id="cat-inc", name="Income", slug="income")
    subcat_refund = Subcategory(id="sub-ref", name="Refund", slug="refund", category_id="cat-inc")

    _apply_category_side_effects(tx, cat_income, subcat_refund)
    assert tx.is_refund is True
    assert tx.transaction_type == "refund"
    assert tx.excludes_from_spending is True


def test_get_or_create_account_ambiguous_last4(db_session: Session) -> None:
    inst = Institution(name="Axis Bank", institution_type="BANK")
    db_session.add(inst)
    db_session.flush()

    # Both bank account and credit card share last4 digits "1022" in their masked strings
    bank_acc = Account(
        name="Axis Bank Savings",
        institution_id=inst.id,
        account_type="BANK",
        account_number_masked="1022",
        card_last4=None,
    )
    card_acc = Account(
        name="Axis Bank Credit Card",
        institution_id=inst.id,
        account_type="CREDIT_CARD",
        account_number_masked="1022",
        card_last4="4951",
    )
    db_session.add_all([bank_acc, card_acc])
    db_session.commit()

    # 1. ParsedTransaction with account="1022" (no card) should unambiguously pick the BANK account
    parsed_bank = ParsedTransaction(
        amount=500.0,
        currency="INR",
        transaction_date=datetime(2026, 8, 1, tzinfo=UTC),
        direction="debit",
        account="1022",
        merchant_raw="Swiggy",
    )
    resolved = _get_or_create_account(db_session, parsed_bank)
    assert resolved.id == bank_acc.id
    assert resolved.account_type == "BANK"

    # 2. ParsedTransaction with card="4951" should unambiguously pick the CREDIT_CARD account
    parsed_card = ParsedTransaction(
        amount=1200.0,
        currency="INR",
        transaction_date=datetime(2026, 8, 1, tzinfo=UTC),
        direction="debit",
        card="4951",
        merchant_raw="Amazon",
    )
    resolved_card = _get_or_create_account(db_session, parsed_card)
    assert resolved_card.id == card_acc.id
    assert resolved_card.account_type == "CREDIT_CARD"


def test_get_or_create_account_fallback_populates_identifiers(db_session: Session) -> None:
    # ParsedTransaction for a completely new card
    parsed_new = ParsedTransaction(
        amount=350.0,
        currency="INR",
        transaction_date=datetime(2026, 8, 2, tzinfo=UTC),
        direction="debit",
        card="9988",
        merchant_raw="Uber",
    )
    created = _get_or_create_account(db_session, parsed_new)
    assert created.card_last4 == "9988"
    assert created.account_type == "CREDIT_CARD"

    # Subsequent transaction matching "9988" reuses this newly created account
    resolved_again = _get_or_create_account(db_session, parsed_new)
    assert resolved_again.id == created.id
