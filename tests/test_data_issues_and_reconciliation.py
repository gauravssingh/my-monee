from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from mymonee.db.models import (
    CreditCardStatement,
    StatementTransaction,
    Transaction,
)
from mymonee.domain.enums import DataIssueStatus
from mymonee.services.data_issues import (
    flag_transaction_issue,
    flag_transactions_bulk,
    list_data_issues,
    resolve_data_issues_bulk,
    summarize_data_issues,
)
from mymonee.statements.reconciliation import (
    match_statement_transaction,
    reconcile_statement_in_db,
)


def test_data_issues_lifecycle(db_session: Session) -> None:
    # 1. Create a dummy transaction
    tx = Transaction(
        amount=Decimal("1500.00"),
        currency="INR",
        direction="debit",
        transaction_date=datetime(2026, 8, 15, 12, 0, 0, tzinfo=UTC),
        merchant_raw="TEST MERCHANT",
        merchant_normalized="Test Merchant",
        source="gmail:test",
    )
    db_session.add(tx)
    db_session.commit()

    # 2. Flag an issue
    issue = flag_transaction_issue(
        db_session,
        tx.id,
        issue_type="duplicate",
        field_name="amount",
        suggested_value="1200",
        note="Possible duplicate charge",
    )
    assert issue.id is not None
    assert issue.status == DataIssueStatus.OPEN
    assert issue.reported_value == "1500.0000"

    # 3. List data issues
    issues_list = list_data_issues(db_session, status="open")
    assert issues_list["total"] >= 1
    found = any(item["id"] == issue.id for item in issues_list["items"])
    assert found is True

    # 4. Summarize data issues
    summary = summarize_data_issues(db_session, status="open")
    assert len(summary) >= 1
    assert any(s["issue_type"] == "duplicate" for s in summary)

    # 5. Resolve data issue
    resolved = resolve_data_issues_bulk(
        db_session,
        issue_ids=[issue.id],
        status=DataIssueStatus.RESOLVED,
        resolved_note="Verified not a duplicate",
    )
    assert len(resolved) == 1
    assert resolved[0].status == DataIssueStatus.RESOLVED
    assert resolved[0].resolved_at is not None

    # Verify open count decreased
    open_issues = list_data_issues(db_session, status="open")
    assert not any(item["id"] == issue.id for item in open_issues["items"])


def test_flag_transactions_bulk(db_session: Session) -> None:
    tx1 = Transaction(
        amount=Decimal("200.00"),
        currency="INR",
        direction="debit",
        transaction_date=datetime(2026, 8, 1, tzinfo=UTC),
        source="gmail:test",
    )
    tx2 = Transaction(
        amount=Decimal("300.00"),
        currency="INR",
        direction="debit",
        transaction_date=datetime(2026, 8, 2, tzinfo=UTC),
        source="gmail:test",
    )
    db_session.add_all([tx1, tx2])
    db_session.commit()

    issues = flag_transactions_bulk(
        db_session,
        transaction_ids=[tx1.id, tx2.id],
        issue_type="not_a_transaction",
        note="Bulk OTP alert",
    )
    assert len(issues) == 2
    assert {i.transaction_id for i in issues} == {tx1.id, tx2.id}


def test_reconciliation_exact_upi_rrn_match(db_session: Session) -> None:
    # Statement tx with UPI RRN
    stmt_tx = StatementTransaction(
        statement_id="stmt-1",
        transaction_date=datetime(2026, 8, 10, tzinfo=UTC),
        description="UPI/P2M/800745883926/Swiggy Bangalore",
        amount=Decimal("450.00"),
    )

    # Ledger tx with matching RRN in reference
    ledger_tx = Transaction(
        amount=Decimal("450.00"),
        currency="INR",
        direction="debit",
        transaction_date=datetime(2026, 8, 10, tzinfo=UTC),
        merchant_raw="Swiggy",
        reference_number="800745883926",
    )

    result = match_statement_transaction(stmt_tx, [ledger_tx])
    assert result.status == "MATCHED"
    assert result.matched_transaction_id == ledger_tx.id
    assert result.score == 1.0
    assert "Exact UPI RRN match" in result.reason


def test_reconciliation_liability_payment_detection() -> None:
    stmt_tx = StatementTransaction(
        statement_id="stmt-1",
        transaction_date=datetime(2026, 8, 15, tzinfo=UTC),
        description="Scapia Credit Card Bill Payment",
        amount=Decimal("15000.00"),
        credit_amount=Decimal("15000.00"),
    )

    ledger_tx = Transaction(
        amount=Decimal("15000.00"),
        currency="INR",
        direction="credit",
        transaction_date=datetime(2026, 8, 15, tzinfo=UTC),
        merchant_raw="Scapia Billdesk",
        source="gmail:axis",
    )

    result = match_statement_transaction(stmt_tx, [ledger_tx])
    assert result.status == "LIABILITY_PAYMENT"
    assert result.matched_transaction_id == ledger_tx.id


def test_reconciliation_db_integration(db_session: Session) -> None:
    stmt = CreditCardStatement(
        issuer="Axis Bank Credit Card",
        card_last4="4951",
        original_filename="statement.pdf",
        statement_date=datetime(2026, 8, 20, tzinfo=UTC),
        statement_period_start=datetime(2026, 7, 20, tzinfo=UTC),
        statement_period_end=datetime(2026, 8, 19, tzinfo=UTC),
    )
    db_session.add(stmt)
    db_session.flush()

    # Create 2 statement txs
    st1 = StatementTransaction(
        statement_id=stmt.id,
        transaction_date=datetime(2026, 8, 5, tzinfo=UTC),
        description="AMAZON INDIA BANGALORE",
        amount=Decimal("2499.00"),
    )
    st2 = StatementTransaction(
        statement_id=stmt.id,
        transaction_date=datetime(2026, 8, 8, tzinfo=UTC),
        description="UNKNOWN UNMATCHED VENDOR",
        amount=Decimal("999.00"),
    )
    db_session.add_all([st1, st2])

    # Create 1 matching ledger tx
    lt1 = Transaction(
        amount=Decimal("2499.00"),
        currency="INR",
        direction="debit",
        transaction_date=datetime(2026, 8, 5, tzinfo=UTC),
        merchant_raw="AMAZON INDIA",
        merchant_normalized="Amazon",
    )
    db_session.add(lt1)
    db_session.commit()

    recon_summary = reconcile_statement_in_db(db_session, stmt.id)
    assert recon_summary["total_transactions"] == 2
    assert recon_summary["matched"] == 1
    assert recon_summary["unmatched"] == 1

    # Reload statement transactions
    db_session.refresh(st1)
    db_session.refresh(st2)
    assert st1.match_status == "MATCHED"
    assert st1.matched_transaction_id == lt1.id
    assert st2.match_status == "UNMATCHED"
