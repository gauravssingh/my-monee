"""Tests for privacy sanitizer, masking, and fail-closed leak detector."""

from __future__ import annotations

import pytest

from mymonee.mcp.errors import AgentServiceError, ErrorCode
from mymonee.mcp.models import Money, TransactionItem
from mymonee.mcp.sanitizer import (
    mask_account,
    mask_card,
    sanitize_description,
    validate_agent_dto,
)


def test_mask_account():
    assert mask_account("XX1234") == "•••• 1234"
    assert mask_account("A/c 9876543210") == "•••• 3210"
    assert mask_account("4321") == "•••• 4321"
    assert mask_account(None) is None
    assert mask_account("") is None


def test_mask_card():
    assert mask_card("4111222233334444") == "•••• 4444"
    assert mask_card("Card-9988") == "•••• 9988"
    assert mask_card(None) is None


def test_sanitize_description():
    desc = "Payment to rahul@upi via UTR 123456789012 ref for lunch"
    sanitized = sanitize_description(desc)
    assert "[UPI]" in sanitized
    assert "[REF]" in sanitized
    assert "123456789012" not in sanitized


def test_canary_leak_fails_closed():
    """Verify that seeded canaries trigger fail-closed AgentServiceError(ErrorCode.INTERNAL)."""
    item = TransactionItem(
        public_id="txn_123",
        date="2026-03-01",
        amount=Money(amount="100.00", currency="INR"),
        merchant="SECRET_API_KEY_TEST",
        description="Normal description",
    )
    with pytest.raises(AgentServiceError) as exc_info:
        validate_agent_dto(item)
    assert exc_info.value.code == ErrorCode.INTERNAL
    assert "Unable to complete requested operation" in exc_info.value.to_public_message()


def test_email_leak_fails_closed():
    item = TransactionItem(
        public_id="txn_123",
        date="2026-03-01",
        amount=Money(amount="100.00", currency="INR"),
        merchant="Valid Merchant",
        description="Contact user at sensitive@example.com for invoice",
    )
    with pytest.raises(AgentServiceError) as exc_info:
        validate_agent_dto(item)
    assert exc_info.value.code == ErrorCode.INTERNAL


def test_jwt_bearer_leak_fails_closed():
    jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozqvE_vF_1234567890"
    item = TransactionItem(
        public_id="txn_123",
        date="2026-03-01",
        amount=Money(amount="100.00", currency="INR"),
        merchant="Valid Merchant",
        description=f"Auth token: {jwt}",
    )
    with pytest.raises(AgentServiceError) as exc_info:
        validate_agent_dto(item)
    assert exc_info.value.code == ErrorCode.INTERNAL


def test_file_path_leak_fails_closed():
    item = TransactionItem(
        public_id="txn_123",
        date="2026-03-01",
        amount=Money(amount="100.00", currency="INR"),
        merchant="Valid Merchant",
        description="Saved to /Users/gauravsingh/private_ledger/secrets.json",
    )
    with pytest.raises(AgentServiceError) as exc_info:
        validate_agent_dto(item)
    assert exc_info.value.code == ErrorCode.INTERNAL


def test_traceback_leak_fails_closed():
    tb = "Traceback (most recent call last):\n  File 'app.py', line 10\nZeroDivisionError"
    item = TransactionItem(
        public_id="txn_123",
        date="2026-03-01",
        amount=Money(amount="100.00", currency="INR"),
        merchant="Valid Merchant",
        description=f"Error occurred: {tb}",
    )
    with pytest.raises(AgentServiceError) as exc_info:
        validate_agent_dto(item)
    assert exc_info.value.code == ErrorCode.INTERNAL
