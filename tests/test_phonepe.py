"""Unit tests for PhonePe dedicated parser."""

from datetime import datetime, timezone
from decimal import Decimal

from expense_tracker.parsers.base import EmailContext
from expense_tracker.parsers.phonepe import PhonePeParser


def test_phonepe_challan_parsing():
    parser = PhonePeParser()
    body = """
Jan 13, 2026 Payment For TGXXX5200 ₹2073.54
Txn. ID : NB26011313342078729647832
Txn. status : Successful
Debited from Bank Account : XXXXXXXXXX43
Amount : ₹2073.54
Bank Ref. No. : 922291017537
Bill/Recharge Amount : ₹2073.54
Category : E-Challan
Provider : Telangana E Challan
Hi Gaurav
    """
    ctx = EmailContext(
        message_id="msg123",
        thread_id="th123",
        sender="PhonePe <noreply@phonepe.com>",
        subject="Payment for Telangana E Challan E-Challan of ₹ 2073.54 is successful",
        received_at=datetime(2026, 1, 13, 8, 4, 27, tzinfo=timezone.utc),
        body_text=body,
    )
    assert parser.can_parse(ctx) >= 0.90
    results = parser.parse(ctx)
    assert len(results) == 1
    tx = results[0]
    assert tx.amount == Decimal("2073.54")
    assert tx.merchant_raw == "Telangana E Challan"
    assert tx.account == "43"
    assert tx.reference_number == "922291017537"
    assert tx.extra["category_slug"] == "car"
    assert tx.extra["subcategory_slug"] == "fines"


def test_phonepe_gas_bill_parsing():
    parser = PhonePeParser()
    body = """
Jun 1, 2026 Payment For 1HXXXXX2243 ₹1440
Txn. ID : NX26060117184145395009341
Txn. status : Successful
Debited from Bank Account : XXXX801022
Amount : ₹1440
Bank Ref. No. : 181829717197
Category : Gas
Provider : Bhagyanagar Gas Limited
    """
    ctx = EmailContext(
        message_id="msg124",
        thread_id="th124",
        sender="PhonePe <noreply@phonepe.com>",
        subject="Payment for Bhagyanagar Gas Limited Gas of ₹ 1440 is successful",
        received_at=datetime(2026, 6, 1, 11, 48, 46, tzinfo=timezone.utc),
        body_text=body,
    )
    results = parser.parse(ctx)
    assert len(results) == 1
    tx = results[0]
    assert tx.amount == Decimal("1440")
    assert tx.merchant_raw == "Bhagyanagar Gas Limited"
    assert tx.account == "801022"
    assert tx.reference_number == "181829717197"
    assert tx.extra["category_slug"] == "utilities"
    assert tx.extra["subcategory_slug"] == "gas"


def test_phonepe_autopay_reminder_ignored():
    parser = PhonePeParser()
    ctx = EmailContext(
        message_id="msg125",
        thread_id="th125",
        sender="PhonePe <noreply@phonepe.com>",
        subject="Your AutoPay will be debited as scheduled!",
        received_at=datetime(2026, 1, 17, 11, 23, 46, tzinfo=timezone.utc),
        body_text="Your AutoPay for Apple Inc is scheduled",
    )
    results = parser.parse(ctx)
    assert len(results) == 0
