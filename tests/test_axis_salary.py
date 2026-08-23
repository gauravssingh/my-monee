from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from mymonee.parsers.axis import AxisBankParser, classify_axis_credit, extract_axis_channel_ref
from mymonee.parsers.base import EmailContext
from mymonee.parsers.bootstrap import bootstrap_parsers
from mymonee.parsers.registry import registry


SALARY_BODY = """
Dear Customer,
Your Axis Bank Account A/c no. XX1234 is credited with INR 261,234.00 on 01-05-2026.
Transaction Info: NEFT/CHASH00053023262/Sala.
Amount Credited: INR 261,234.00
If you have not done this transaction, please call us.
"""

UPI_CREDIT_BODY = """
Dear Customer,
Your Axis Bank Account A/c no. XX1234 is credited with INR 99.00 on 12-03-2026.
by UPI/P2A/412345678901/APPLE MED/AXIS BANK.
Amount Credited: INR 99.00
"""

REFUND_BODY = """
Dear Customer,
Your Axis Bank Account A/c no. XX1234 is credited with INR 450.00 on 10-02-2026.
by NEFT/ABCD123456/Refund from merchant.
Amount Credited: INR 450.00
"""


def test_extract_neft_sala_channel_ref() -> None:
    ref = extract_axis_channel_ref(SALARY_BODY)
    assert ref is not None
    assert ref.upper().endswith("/SALA")
    assert "CHASH00053023262" in ref.upper()


def test_classify_salary_vs_transfer() -> None:
    salary = classify_axis_credit("NEFT/CHASH00053023262/Sala", SALARY_BODY)
    assert salary["transaction_type"] == "income"
    assert salary["category_slug"] == "income"
    assert salary["subcategory_slug"] == "salary"
    assert salary["needs_review"] is False
    assert salary["classification_signals"]["rule"] == "axis_neft_sala_salary"

    transfer = classify_axis_credit("UPI/P2A/412345678901/APPLE MED", UPI_CREDIT_BODY)
    assert transfer["transaction_type"] == "transfer"
    assert transfer["is_transfer"] is True
    assert transfer["category_slug"] == "transfers"
    assert transfer["subcategory_slug"] is None
    assert transfer["excludes_from_spending"] is True

    refund = classify_axis_credit("NEFT/ABCD123456/Refund", REFUND_BODY)
    assert refund["transaction_type"] == "refund"
    assert refund["is_refund"] is True


def test_axis_parser_salary_credit() -> None:
    parser = AxisBankParser()
    email = EmailContext(
        message_id="axis-salary-1",
        thread_id="t1",
        sender="alerts@axis.bank.in",
        subject="Credit transaction alert for Axis Bank A/c",
        received_at=datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc),
        body_text=SALARY_BODY,
    )
    assert parser.can_parse(email) >= 0.9
    parsed = parser.parse(email)
    assert len(parsed) == 1
    tx = parsed[0]
    assert tx.amount == Decimal("261234.00")
    assert tx.direction == "credit"
    assert tx.transaction_type == "income"
    assert tx.merchant_raw == "Salary"
    assert tx.extra["category_slug"] == "income"
    assert tx.extra["subcategory_slug"] == "salary"
    assert tx.extra["classification_source"] == "rule"
    assert tx.extra["needs_review"] is False
    assert tx.reference_number and "Sala" in tx.reference_number


def test_axis_parser_upi_credit_is_transfer() -> None:
    parser = AxisBankParser()
    email = EmailContext(
        message_id="axis-upi-1",
        thread_id="t2",
        sender="alerts@axis.bank.in",
        subject="Credit transaction alert for Axis Bank A/c",
        received_at=datetime(2026, 3, 12, 10, 0, tzinfo=timezone.utc),
        body_text=UPI_CREDIT_BODY,
    )
    parsed = parser.parse(email)
    assert len(parsed) == 1
    tx = parsed[0]
    assert tx.amount == Decimal("99.00")
    assert tx.transaction_type == "transfer"
    assert tx.extra["is_transfer"] is True
    assert tx.extra["category_slug"] == "transfers"


def test_axis_parser_upilite_leading_decimal() -> None:
    parser = AxisBankParser()
    email = EmailContext(
        message_id="axis-lite-1",
        thread_id="t4",
        sender="alerts@axis.bank.in",
        subject="Credit transaction alert for Axis Bank A/c",
        received_at=datetime(2026, 3, 12, tzinfo=timezone.utc),
        body_text=(
            "your A/c no. XX1022 has been credited with INR .52 on 12-03-2026 "
            "at 20:46:19 IST by UPILITE/DORMANT/12.03.2026."
        ),
    )
    parsed = parser.parse(email)
    assert len(parsed) == 1
    assert parsed[0].amount == Decimal("0.52")
    assert parsed[0].transaction_type == "transfer"
    assert parsed[0].reference_number and "UPILITE" in parsed[0].reference_number.upper()


def test_axis_parser_registered_before_generic() -> None:
    bootstrap_parsers(force=True)
    email = EmailContext(
        message_id="axis-salary-2",
        thread_id="t3",
        sender="alerts@axis.bank.in",
        subject="Credit transaction alert for Axis Bank A/c",
        received_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        body_text=SALARY_BODY,
    )
    plugin, score = registry.choose(email)
    assert plugin is not None
    assert plugin.name == "axis_bank_alerts"
    assert score >= 0.9


