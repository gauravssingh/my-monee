from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from expense_tracker.parsers.axis import AxisBankParser, classify_axis_credit, extract_axis_channel_ref
from expense_tracker.parsers.base import EmailContext
from expense_tracker.parsers.bootstrap import bootstrap_parsers
from expense_tracker.parsers.registry import registry


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