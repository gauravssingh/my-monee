from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from mymonee.parsers.base import EmailContext
from mymonee.parsers.extract import extract_merchant, infer_direction
from mymonee.parsers.scapia import ScapiaCardParser


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


def test_scapia_parser_bill_payment() -> None:
    email = EmailContext(
        message_id="scapia-test-bill-pay",
        thread_id=None,
        sender="Scapia <alerts@scapia.cards>",
        subject="Bill payment successful!",
        received_at=datetime(2026, 8, 21, 12, 13, tzinfo=timezone.utc),
        body_text="Great news! We received your credit card bill payment in just 1.3 seconds. Card: Federal Bank XXXX-0863 Amount Paid: ₹99816.14 Paid Via: upi",
        body_html=None,
    )
    parser = ScapiaCardParser()
    assert parser.can_parse(email) >= 0.75
    parsed = parser.parse(email)
    assert len(parsed) == 1
    tx = parsed[0]
    assert tx.amount == Decimal("99816.14")
    assert tx.transaction_type == "transfer"
    assert tx.extra["is_transfer"] is True
    assert tx.extra["excludes_from_spending"] is True
    assert tx.extra["category_slug"] == "transfers"
    assert tx.extra["subcategory_slug"] == "credit-card-payment"


def test_scapia_ignores_statement_email() -> None:
    email = EmailContext(
        message_id="scapia-test-stmt",
        thread_id=None,
        sender="Scapia Federal Credit Card <scapiacards@federalbank.co.in>",
        subject="Your Scapia Federal credit card statement for August, 2026",
        received_at=datetime(2026, 8, 21, 12, 13, tzinfo=timezone.utc),
        body_text="Your latest statement for the cycle 21 Jul 2026 - 20 Aug 2026 has landed. Total Amount Due ₹99816.14",
        body_html=None,
    )
    parser = ScapiaCardParser()
    assert parser.can_parse(email) == 0.0
