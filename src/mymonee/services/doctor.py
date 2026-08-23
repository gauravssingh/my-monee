"""MyMonee Diagnostics and Operational Health Engine (Doctor & Status)."""

from __future__ import annotations

import logging
import os
import sqlite3
from typing import Any

from sqlalchemy import func, select

from mymonee.config import Settings, get_settings
from mymonee.db.models import (
    CreditCardStatement,
    Email,
    Transaction,
    utcnow,
)
from mymonee.db.session import get_session_factory
from mymonee.services.archive import APP_VERSION, MMB_FORMAT_VERSION, SCHEMA_VERSION, list_archives

logger = logging.getLogger(__name__)


def get_operational_status(settings: Settings | None = None) -> dict[str, Any]:
    """Fast operational state summary for CLI status command."""
    settings = settings or get_settings()
    db_path = settings.database_path()

    db_ok = db_path.exists()
    tx_count = 0
    needs_review_count = 0
    statements_count = 0
    last_sync_time = None

    if db_ok:
        try:
            SessionFactory = get_session_factory()
            with SessionFactory() as session:
                tx_count = session.scalar(select(func.count()).select_from(Transaction)) or 0
                needs_review_count = session.scalar(
                    select(func.count()).select_from(Transaction).where(Transaction.category_id.is_(None))
                ) or 0
                statements_count = session.scalar(select(func.count()).select_from(CreditCardStatement)) or 0

                # Check last email sync
                latest_email = session.scalars(select(Email).order_by(Email.received_at.desc()).limit(1)).first()
                if latest_email and latest_email.received_at:
                    last_sync_time = latest_email.received_at.isoformat()
        except Exception as e:
            logger.warning("Could not read database status: %s", e)
            db_ok = False

    # Check last backup
    archives = list_archives(settings)
    latest_archive = archives[0] if archives else None

    # Check gmail token
    gmail_token_file = settings.resolved_data_dir() / "gmail_token.json"
    gmail_connected = gmail_token_file.exists()

    return {
        "app_version": APP_VERSION,
        "database_healthy": db_ok,
        "gmail_connected": gmail_connected,
        "last_sync": last_sync_time,
        "transactions_count": tx_count,
        "needs_review_count": needs_review_count,
        "statements_count": statements_count,
        "last_backup": latest_archive.get("created_at") if latest_archive else None,
        "last_backup_verified": latest_archive.get("integrity_verified", False) if latest_archive else False,
    }


def run_diagnostics(settings: Settings | None = None) -> dict[str, Any]:
    """Deep system, database, storage, credentials, and backup diagnostic."""
    settings = settings or get_settings()
    data_dir = settings.resolved_data_dir()
    db_path = settings.database_path()

    checks: list[dict[str, Any]] = []
    remediations: list[str] = []

    # 1. Application
    checks.append({
        "category": "Application",
        "name": "Version",
        "status": "PASS",
        "detail": f"MyMonee v{APP_VERSION} (Schema: {SCHEMA_VERSION}, Archive: v{MMB_FORMAT_VERSION})",
    })

    # 2. Database Checks
    if not db_path.exists():
        checks.append({
            "category": "Database",
            "name": "SQLite Accessible",
            "status": "FAIL",
            "detail": f"Database file not found at {db_path}",
        })
        remediations.append("Run 'mymonee db init' or start the server to initialize the database.")
    else:
        checks.append({
            "category": "Database",
            "name": "SQLite Accessible",
            "status": "PASS",
            "detail": f"Found at {db_path}",
        })

        # Deep PRAGMAs
        try:
            conn = sqlite3.connect(str(db_path))
            cur = conn.cursor()

            # Journal Mode
            cur.execute("PRAGMA journal_mode;")
            j_mode = cur.fetchone()[0].lower()
            if j_mode == "wal":
                checks.append({
                    "category": "Database",
                    "name": "WAL Journal Mode",
                    "status": "PASS",
                    "detail": "WAL enabled",
                })
            else:
                checks.append({
                    "category": "Database",
                    "name": "WAL Journal Mode",
                    "status": "WARN",
                    "detail": f"Current mode: {j_mode} (WAL recommended for concurrency)",
                })
                remediations.append("Run 'mymonee db vacuum' to optimize and enable WAL.")

            # Foreign Keys
            cur.execute("PRAGMA foreign_keys;")
            fk_enabled = bool(cur.fetchone()[0])
            checks.append({
                "category": "Database",
                "name": "Foreign Keys",
                "status": "PASS" if fk_enabled else "WARN",
                "detail": "Enabled" if fk_enabled else "Disabled in connection defaults",
            })

            # Integrity Check
            cur.execute("PRAGMA integrity_check;")
            integ_res = cur.fetchone()[0]
            if integ_res == "ok":
                checks.append({
                    "category": "Database",
                    "name": "Integrity Check",
                    "status": "PASS",
                    "detail": "PRAGMA integrity_check passed",
                })
            else:
                checks.append({
                    "category": "Database",
                    "name": "Integrity Check",
                    "status": "FAIL",
                    "detail": f"Corrupted: {integ_res}",
                })
                remediations.append("Restore from a verified backup with 'mymonee backup restore <file>'.")

            conn.close()
        except Exception as e:
            checks.append({
                "category": "Database",
                "name": "SQLite Diagnostics",
                "status": "FAIL",
                "detail": str(e),
            })

    # 3. Storage Checks
    data_dir_writable = os.access(data_dir, os.W_OK | os.R_OK)
    checks.append({
        "category": "Storage",
        "name": "Data Directory Writable",
        "status": "PASS" if data_dir_writable else "FAIL",
        "detail": str(data_dir),
    })
    if not data_dir_writable:
        remediations.append(f"Ensure permissions allow write access to {data_dir}.")

    stmts_dir = data_dir / "statements"
    stmts_count = len(list(stmts_dir.glob("*"))) if stmts_dir.exists() else 0
    checks.append({
        "category": "Storage",
        "name": "Statements Storage",
        "status": "PASS",
        "detail": f"{stmts_count} files in {stmts_dir}",
    })

    # 4. Gmail Integration Checks
    gmail_token = data_dir / "gmail_token.json"
    if gmail_token.exists():
        checks.append({
            "category": "Gmail",
            "name": "OAuth Token",
            "status": "PASS",
            "detail": "Token file present",
        })
    else:
        checks.append({
            "category": "Gmail",
            "name": "OAuth Token",
            "status": "WARN",
            "detail": "No token found (Gmail sync inactive)",
        })
        remediations.append("Authenticate via Settings -> Gmail to enable automated email sync.")

    # 5. Backup Checks
    archives = list_archives(settings)
    if archives:
        checks.append({
            "category": "Backup",
            "name": "Archive Status",
            "status": "PASS",
            "detail": f"{len(archives)} archives (Latest: {archives[0]['filename']})",
        })
    else:
        checks.append({
            "category": "Backup",
            "name": "Archive Status",
            "status": "WARN",
            "detail": "No .mmb backup archives created yet",
        })
        remediations.append("Create your first archive with 'mymonee backup create'.")

    all_pass = all(c["status"] == "PASS" for c in checks)
    has_fails = any(c["status"] == "FAIL" for c in checks)
    overall = "HEALTHY" if all_pass else ("CRITICAL" if has_fails else "ATTENTION_NEEDED")

    return {
        "status": overall,
        "timestamp": utcnow().isoformat(),
        "checks": checks,
        "remediations": remediations,
    }