def test_axis_declined_card_alert_is_excluded() -> None:
    parser = AxisBankParser()
    email = EmailContext(
        message_id="axis-declined-1",
        thread_id="td",
        sender="Axis Bank Alerts <alerts@axis.bank.in>",
        subject="Transaction declined for Transaction alert on Axis Bank Credit Card no. XX4951",
        received_at=datetime(2026, 8, 12, tzinfo=timezone.utc),
        body_text=(
            "12-08-2026 Dear Gaurav Singh, Please note that transaction attempt for INR 399 "
            "on your Axis Bank Credit Card no. XX4951 has been declined due to security reasons."
        ),
    )
    assert parser.can_parse(email) >= 0.95
    parsed = parser.parse(email)
    assert len(parsed) == 1
    tx = parsed[0]
    assert tx.amount == Decimal("399")
    assert tx.transaction_type == "not_a_transaction"
    assert tx.extra["excludes_from_spending"] is True
    assert tx.extra["needs_review"] is False
    assert tx.extra["classification_signals"]["rule"] == "axis_declined_transaction"


def test_axis_credit_card_merchant_extraction() -> None:
    parser = AxisBankParser()
    body_text = """
13-06-2026 Dear Gaurav Singh,
Here's the summary of your Axis Bank Credit Card Transaction:
Transaction Amount:
INR 1264
Merchant Name:
AMAZON PAY
Axis Bank Credit Card No.
XX4951
Date & Time:
13-06-2026, 18:08:48 IST
Available Limit*:
INR 1148594.89
Total Credit Limit*:
INR 1193000
"""
    email = EmailContext(
        message_id="axis-cc-amazon-1",
        thread_id="t_cc_1",
        sender="Axis Bank Alerts <alerts@axis.bank.in>",
        subject="INR 1264 spent on credit card no. XX4951",
        received_at=datetime(2026, 6, 13, 18, 8, 48, tzinfo=timezone.utc),
        body_text=body_text,
    )
    assert parser.can_parse(email) >= 0.9
    parsed = parser.parse(email)
    assert len(parsed) == 1
    tx = parsed[0]
    assert tx.amount == Decimal("1264")
    assert tx.direction == "debit"
    assert tx.merchant_raw == "AMAZON PAY"
    assert tx.card == "4951"
    assert tx.transaction_date.day == 13
    assert tx.transaction_date.month == 6


def test_axis_bank_upi_email_parsing() -> None:
    parser = AxisBankParser()
    body_text = """
Amount Debited:
INR 20.00

Account Number:
XX1022

Date & Time:
27-07-26, 08:00:44 IST

Transaction Info:
UPI/P2M/800745883926/Syed Naseeruddin
"""
    email = EmailContext(
        message_id="axis-upi-debit-1",
        thread_id="t_upi_1",
        sender="Axis Bank Alerts <alerts@axis.bank.in>",
        subject="Debit Transaction Alert",
        received_at=datetime(2026, 7, 27, 8, 0, 44, tzinfo=timezone.utc),
        body_text=body_text,
    )
    assert parser.can_parse(email) >= 0.9
    parsed = parser.parse(email)
    assert len(parsed) == 1
    tx = parsed[0]
    assert tx.amount == Decimal("20.00")
    assert tx.direction == "debit"
    assert tx.merchant_raw == "Syed Naseeruddin"
    assert tx.payment_method == "upi"
    assert tx.reference_number == "UPI/P2M/800745883926/Syed Naseeruddin"
    assert "800745883926" in tx.description
    assert tx.extra["upi_rrn"] == "800745883926"


def test_axis_bank_scapia_cc_bill_payment() -> None:
    parser = AxisBankParser()
    body_text = """
Amount Debited:
INR 99816.14

Account Number:
XX1022

Date & Time:
21-08-26, 12:13:00 IST

Transaction Info:
UPI/P2M/553480039613/Scapia
"""
    email = EmailContext(
        message_id="axis-scapia-bill-1",
        thread_id="t_scapia_1",
        sender="Axis Bank Alerts <alerts@axis.bank.in>",
        subject="INR 99816.14 was debited from your A/c no. XX1022.",
        received_at=datetime(2026, 8, 21, 12, 13, 0, tzinfo=timezone.utc),
        body_text=body_text,
    )
    assert parser.can_parse(email) >= 0.9
    parsed = parser.parse(email)
    assert len(parsed) == 1
    tx = parsed[0]
    assert tx.amount == Decimal("99816.14")
    assert tx.transaction_type == "transfer"
    assert tx.extra["is_transfer"] is True
    assert tx.extra["excludes_from_spending"] is True
    assert tx.extra["category_slug"] == "transfers"
    assert tx.extra["subcategory_slug"] == "credit-card-payment"


def test_axis_bank_credit_card_payment() -> None:
    parser = AxisBankParser()
    body_text = """
11-01-2026 Dear Gaurav Singh, Thank you for banking with us.
We wish to inform you that your A/c no. XX1022 has been debited with INR 56943.57 on 11-01-2026 15:18:21 IST by CreditCard Payment XX 4951.
"""
    email = EmailContext(
        message_id="axis-cc-pay-1",
        thread_id="t_cc_1",
        sender="Axis Bank Alerts <alerts@axis.bank.in>",
        subject="Debit transaction alert for Axis Bank A/c",
        received_at=datetime(2026, 1, 11, 15, 18, 21, tzinfo=timezone.utc),
        body_text=body_text,
    )
    assert parser.can_parse(email) >= 0.9
    parsed = parser.parse(email)
    assert len(parsed) == 1
    tx = parsed[0]
    assert tx.amount == Decimal("56943.57")
    assert tx.transaction_type == "transfer"
    assert tx.extra["is_transfer"] is True
    assert tx.extra["excludes_from_spending"] is True
    assert tx.extra["category_slug"] == "transfers"
    assert tx.extra["subcategory_slug"] == "credit-card-payment"