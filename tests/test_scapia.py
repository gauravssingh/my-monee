from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from expense_tracker.parsers.base import EmailContext
from expense_tracker.parsers.extract import extract_merchant, infer_direction
from expense_tracker.parsers.scapia import ScapiaCardParser


SCAPIA_BODY = """
Your transaction was successful!
Your payment on 12-08-2026 at 01:37 PM using your Scapia Federal Visa Credit Card ending in 0863 has been successfully processed.
Amount
₹649.00
Merchant
Cursor, Ai Powered Ide + Us
Not you? Head to Support on the Scapia app or call 18002961199.
"""


def test_credit_card_phrase_is_debit_not_credit() -> None:
    text = (
        "Your payment on 12-08-2026 using your Scapia Federal Visa Credit Card "
        "ending in 0863. Amount ₹649.00 Merchant Cursor"
    )
    assert infer_direction(text) == "debit"


def test_true_credit_still_credit() -> None:
    assert infer_direction("INR 1000 credited to your account") == "credit"
    assert infer_direction("Refund of INR 100 credited to your account") == "credit"


def test_merchant_prefers_labeled_field_over_support_footer() -> None:
    merchant = extract_merchant(SCAPIA_BODY)
    assert merchant is not None
    assert "Cursor" in merchant
    assert "Support" not in merchant


def test_scapia_parser_purchase() -> None:
    email = EmailContext(
        message_id="scapia-test-1",
        thread_id=None,
        sender="Scapia Federal Credit Card <scapiacards@federalbank.co.in>",
        subject="Your transaction was successful",
        received_at=datetime(2026, 8, 12, 8, 0, tzinfo=timezone.utc),
        body_text=SCAPIA_BODY,
        body_html=None,
    )
    parser = ScapiaCardParser()
    assert parser.can_parse(email) >= 0.9
    parsed = parser.parse(email)
    assert len(parsed) == 1
    tx = parsed[0]
    assert tx.amount == Decimal("649.00")
    assert tx.direction == "debit"
    assert tx.transaction_type == "purchase"
    assert tx.merchant_raw and "Cursor" in tx.merchant_raw
    assert tx.card == "0863"
    assert tx.payment_method == "card"
