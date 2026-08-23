"""Portability matrix, fresh-install contract, and container health tests."""

from __future__ import annotations

import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from expense_tracker.app import create_app
from expense_tracker.config import AppConfig, DatabaseConfig, LoggingConfig, Settings
from expense_tracker.db.models import (
    Account,
    Category,
    CreditCardStatement,
    Transaction,
    utcnow,
)
from expense_tracker.db.session import get_session_factory, init_db
from expense_tracker.services.archive import create_archive, restore_archive, verify_archive
from expense_tracker.services.doctor import run_diagnostics


def test_fresh_installation_filesystem_contract(tmp_path: Path):
    fresh_data_dir = tmp_path / "fresh_container_data"
    fresh_settings = Settings(
        app=AppConfig(data_dir=fresh_data_dir),
        database=DatabaseConfig(filename="mymonee.db"),
        logging=LoggingConfig(file=fresh_data_dir / "logs" / "app.log"),
    )

    # 1. Initialize application on empty directory
    app = create_app(fresh_settings)
    client = TestClient(app)

    # 2. Verify explicit filesystem contract directories exist
    resolved = fresh_settings.resolved_data_dir()
    assert (resolved / "db").is_dir()
    assert (resolved / "statements").is_dir()
    assert (resolved / "evidence").is_dir()
    assert (resolved / "attachments").is_dir()
    assert (resolved / "backups").is_dir()
    assert (resolved / "exports").is_dir()
    assert (resolved / "tmp").is_dir()
    assert (resolved / "logs").is_dir()

    # 3. Verify SQLite DB was initialized
    assert fresh_settings.database_path().exists()

    # 4. Verify doctor passes on fresh installation
    diag = run_diagnostics(fresh_settings)
    assert diag["status"] in ["HEALTHY", "ATTENTION_NEEDED"]


def test_container_health_endpoints(test_settings: Settings):
    app = create_app(test_settings)
    client = TestClient(app)

    # 1. Liveness
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}

    res_live = client.get("/health/live")
    assert res_live.status_code == 200
    assert res_live.json() == {"status": "ok"}

    # 2. Readiness
    res_ready = client.get("/health/ready")
    assert res_ready.status_code == 200
    data = res_ready.json()
    assert data["ready"] is True
    assert data["status"] == "ok"
    assert data["database"] == "connected"
    # Ensure no sensitive paths/emails/numbers leaked
    assert "email" not in str(data).lower()
    assert "/" not in str(data["database"])


def test_cross_runtime_portability_matrix(tmp_path: Path):
    # Runtime A: Source environment (e.g. macOS native)
    dir_a = tmp_path / "runtime_a"
    settings_a = Settings(
        app=AppConfig(data_dir=dir_a),
        database=DatabaseConfig(filename="mymonee.db"),
        logging=LoggingConfig(file=dir_a / "logs" / "app.log"),
    )
    init_db(settings_a)

    # Seed data in Runtime A
    SessionFactoryA = get_session_factory()
    with SessionFactoryA() as s_a:
        cat = s_a.query(Category).first()
        acc = Account(
            name="Primary Savings",
            account_type="BANK",
            account_number_masked="5544",
        )
        s_a.add(acc)
        s_a.commit()

        tx = Transaction(
            account=acc.name,
            category_id=cat.id,
            source="bank",
            amount=2450.0,
            currency="INR",
            direction="debit",
            merchant_raw="APPLE SERVICES MUMBAI",
            merchant_normalized="Apple",
            transaction_date=utcnow(),
        )
        s_a.add(tx)
        s_a.commit()

    # Add statement file in Runtime A
    stmt_file = dir_a / "statements" / "apple_receipt.pdf"
    stmt_file.write_bytes(b"%PDF-1.4 Mock Receipt for Portability Test")

    # Create .mmb archive in Runtime A
    meta_a = create_archive(settings_a, note="Runtime A to Runtime B export")
    archive_file = Path(meta_a["path"])
    assert archive_file.exists()

    # Runtime B: Destination environment (e.g. Linux Docker Container mount)
    dir_b = tmp_path / "runtime_b_docker"
    settings_b = Settings(
        app=AppConfig(data_dir=dir_b),
        database=DatabaseConfig(filename="mymonee.db"),
        logging=LoggingConfig(file=dir_b / "logs" / "app.log"),
    )
    init_db(settings_b)

    # Restore .mmb archive into Runtime B
    res_restore = restore_archive(archive_file, settings_b)
    assert res_restore["success"] is True

    # Verify Runtime B has identical financial truth and statement evidence
    SessionFactoryB = get_session_factory()
    with SessionFactoryB() as s_b:
        acc_b = s_b.query(Account).filter_by(account_number_masked="5544").first()
        assert acc_b is not None
        assert acc_b.name == "Primary Savings"

        tx_b = s_b.query(Transaction).filter_by(merchant_normalized="Apple").first()
        assert tx_b is not None
        assert float(tx_b.amount) == 2450.0

    # Verify statement file was restored into Runtime B
    restored_stmt = dir_b / "statements" / "apple_receipt.pdf"
    assert restored_stmt.exists()
    assert restored_stmt.read_bytes() == b"%PDF-1.4 Mock Receipt for Portability Test"

    # Runtime B -> Runtime C roundtrip
    meta_b = create_archive(settings_b, note="Runtime B to Runtime C roundtrip")
    archive_b_file = Path(meta_b["path"])
    verify_b = verify_archive(archive_b_file)
    assert verify_b["valid"] is True
    assert verify_b["metrics"]["transactions"] == 1
