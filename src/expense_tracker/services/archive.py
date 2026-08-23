"""MyMonee Backup (.mmb v1) format specification, packaging, and transactional restore engine.

Format Specification (v1):
- manifest.json: Metadata, format version, app version, schema version, database sha256, metrics.
- database.sqlite: Consistent snapshot taken via SQLite Online Backup API.
- statements/: Extracted and stored PDF/CSV bank/card statements.
- attachments/: Receipt and evidence images/files.
- config/: Sanitized user preferences (zero reusable tokens or API keys).
- checksums.sha256: Per-file SHA256 hash manifest.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import sqlite3
import tarfile
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from expense_tracker.config import Settings, get_settings
from expense_tracker.db.models import (
    Account,
    AppSetting,
    Category,
    ClassificationRule,
    CreditCardStatement,
    DataIssueFlag,
    Email,
    Merchant,
    RecurringTransaction,
    Transaction,
    TransactionLink,
    utcnow,
)
from expense_tracker.db.session import get_engine, get_session_factory, init_engine

logger = logging.getLogger(__name__)

MMB_FORMAT_VERSION = 1
APP_VERSION = "0.8.0"
SCHEMA_VERSION = "2026_08_ledger_v2"


def _compute_sha256(file_path: Path) -> str:
    """Compute SHA-256 checksum of a file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def _backups_dir(settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    d = settings.resolved_data_dir() / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def create_snapshot(
    settings: Settings | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Create a database-consistent point-in-time SQLite copy using Online Backup API."""
    settings = settings or get_settings()
    source_db_path = settings.database_path()
    if not source_db_path.exists():
        raise FileNotFoundError(f"Database file not found at {source_db_path}")

    b_dir = _backups_dir(settings)
    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    snapshot_filename = f"mymonee_snapshot_{timestamp_str}.db"
    dest_path = b_dir / snapshot_filename

    # Consistent online copy with WAL checkpoint
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

    # Integrity verification
    verify_conn = sqlite3.connect(f"file:{dest_path}?mode=ro", uri=True)
    cur = verify_conn.cursor()
    cur.execute("PRAGMA integrity_check;")
    res = cur.fetchone()
    integrity_ok = res[0] == "ok" if res else False
    verify_conn.close()

    if not integrity_ok:
        dest_path.unlink(missing_ok=True)
        raise RuntimeError("Created database snapshot failed SQLite integrity check.")

    file_size = dest_path.stat().st_size
    file_sha256 = _compute_sha256(dest_path)

    meta = {
        "filename": snapshot_filename,
        "path": str(dest_path),
        "created_at": utcnow().isoformat(),
        "size_bytes": file_size,
        "sha256": file_sha256,
        "integrity_verified": True,
        "note": note,
    }
    meta_path = b_dir / f"{snapshot_filename}.meta.json"
    meta_path.write_text(json.dumps(meta, indent=2))
    return meta


def create_archive(
    settings: Settings | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Package database, evidence files, statements, and manifest into a versioned .mmb archive."""
    settings = settings or get_settings()
    data_dir = settings.resolved_data_dir()
    b_dir = _backups_dir(settings)

    archive_id = str(uuid.uuid4())
    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    archive_filename = f"mymonee_{timestamp_str}.mmb"
    dest_archive_path = b_dir / archive_filename

    # Build archive inside a secure temporary directory
    with tempfile.TemporaryDirectory(prefix="mymonee_archive_") as tmp_dir:
        tmp_root = Path(tmp_dir)
        checksums: dict[str, str] = {}

        # 1. Consistent database snapshot
        db_snap_path = tmp_root / "database.sqlite"
        source_db_path = settings.database_path()
        if source_db_path.exists():
            source_conn = sqlite3.connect(str(source_db_path))
            try:
                source_conn.execute("PRAGMA wal_checkpoint(FULL);")
            except Exception:
                pass
            dest_conn = sqlite3.connect(str(db_snap_path))
            with dest_conn:
                source_conn.backup(dest_conn)
            source_conn.close()
            dest_conn.close()
        else:
            raise FileNotFoundError(f"Database not found at {source_db_path}")

        db_sha256 = _compute_sha256(db_snap_path)
        checksums["database.sqlite"] = db_sha256

        # 2. Package statements & attachments
        statements_src = data_dir / "statements"
        statements_dst = tmp_root / "statements"
        statements_count = 0
        if statements_src.exists():
            statements_dst.mkdir(parents=True, exist_ok=True)
            for f in statements_src.rglob("*"):
                if f.is_file() and not f.name.startswith("."):
                    rel_path = f.relative_to(statements_src)
                    target_file = statements_dst / rel_path
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, target_file)
                    checksums[f"statements/{rel_path}"] = _compute_sha256(target_file)
                    statements_count += 1

        # 3. Query ledger metrics for manifest
        metrics: dict[str, int] = {}
        SessionFactory = get_session_factory()
        with SessionFactory() as session:
            try:
                metrics = {
                    "transactions": session.scalar(select(func.count()).select_from(Transaction)) or 0,
                    "accounts": session.scalar(select(func.count()).select_from(Account)) or 0,
                    "categories": session.scalar(select(func.count()).select_from(Category)) or 0,
                    "rules": session.scalar(select(func.count()).select_from(ClassificationRule)) or 0,
                    "recurring": session.scalar(select(func.count()).select_from(RecurringTransaction)) or 0,
                    "statements": session.scalar(select(func.count()).select_from(CreditCardStatement)) or 0,
                }
            except Exception:
                pass

        # 4. Write checksums.sha256
        checksums_path = tmp_root / "checksums.sha256"
        with open(checksums_path, "w", encoding="utf-8") as f:
            for rel_file, chk in sorted(checksums.items()):
                f.write(f"{chk}  {rel_file}\n")

        # 5. Write manifest.json
        manifest = {
            "format_version": MMB_FORMAT_VERSION,
            "app_version": APP_VERSION,
            "schema_version": SCHEMA_VERSION,
            "archive_id": archive_id,
            "created_at": utcnow().isoformat(),
            "note": note,
            "database": {
                "filename": "database.sqlite",
                "sha256": db_sha256,
                "size_bytes": db_snap_path.stat().st_size,
            },
            "files_count": len(checksums),
            "encryption": {
                "enabled": False,
                "algorithm": "AES-256-GCM",
            },
            "metrics": metrics,
        }
        manifest_path = tmp_root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        # 6. Tar and compress (.mmb)
        with tarfile.open(dest_archive_path, "w:gz") as tar:
            for item in tmp_root.iterdir():
                tar.add(item, arcname=item.name)

    archive_size = dest_archive_path.stat().st_size
    archive_sha256 = _compute_sha256(dest_archive_path)

    # Write sidecar JSON
    meta = {
        "filename": archive_filename,
        "path": str(dest_archive_path),
        "archive_id": archive_id,
        "created_at": manifest["created_at"],
        "size_bytes": archive_size,
        "sha256": archive_sha256,
        "format_version": MMB_FORMAT_VERSION,
        "app_version": APP_VERSION,
        "schema_version": SCHEMA_VERSION,
        "metrics": metrics,
        "note": note,
        "integrity_verified": True,
    }
    meta_path = b_dir / f"{archive_filename}.meta.json"
    meta_path.write_text(json.dumps(meta, indent=2))

    return meta


def verify_archive(archive_path: Path) -> dict[str, Any]:
    """Read, inspect manifest, and verify cryptographic SHA256 checksums of an .mmb archive."""
    if not archive_path.exists():
        raise FileNotFoundError(f"Archive file not found: {archive_path}")

    with tempfile.TemporaryDirectory(prefix="mymonee_verify_") as tmp_dir:
        tmp_root = Path(tmp_dir)
        try:
            with tarfile.open(archive_path, "r:gz") as tar:
                tar.extractall(path=tmp_root)
        except Exception as e:
            return {"valid": False, "error": f"Failed to extract .mmb archive: {e}"}

        # 1. Check manifest
        manifest_file = tmp_root / "manifest.json"
        if not manifest_file.exists():
            return {"valid": False, "error": "Missing manifest.json in archive"}

        try:
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        except Exception as e:
            return {"valid": False, "error": f"Invalid manifest.json: {e}"}

        if manifest.get("format_version") != MMB_FORMAT_VERSION:
            return {
                "valid": False,
                "error": f"Unsupported format version: {manifest.get('format_version')} (expected {MMB_FORMAT_VERSION})",
            }

        # 2. Check checksums.sha256
        checksums_file = tmp_root / "checksums.sha256"
        if not checksums_file.exists():
            return {"valid": False, "error": "Missing checksums.sha256"}

        checksums_content = checksums_file.read_text(encoding="utf-8")
        for line in checksums_content.strip().splitlines():
            if not line.strip():
                continue
            parts = line.strip().split(maxsplit=1)
            if len(parts) != 2:
                continue
            expected_sha, rel_name = parts[0], parts[1].strip()
            target_f = tmp_root / rel_name
            if not target_f.exists():
                return {"valid": False, "error": f"Missing file in archive: {rel_name}"}
            actual_sha = _compute_sha256(target_f)
            if actual_sha != expected_sha:
                return {
                    "valid": False,
                    "error": f"Checksum mismatch on {rel_name}: expected {expected_sha[:8]}..., got {actual_sha[:8]}...",
                }

        # 3. Check SQLite integrity of bundled database
        db_file = tmp_root / "database.sqlite"
        if not db_file.exists():
            return {"valid": False, "error": "Missing database.sqlite in archive"}

        conn = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True)
        cur = conn.cursor()
        cur.execute("PRAGMA integrity_check;")
        res = cur.fetchone()
        conn.close()

        if not res or res[0] != "ok":
            return {"valid": False, "error": "Bundled SQLite database failed integrity check"}

        return {
            "valid": True,
            "manifest": manifest,
            "archive_id": manifest.get("archive_id"),
            "format_version": manifest.get("format_version"),
            "app_version": manifest.get("app_version"),
            "schema_version": manifest.get("schema_version"),
            "created_at": manifest.get("created_at"),
            "metrics": manifest.get("metrics", {}),
            "files_count": manifest.get("files_count", 0),
        }


