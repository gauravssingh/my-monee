"""Comprehensive privacy assertion tests against prohibited tokens and canaries."""

from __future__ import annotations

import pytest

from mymonee.mcp.errors import AgentServiceError
from mymonee.mcp.models import (
    Money,
    Page,
    TransactionItem,
)
from mymonee.mcp.sanitizer import validate_agent_dto

SENSITIVE_CANARY_SAMPLES = [
    ("oauth_token", "ya29.a0AfH6SMD_OAUTH_TOKEN_TEST_1234567890"),
    ("refresh_token", "1//04REFRESH_TOKEN_TEST_secret_token_value"),
    ("gmail_id", "GMAIL_ID_TEST_18a2b3c4d5e6f7"),
    ("email_address", "test@example.com"),
    ("full_card", "4111111111111111"),
    ("full_account", "FULL_ACCOUNT_TEST_9876543210"),
    ("db_path", "/Users/gauravsingh/projects/my-monee/data/expense_tracker.db"),
    ("file_path", "/var/log/mymonee_private_secrets.log"),
    ("traceback", "Traceback (most recent call last):\n  File 'foo.py', line 1"),
]


@pytest.mark.parametrize("label,sensitive_val", SENSITIVE_CANARY_SAMPLES)
def test_sensitive_tokens_fail_closed_in_transaction_item(label: str, sensitive_val: str):
    """Verify that any DTO containing sensitive tokens triggers an immediate fail-closed error."""
    # Place sensitive value in merchant
    dto_merchant = TransactionItem(
        public_id="txn_safe",
        date="2026-03-01",
        amount=Money(amount="50.00", currency="INR"),
        merchant=f"Merchant {sensitive_val}",
        description="Normal transaction",
    )
    with pytest.raises(AgentServiceError):
        validate_agent_dto(dto_merchant)

    # Place sensitive value in description
    dto_desc = TransactionItem(
        public_id="txn_safe",
        date="2026-03-01",
        amount=Money(amount="50.00", currency="INR"),
        merchant="Safe Merchant",
        description=f"Ref: {sensitive_val}",
    )
    with pytest.raises(AgentServiceError):
        validate_agent_dto(dto_desc)


def test_clean_dto_passes_validation():
    """Verify clean, properly sanitized DTOs pass validation without errors."""
    clean_dto = TransactionItem(
        public_id="txn_9cbd76aefba52871",
        date="2026-03-01",
        amount=Money(amount="1004.00", currency="INR"),
        merchant="Jio Recharge",
        category="Utilities",
        subcategory="Mobile",
        account_masked="•••• 1022",
        payment_method="UPI",
        description="Jio mobile recharge monthly plan",
    )
    # Must not raise
    validate_agent_dto(clean_dto)

    page = Page[TransactionItem](
        items=[clean_dto],
        has_more=False,
        next_cursor=None,
        total_count=1,
    )
    validate_agent_dto(page)
