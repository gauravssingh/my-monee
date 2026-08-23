"""Golden-path integration tests for .mmb archive creation, verification, disaster recovery, and unified CLI."""

from __future__ import annotations

import argparse
from datetime import timedelta
from pathlib import Path
import pytest
from sqlalchemy.orm import Session

from expense_tracker.config import Settings
from expense_tracker.db.models import (
    Account,
    Category,
    ClassificationRule,
    Transaction,
    TransactionLink,
    utcnow,
)
from expense_tracker.db.session import get_session_factory
from expense_tracker.services.archive import (
    create_archive,
    restore_archive,
    verify_archive,
)
from expense_tracker.services.doctor import get_operational_status, run_diagnostics
from expense_tracker.cli.main import (
    cmd_db_integrity,
    cmd_doctor,
    cmd_version,
)


def test_mmb_archive_creation_and_verification(test_settings: Settings, db_session: Session):
    # 1. Populate test dataset
    acc = Account(
        account_type="BANK",
        name="HDFC Salary Account",
        account_number_masked="1234",
    )
    cat = db_session.query(Category).first()
    if not cat:
        cat = Category(name="Test Groceries", slug="test_groceries", sort_order=1)
        db_session.add(cat)
    db_session.add(acc)
    db_session.commit()

    tx = Transaction(
        account=acc.name,
        category_id=cat.id,
        source="hdfc_email",
        amount=1850.0,
        currency="INR",
        direction="debit",
        merchant_raw="NATURES BASKET BLR",
        merchant_normalized="Nature's Basket",
        description="Grocery shopping",
        transaction_date=utcnow(),
    )
    rule = ClassificationRule(
        merchant_normalized="Nature's Basket",
        category_id=cat.id,
        source="user",
    )
    db_session.add_all([tx, rule])
    db_session.commit()

    # Create dummy statement in statements dir
    stmts_dir = test_settings.resolved_data_dir() / "statements"
    stmts_dir.mkdir(parents=True, exist_ok=True)
    dummy_pdf = stmts_dir / "statement_aug_2026.pdf"
    dummy_pdf.write_bytes(b"%PDF-1.4 dummy statement content for testing")

    # 2. Create .mmb archive
    meta = create_archive(test_settings, note="Sprint 5 Golden Test Archive")
    assert meta["integrity_verified"] is True
    assert meta["metrics"]["transactions"] == 1
    assert meta["metrics"]["accounts"] == 1
    assert meta["metrics"]["rules"] == 1

    archive_path = Path(meta["path"])
    assert archive_path.exists()

    # 3. Verify .mmb archive
    verify_res = verify_archive(archive_path)
    assert verify_res["valid"] is True
    assert verify_res["format_version"] == 1
    assert verify_res["files_count"] >= 2  # database.sqlite + statement


def test_mmb_corruption_detection(test_settings: Settings, db_session: Session):
    # Add record and create archive
    tx = Transaction(
        source="test",
        amount=100.0,
        currency="INR",
        direction="debit",
        transaction_date=utcnow(),
    )
    db_session.add(tx)
    db_session.commit()

    meta = create_archive(test_settings, note="Integrity Test")
    archive_path = Path(meta["path"])

    # Corrupt archive file
    archive_path.write_bytes(b"CORRUPTED BYTES INVALID TAR")

    verify_res = verify_archive(archive_path)
    assert verify_res["valid"] is False
    assert "error" in verify_res


def test_disaster_recovery_golden_path(test_settings: Settings, db_session: Session):
    # 1. Setup rich financial ledger state
    acc = Account(
        account_type="CREDIT_CARD",
        name="Axis Atlas Card",
        card_last4="9876",
        is_liability=True,
    )
    cat = db_session.query(Category).first()
    db_session.add(acc)
    db_session.commit()

    tx1 = Transaction(
        card=acc.card_last4,
        category_id=cat.id,
        source="axis_email",
        amount=14500.0,
        currency="INR",
        direction="debit",
        merchant_raw="INDIGO AIRLINES GURGAON",
        merchant_normalized="IndiGo",
        transaction_date=utcnow() - timedelta(days=2),
    )
    tx2 = Transaction(
        card=acc.card_last4,
        category_id=cat.id,
        source="axis_email",
        amount=14500.0,
        currency="INR",
        direction="credit",
        merchant_raw="INDIGO AIRLINES REFUND",
        merchant_normalized="IndiGo",
        transaction_date=utcnow() - timedelta(days=1),
    )
    db_session.add_all([tx1, tx2])
    db_session.commit()

    # Link refund
    link = TransactionLink(
        from_transaction_id=tx1.id,
        to_transaction_id=tx2.id,
        kind="refund",
        confidence=1.0,
    )
    db_session.add(link)
    db_session.commit()

    # 2. Package into .mmb
    meta = create_archive(test_settings, note="Pre-disaster snapshot")
    archive_path = Path(meta["path"])

    # 3. Simulate disaster: delete user records in active database
    db_session.delete(link)
    db_session.delete(tx1)
    db_session.delete(tx2)
    db_session.delete(acc)
    db_session.commit()
    db_session.close()

    # 4. Perform transactional restore
    res = restore_archive(archive_path, test_settings)
    assert res["success"] is True

    # 5. Query fresh database session and verify 100% financial state restored
    SessionFactory = get_session_factory()
    with SessionFactory() as verify_session:
        acc_check = verify_session.query(Account).filter_by(card_last4="9876").first()
        assert acc_check is not None
        assert acc_check.name == "Axis Atlas Card"

        txs_check = verify_session.query(Transaction).filter_by(merchant_normalized="IndiGo").all()
        assert len(txs_check) == 2

        link_check = verify_session.query(TransactionLink).filter_by(kind="refund").first()
        assert link_check is not None


def test_doctor_and_status_diagnostics(test_settings: Settings, db_session: Session):
    # Test status
    status = get_operational_status(test_settings)
    assert status["database_healthy"] is True
    assert status["app_version"] == "0.8.0"

    # Test doctor
    diag = run_diagnostics(test_settings)
    assert diag["status"] in ["HEALTHY", "ATTENTION_NEEDED"]
    assert len(diag["checks"]) >= 5


def test_cli_commands_execution(test_settings: Settings, db_session: Session, capsys: pytest.CaptureFixture[str]):
    # cmd_version
    cmd_version(argparse.Namespace())
    out, _ = capsys.readouterr()
    assert "MyMonee v0.8.0" in out

    # cmd_db_integrity
    cmd_db_integrity(argparse.Namespace())
    out, _ = capsys.readouterr()
    assert "SQLite Integrity: ✓ PASS" in out

    # cmd_doctor
    cmd_doctor(argparse.Namespace())
    out, _ = capsys.readouterr()
    assert "MyMonee Doctor" in out
