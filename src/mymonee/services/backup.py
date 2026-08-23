"""SQLite online backup, point-in-time snapshots, recovery, and diagnostics."""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mymonee.config import Settings, get_settings
from mymonee.db.models import (
    Account,
    Category,
    ClassificationRule,
    CreditCardStatement,
    DataIssueFlag,
    Email,
    Merchant,
    RecurringTransaction,
    Transaction,
    utcnow,
)
from mymonee.db.session import get_engine, get_session_factory

logger = logging.getLogger(__name__)


def _backups_dir(settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    d = settings.resolved_data_dir() / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_db_health(settings: Settings | None = None) -> dict[str, Any]:
    """Inspect SQLite database health, WAL status, integrity, and table metrics."""
    settings = settings or get_settings()
    db_path = settings.database_path()
    wal_path = Path(f"{db_path}-wal")
    shm_path = Path(f"{db_path}-shm")

    db_size = db_path.stat().st_size if db_path.exists() else 0
    wal_size = wal_path.stat().st_size if wal_path.exists() else 0
    shm_size = shm_path.stat().st_size if shm_path.exists() else 0

    integrity_ok = False
    foreign_keys_ok = False
    page_count = 0
    page_size = 4096
    freelist_count = 0

    if db_path.exists():
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            cur = conn.cursor()
            cur.execute("PRAGMA integrity_check;")
            res = cur.fetchone()
            integrity_ok = res[0] == "ok" if res else False

            cur.execute("PRAGMA foreign_key_check;")
            fk_res = cur.fetchall()
            foreign_keys_ok = len(fk_res) == 0

            cur.execute("PRAGMA page_count;")
            page_count = cur.fetchone()[0]

            cur.execute("PRAGMA page_size;")
            page_size = cur.fetchone()[0]

            cur.execute("PRAGMA freelist_count;")
            freelist_count = cur.fetchone()[0]

            conn.close()
        except Exception as e:
            logger.error("Failed to inspect SQLite health: %s", e)

    # Get row counts per table
    table_metrics: dict[str, int] = {}
    SessionFactory = get_session_factory()
    with SessionFactory() as session:
        try:
            table_metrics = {
                "transactions": session.scalar(select(func.count()).select_from(Transaction)) or 0,
                "emails": session.scalar(select(func.count()).select_from(Email)) or 0,
                "accounts": session.scalar(select(func.count()).select_from(Account)) or 0,
                "merchants": session.scalar(select(func.count()).select_from(Merchant)) or 0,
                "categories": session.scalar(select(func.count()).select_from(Category)) or 0,
                "rules": session.scalar(select(func.count()).select_from(ClassificationRule)) or 0,
                "recurring": session.scalar(select(func.count()).select_from(RecurringTransaction)) or 0,
                "statements": session.scalar(select(func.count()).select_from(CreditCardStatement)) or 0,
                "issues": session.scalar(select(func.count()).select_from(DataIssueFlag)) or 0,
            }
        except Exception as e:
            logger.error("Failed to query table counts: %s", e)

    fragmentation_pct = round((freelist_count / max(1, page_count)) * 100, 1)

    return {
        "healthy": integrity_ok and foreign_keys_ok,
        "integrity_ok": integrity_ok,
        "foreign_keys_ok": foreign_keys_ok,
        "database_size_bytes": db_size,
        "wal_size_bytes": wal_size,
        "total_disk_bytes": db_size + wal_size + shm_size,
        "page_count": page_count,
        "page_size": page_size,
        "freelist_pages": freelist_count,
        "fragmentation_pct": fragmentation_pct,
        "table_metrics": table_metrics,
    }


def vacuum_and_optimize(settings: Settings | None = None) -> dict[str, Any]:
    """Execute SQLite WAL checkpoint, VACUUM, and OPTIMIZE."""
    settings = settings or get_settings()
    db_path = settings.database_path()

    before_health = get_db_health(settings)
    before_size = before_health["total_disk_bytes"]

    try:
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        conn.execute("VACUUM;")
        conn.execute("PRAGMA optimize;")
        conn.close()
    except Exception as e:
        logger.error("Vacuum failed: %s", e)
        raise RuntimeError(f"Database vacuum failed: {e}") from e

    after_health = get_db_health(settings)
    after_size = after_health["total_disk_bytes"]
    reclaimed_bytes = max(0, before_size - after_size)

    return {
        "success": True,
        "before_bytes": before_size,
        "after_bytes": after_size,
        "reclaimed_bytes": reclaimed_bytes,
        "health": after_health,
    }


def create_backup_snapshot(
    settings: Settings | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Create a consistent online SQLite backup snapshot using sqlite3.Connection.backup()."""
    settings = settings or get_settings()
    source_db_path = settings.database_path()
    if not source_db_path.exists():
        raise FileNotFoundError(f"Database file not found at {source_db_path}")

    b_dir = _backups_dir(settings)
    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    backup_filename = f"mymonee_backup_{timestamp_str}.db"
    dest_path = b_dir / backup_filename

    # Online backup (safe while concurrent reads/writes happen)
    source_conn = sqlite3.connect(str(source_db_path))
    try:
        source_conn.execute("PRAGMA wal_checkpoint(FULL);")
    except Exception:
        pass
    dest_conn = sqlite3.connect(str(dest_path))
    with dest_conn:
        source_conn.backup(dest_conn)
    source_conn.close()
    dest_conn.close()

    # Verify backup integrity
    verify_conn = sqlite3.connect(f"file:{dest_path}?mode=ro", uri=True)
    cur = verify_conn.cursor()
    cur.execute("PRAGMA integrity_check;")
    res = cur.fetchone()
    integrity_ok = res[0] == "ok" if res else False
    verify_conn.close()

    if not integrity_ok:
        dest_path.unlink(missing_ok=True)
        raise RuntimeError("Created backup failed integrity verification.")

    file_size = dest_path.stat().st_size

    # Write metadata sidecar JSON
    meta = {
        "filename": backup_filename,
        "created_at": utcnow().isoformat(),
        "size_bytes": file_size,
        "integrity_verified": True,
        "note": note,
    }
    meta_path = b_dir / f"{backup_filename}.meta.json"
    meta_path.write_text(json.dumps(meta, indent=2))

    # Apply retention policy: Keep last 15 backups
    prune_old_backups(settings, keep_count=15)

    return meta


def list_backups(settings: Settings | None = None) -> list[dict[str, Any]]:
    """List all available backup snapshots ordered by newest first."""
    settings = settings or get_settings()
    b_dir = _backups_dir(settings)

    backups = []
    for f in sorted(b_dir.glob("mymonee_backup_*.db"), reverse=True):
        meta_path = b_dir / f"{f.name}.meta.json"
        meta: dict[str, Any] = {}
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text())
            except Exception:
                pass

        file_stat = f.stat()
        backups.append({
            "filename": f.name,
            "path": str(f),
            "size_bytes": file_stat.st_size,
            "created_at": meta.get("created_at") or datetime.fromtimestamp(file_stat.st_mtime, tz=timezone.utc).isoformat(),
            "integrity_verified": meta.get("integrity_verified", True),
            "note": meta.get("note"),
        })
    return backups


def delete_backup(filename: str, settings: Settings | None = None) -> bool:
    """Delete a specific backup snapshot."""
    settings = settings or get_settings()
    b_dir = _backups_dir(settings)
    target = b_dir / filename
    if target.exists() and target.is_file() and target.name.startswith("mymonee_backup_"):
        target.unlink(missing_ok=True)
        meta_path = b_dir / f"{filename}.meta.json"
        meta_path.unlink(missing_ok=True)
        return True
    return False


def prune_old_backups(settings: Settings | None = None, keep_count: int = 15) -> int:
    """Prune oldest backups exceeding keep_count."""
    backups = list_backups(settings)
    deleted = 0
    if len(backups) > keep_count:
        for b in backups[keep_count:]:
            if delete_backup(b["filename"], settings):
                deleted += 1
    return deleted


def restore_backup(
    filename: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Restore database from a selected backup snapshot with automatic safety snapshot."""
    settings = settings or get_settings()
    b_dir = _backups_dir(settings)
    backup_file = b_dir / filename

    if not backup_file.exists():
        raise FileNotFoundError(f"Backup file {filename} not found.")

    # 1. Verify candidate backup integrity first
    verify_conn = sqlite3.connect(f"file:{backup_file}?mode=ro", uri=True)
    cur = verify_conn.cursor()
    cur.execute("PRAGMA integrity_check;")
    res = cur.fetchone()
    if not res or res[0] != "ok":
        verify_conn.close()
        raise ValueError("Cannot restore: backup file failed integrity check.")
    verify_conn.close()

    # 2. Create pre-restore safety backup of active database
    safety_meta = None
    if settings.database_path().exists():
        try:
            safety_meta = create_backup_snapshot(settings, note="Pre-restore safety snapshot")
        except Exception as e:
            logger.warning("Could not create pre-restore snapshot: %s", e)

    # 3. Dispose active SQLAlchemy engine connection pool
    engine = get_engine()
    engine.dispose()

    # 4. Safe atomic restore using sqlite3 backup API
    target_db_path = settings.database_path()
    source_conn = sqlite3.connect(str(backup_file))
    dest_conn = sqlite3.connect(str(target_db_path))
    with dest_conn:
        source_conn.backup(dest_conn)
    source_conn.close()
    dest_conn.close()

    # Clean WAL & SHM files so restored database starts clean
    wal_path = Path(f"{target_db_path}-wal")
    shm_path = Path(f"{target_db_path}-shm")
    wal_path.unlink(missing_ok=True)
    shm_path.unlink(missing_ok=True)

    # Re-initialize engine with target settings
    from mymonee.db.session import init_engine
    init_engine(settings)

    # Check health of restored database
    health = get_db_health(settings)
    return {
        "success": True,
        "restored_file": filename,
        "safety_backup": safety_meta["filename"] if safety_meta else None,
        "health": health,
    }


def export_full_json_bundle(session: Session) -> dict[str, Any]:
    """Export complete ledger data (accounts, categories, rules, transactions, recurring) as JSON."""
    accounts = [
        {
            "id": a.id,
            "name": a.name,
            "account_type": a.account_type,
            "account_number_masked": a.account_number_masked,
            "card_last4": a.card_last4,
            "is_asset": a.is_asset,
            "is_liability": a.is_liability,
            "is_active": a.is_active,
        }
        for a in session.scalars(select(Account)).all()
    ]

    categories = [
        {
            "id": c.id,
            "name": c.name,
            "slug": c.slug,
            "sort_order": c.sort_order,
            "is_system": c.is_system,
            "expense_type": c.expense_type,
        }
        for c in session.scalars(select(Category)).all()
    ]

    rules = [
        {
            "id": r.id,
            "name": r.name,
            "merchant_normalized": r.merchant_normalized,
            "merchant_entity_id": r.merchant_entity_id,
            "upi_id": r.upi_id,
            "match_json": r.match_json,
            "category_id": r.category_id,
            "subcategory_id": r.subcategory_id,
            "priority": r.priority,
            "is_active": r.is_active,
            "source": r.source,
            "hit_count": r.hit_count,
        }
        for r in session.scalars(select(ClassificationRule)).all()
    ]

    recurring = [
        {
            "id": r.id,
            "name": r.name,
            "expected_amount": float(r.expected_amount) if r.expected_amount else None,
            "frequency": r.frequency,
            "expected_day": r.expected_day,
            "status": r.status,
        }
        for r in session.scalars(select(RecurringTransaction)).all()
    ]

    transactions = [
        {
            "id": t.id,
            "source": t.source,
            "amount": float(t.amount),
            "currency": t.currency,
            "direction": t.direction,
            "merchant_raw": t.merchant_raw,
            "merchant_normalized": t.merchant_normalized,
            "description": t.description,
            "category_id": t.category_id,
            "account": t.account,
            "transaction_date": t.transaction_date.isoformat() if t.transaction_date else None,
            "is_reviewed": t.is_reviewed,
            "is_transfer": t.is_transfer,
            "is_refund": t.is_refund,
            "excludes_from_spending": t.excludes_from_spending,
        }
        for t in session.scalars(select(Transaction).order_by(Transaction.transaction_date.desc())).all()
    ]

    return {
        "version": "1.0",
        "exported_at": utcnow().isoformat(),
        "summary": {
            "accounts_count": len(accounts),
            "categories_count": len(categories),
            "rules_count": len(rules),
            "recurring_count": len(recurring),
            "transactions_count": len(transactions),
        },
        "accounts": accounts,
        "categories": categories,
        "rules": rules,
        "recurring": recurring,
        "transactions": transactions,
    }
