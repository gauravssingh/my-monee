"""Comprehensive test suite for Statement Parsers, Arithmetic Validator, and Reconciliation Engine."""

from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from expense_tracker.app import create_app
from expense_tracker.config import Settings
from expense_tracker.db.models import Transaction, new_id
from expense_tracker.statements.extractor import load_pdf_structure
from expense_tracker.statements.parsers.axis_bank import AxisBankParser
from expense_tracker.statements.parsers.axis_credit_card import AxisCreditCardParser
from expense_tracker.statements.parsers.scapia import ScapiaParser
from expense_tracker.statements.reconciliation import match_statement_transaction
from expense_tracker.statements.validator import StatementValidator


def _create_text_pdf(text_pages: list[str]) -> bytes:
    """Create in-memory PDF with text on pages."""
    import pymupdf

    doc = pymupdf.open()
    for text in text_pages:
        page = doc.new_page(width=595, height=842)
        page.insert_text((50, 72), text, fontsize=11)
    stream = doc.tobytes()
    doc.close()
    return stream


# --- 1. Scapia Multi-Card Parser Tests ---


def test_scapia_combined_card_parser():
    scapia_text = """
    Scapia Federal Credit Card
    Statement Date: 21 Jul 2026
    Payment Due Date: 08 Aug 2026
    Statement Period: 21 Jun 2026 to 20 Jul 2026
    
    Cards on this statement:
    Visa Credit Card ending in 0863
    RuPay Credit Card ending in 1221
    
    Statement Summary:
    Previous Balance: INR 0.00
    Transactions: INR 34,687.55
    Payments / Refunds: INR -100.64
    Total Amount Due: INR 34,586.91
    Minimum Amount Due: INR 1,729.35
    
    Transaction Details:
    22 Jun 2026 Swiggy Bangalore 450.00
    25 Jun 2026 Amazon India 1,704.00
    10 Jul 2026 Seasons Xprs Hyderabad 1,304.00
    15 Jul 2026 Merchant Refund 100.64 Cr
    """
    pdf_bytes = _create_text_pdf([scapia_text])
    doc_struct = load_pdf_structure(pdf_bytes)

    parser = ScapiaParser()
    assert parser.can_parse(doc_struct) >= 0.5

    result = parser.parse(doc_struct)

    # 1. Multi-card detection: Both Visa and RuPay discovered
    assert len(result.accounts) == 2
    networks = {a.card_network for a in result.accounts}
    assert "VISA" in networks
    assert "RUPAY" in networks
    assert any("0863" in a.masked_identifier for a in result.accounts)
    assert any("1221" in a.masked_identifier for a in result.accounts)

    # 2. Combined Summary extraction
    assert result.summary is not None
    assert result.summary.total_due == 34586.91
    assert result.summary.minimum_due == 1729.35
    assert result.summary.purchases == 34687.55
    assert result.summary.payments == -100.64

    # 3. Transactions extracted
    assert len(result.transactions) == 4

    # 4. Principle 3 Verification: Combined statements MUST NOT guess card attribution!
    for tx in result.transactions:
        assert tx.attribution_status == "UNKNOWN"
        assert tx.statement_account_index is None

    # 5. Arithmetic Validation
    validator = StatementValidator()
    val_report = validator.validate(result)
    assert val_report.status == "VALIDATED"
    assert len(val_report.equations) == 1
    assert val_report.equations[0].is_balanced is True
    assert val_report.equations[0].difference == 0.0


# --- 2. Axis Bank Savings Parser Tests ---


def test_axis_bank_savings_parser():
    axis_bank_text = """
    Axis Bank Limited
    Statement of Axis Bank Account No: 921010045671022
    Period: 01-07-2026 to 31-07-2026
    
    Account Summary:
    Opening Balance: INR 467,426.81
    Total Withdrawals: INR 107,288.58
    Total Deposits: INR 284,818.00
    Closing Balance: INR 644,956.23

    Transactions:
    01-07-2026 /Sala Axis Salary Credit 284,818.00 752,244.81
    11-07-2026 CREDITCARD PAYMENT XX 4951 72,701.67 679,543.14
    21-07-2026 Scapia CC Payment 34,586.91 644,956.23
    """
    pdf_bytes = _create_text_pdf([axis_bank_text])
    doc_struct = load_pdf_structure(pdf_bytes)

    parser = AxisBankParser()
    assert parser.can_parse(doc_struct) >= 0.6

    result = parser.parse(doc_struct)

    # 1. Account detection
    assert len(result.accounts) == 1
    assert result.accounts[0].masked_identifier == "****1022"
    assert result.accounts[0].opening_balance == 467426.81
    assert result.accounts[0].closing_balance == 644956.23

    # 2. Summary
    assert result.summary is not None
    assert result.summary.previous_balance == 467426.81

    # 3. Transactions & Attribution
    assert len(result.transactions) == 3
    for tx in result.transactions:
        assert tx.attribution_status == "EXACT"
        assert tx.statement_account_index == 0

    # 4. Bank Arithmetic Validation: Opening (467426.81) + Deposits (284818.00) - Withdrawals (276685.73) = Closing (475559.08)
    validator = StatementValidator()
    val_report = validator.validate(result)
    assert val_report.status == "VALIDATED"
    assert len(val_report.equations) == 1
    eq = val_report.equations[0]
    assert eq.is_balanced is True
    assert eq.difference < 0.01


