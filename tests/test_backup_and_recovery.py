"""Tests for SQLite backup, recovery, diagnostics, and JSON portability."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from expense_tracker.app import create_app
from expense_tracker.config import Settings
from expense_tracker.db.models import Transaction, utcnow
from expense_tracker.db.session import get_session_factory
from expense_tracker.services.backup import (
    create_backup_snapshot,
    delete_backup,
    export_full_json_bundle,
    get_db_health,
    list_backups,
    restore_backup,
    vacuum_and_optimize,
)


def test_db_health_and_diagnostics(db_session: Session, test_settings: Settings):
    health = get_db_health(test_settings)
    assert health["healthy"] is True
    assert health["integrity_ok"] is True
    assert health["foreign_keys_ok"] is True
    assert health["database_size_bytes"] > 0
    assert "transactions" in health["table_metrics"]


def test_create_and_list_backups(db_session: Session, test_settings: Settings):
    # 1. Create a snapshot
    meta = create_backup_snapshot(test_settings, note="Automated test snapshot")
    assert meta["filename"].startswith("mymonee_backup_")
    assert meta["integrity_verified"] is True
    assert meta["size_bytes"] > 0

    # 2. List backups
    backups = list_backups(test_settings)
    assert len(backups) >= 1
    assert any(b["filename"] == meta["filename"] for b in backups)

    # 3. Delete backup
    deleted = delete_backup(meta["filename"], test_settings)
    assert deleted is True

    # 4. Verify gone
    backups_after = list_backups(test_settings)
    assert not any(b["filename"] == meta["filename"] for b in backups_after)


def test_vacuum_and_optimize(db_session: Session, test_settings: Settings):
    res = vacuum_and_optimize(test_settings)
    assert res["success"] is True
    assert "reclaimed_bytes" in res
    assert res["health"]["healthy"] is True


def test_restore_backup(test_settings: Settings, db_session: Session):
    # Add a test transaction
    tx = Transaction(
        source="test",
        amount=500.0,
        currency="INR",
        direction="debit",
        merchant_raw="Backup Test Merchant",
        description="Pre-backup transaction",
        transaction_date=utcnow(),
    )
    db_session.add(tx)
    db_session.commit()

    # Create backup containing the transaction
    meta = create_backup_snapshot(test_settings, note="Pre-delete snapshot")

    # Delete transaction in active database
    db_session.delete(tx)
    db_session.commit()
    db_session.close()

    # Restore from the backup snapshot
    res = restore_backup(meta["filename"], test_settings)
    assert res["success"] is True
    assert res["health"]["healthy"] is True

    # Re-query db with fresh session factory to verify data restored
    SessionFactory = get_session_factory()
    with SessionFactory() as verify_session:
        tx_check = verify_session.query(Transaction).filter_by(merchant_raw="Backup Test Merchant").first()
        assert tx_check is not None
        assert float(tx_check.amount) == 500.0


def test_export_full_json_bundle(db_session: Session):
    bundle = export_full_json_bundle(db_session)
    assert bundle["version"] == "1.0"
    assert "exported_at" in bundle
    assert "summary" in bundle
    assert isinstance(bundle["accounts"], list)
    assert isinstance(bundle["transactions"], list)
    assert isinstance(bundle["categories"], list)
    assert isinstance(bundle["rules"], list)


def test_backup_api_endpoints(test_settings: Settings):
    app = create_app(test_settings)
    client = TestClient(app)

    # Health check endpoint
    resp = client.get("/api/system/db-health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["healthy"] is True

    # Vacuum endpoint
    resp = client.post("/api/system/db-vacuum")
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # Create backup endpoint
    resp = client.post("/api/system/backups/create", json={"note": "API test"})
    assert resp.status_code == 200
    filename = resp.json()["filename"]

    # List backups endpoint
    resp = client.get("/api/system/backups")
    assert resp.status_code == 200
    assert any(b["filename"] == filename for b in resp.json())

    # Download backup endpoint
    resp = client.get(f"/api/system/backups/download/{filename}")
    assert resp.status_code == 200
    assert len(resp.content) > 0

    # Delete backup endpoint
    resp = client.delete(f"/api/system/backups/{filename}")
    assert resp.status_code == 200

    # Export bundle endpoint
    resp = client.get("/api/system/export-bundle")
    assert resp.status_code == 200
    export_data = resp.json()
    assert export_data["version"] == "1.0"