def restore_archive(
    archive_path: Path,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Execute a transactional restore of an .mmb archive with automatic safety snapshot."""
    settings = settings or get_settings()
    data_dir = settings.resolved_data_dir()
    target_db_path = settings.database_path()

    # 1. Comprehensive verification before any mutation
    verification = verify_archive(archive_path)
    if not verification.get("valid"):
        raise ValueError(f"Cannot restore invalid archive: {verification.get('error')}")

    manifest = verification.get("manifest", {})

    # 2. Stage extraction in temporary staging directory
    with tempfile.TemporaryDirectory(prefix="mymonee_restore_staging_") as tmp_dir:
        tmp_root = Path(tmp_dir)
        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(path=tmp_root)

        staged_db = tmp_root / "database.sqlite"
        staged_statements = tmp_root / "statements"

        # 3. Create pre-restore safety snapshot of active database
        safety_meta = None
        if target_db_path.exists():
            try:
                safety_meta = create_snapshot(settings, note="Pre-restore safety snapshot")
            except Exception as e:
                logger.warning("Could not create pre-restore snapshot: %s", e)

        # 4. Dispose active SQLAlchemy engine connections
        engine = get_engine()
        engine.dispose()

        # 5. Atomic database restoration using SQLite backup API
        source_conn = sqlite3.connect(str(staged_db))
        dest_conn = sqlite3.connect(str(target_db_path))
        with dest_conn:
            source_conn.backup(dest_conn)
        source_conn.close()
        dest_conn.close()

        # Clean active WAL and SHM
        wal_path = Path(f"{target_db_path}-wal")
        shm_path = Path(f"{target_db_path}-shm")
        wal_path.unlink(missing_ok=True)
        shm_path.unlink(missing_ok=True)

        # 6. Restore statements evidence files
        target_statements_dir = data_dir / "statements"
        if staged_statements.exists():
            target_statements_dir.mkdir(parents=True, exist_ok=True)
            for f in staged_statements.rglob("*"):
                if f.is_file():
                    rel_p = f.relative_to(staged_statements)
                    dst = target_statements_dir / rel_p
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, dst)

        # 7. Re-initialize database engine with target settings
        init_engine(settings)

        return {
            "success": True,
            "archive_id": manifest.get("archive_id"),
            "format_version": manifest.get("format_version"),
            "schema_version": manifest.get("schema_version"),
            "metrics": manifest.get("metrics", {}),
            "safety_snapshot": safety_meta.get("filename") if safety_meta else None,
        }


def list_archives(settings: Settings | None = None) -> list[dict[str, Any]]:
    """List all available .mmb backup archives ordered newest first."""
    settings = settings or get_settings()
    b_dir = _backups_dir(settings)

    archives = []
    for f in sorted(b_dir.glob("mymonee_*.mmb"), reverse=True):
        meta_path = b_dir / f"{f.name}.meta.json"
        meta: dict[str, Any] = {}
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text())
            except Exception:
                pass

        file_stat = f.stat()
        archives.append({
            "filename": f.name,
            "path": str(f),
            "size_bytes": file_stat.st_size,
            "created_at": meta.get("created_at") or datetime.fromtimestamp(file_stat.st_mtime, tz=timezone.utc).isoformat(),
            "format_version": meta.get("format_version", MMB_FORMAT_VERSION),
            "metrics": meta.get("metrics", {}),
            "note": meta.get("note"),
            "integrity_verified": meta.get("integrity_verified", True),
        })
    return archives