# --- 3. Axis Credit Card Parser Tests ---


def test_axis_credit_card_parser():
    axis_cc_text = """
    Axis Bank Credit Card Statement
    Card Number: 4375 XXXX XXXX 4951
    Statement Date: 15-07-2026
    Payment Due Date: 05-08-2026
    Period: 16-06-2026 to 15-07-2026
    Credit Limit: INR 300,000.00
    Available Credit Limit: INR 227,298.33
    
    Payment Summary:
    Previous Balance: INR 50,000.00
    Payments Received: INR 50,000.00
    Purchases: INR 72,701.67
    Finance Charges: INR 0.00
    Total Payment Due: INR 72,701.67
    Minimum Payment Due: INR 3,635.00
    
    Transactions:
    18-06-2026 Croma Electronics Mumbai 45,000.00
    25-06-2026 Indigo Airlines Gurgaon 27,701.67
    """
    pdf_bytes = _create_text_pdf([axis_cc_text])
    doc_struct = load_pdf_structure(pdf_bytes)

    parser = AxisCreditCardParser()
    assert parser.can_parse(doc_struct) >= 0.6

    result = parser.parse(doc_struct)

    assert len(result.accounts) == 1
    assert result.accounts[0].masked_identifier == "****4951"
    assert result.accounts[0].credit_limit == 300000.00
    assert result.summary.total_due == 72701.67

    validator = StatementValidator()
    val_report = validator.validate(result)
    assert val_report.status == "VALIDATED"


# --- 4. Reconciliation & Liability Payment Engine Tests ---


def test_reconciliation_liability_payment_matching():
    # 1. Statement transaction: Bank payment of ₹34,586.91 to Scapia
    stmt_tx = type(
        "MockStmtTx",
        (),
        {
            "description": "Scapia Credit Card Bill Payment",
            "amount": 34586.91,
            "transaction_date": datetime(2026, 7, 21, tzinfo=timezone.utc),
            "reference_number": "REF999",
        },
    )()

    # 2. Ledger transaction: Alert for Scapia payment
    ledger_tx = Transaction(
        id=new_id(),
        transaction_date=datetime(2026, 7, 21, tzinfo=timezone.utc),
        amount=34586.91,
        merchant_raw="Scapia Billdesk",
        direction="debit",
    )

    match_res = match_statement_transaction(stmt_tx, [ledger_tx])
    assert match_res.status == "LIABILITY_PAYMENT"
    assert match_res.matched_transaction_id == ledger_tx.id
    assert match_res.score >= 0.90


# --- 5. Full End-to-End Statement Ingestion & Validation API Test ---


def test_statement_e2e_api_pipeline(tmp_path: Path):
    settings = Settings(
        app={"data_dir": tmp_path},
        database={"filename": "test.db"},
    )
    app = create_app(settings)
    client = TestClient(app)

    scapia_text = """
    Scapia Federal Credit Card
    Statement Date: 21 Jul 2026
    Payment Due Date: 08 Aug 2026
    Statement Period: 21 Jun 2026 to 20 Jul 2026
    
    Visa Credit Card ending in 0863
    RuPay Credit Card ending in 1221
    
    Statement Summary:
    Previous Balance: INR 0.00
    Transactions: INR 34,687.55
    Payments / Refunds: INR -100.64
    Total Amount Due: INR 34,586.91
    Minimum Amount Due: INR 1,729.35
    
    Transactions:
    22 Jun 2026 Swiggy Bangalore 450.00
    25 Jun 2026 Amazon India 1,704.00
    """
    pdf_bytes = _create_text_pdf([scapia_text])

    # Upload unencrypted Scapia PDF
    res = client.post(
        "/api/statements/upload",
        files={"file": ("Scapia_Jul_2026.pdf", pdf_bytes, "application/pdf")},
        data={"issuer": "SCAPIA"},
    )
    assert res.status_code == 200
    data = res.json()

    assert data["status"] in ("VALIDATED", "REVIEW_REQUIRED")
    assert data["validation_status"] == "VALIDATED"
    assert data["parser_name"] == "scapia"
    assert len(data["statement_accounts"]) == 2
    assert data["summary"]["total_due"] == 34586.91
    assert data["summary"]["minimum_due"] == 1729.35
    assert len(data["transactions"]) == 2

    statement_id = data["id"]

    # Test re-extract endpoint
    re_res = client.post(f"/api/statements/{statement_id}/re-extract")
    assert re_res.status_code == 200
    assert re_res.json()["validation_status"] == "VALIDATED"

    # Test reconcile endpoint
    rec_res = client.post(f"/api/statements/{statement_id}/reconcile")
    assert rec_res.status_code == 200
    assert rec_res.json()["success"] is True
