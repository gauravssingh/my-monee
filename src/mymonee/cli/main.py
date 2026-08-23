"""Unified CLI entrypoint for MyMonee.

Supports running directly against the local SQLite database or against a running server.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from mymonee.config import load_settings
from mymonee.db.session import init_db
from mymonee.services.archive import (
    APP_VERSION,
    MMB_FORMAT_VERSION,
    SCHEMA_VERSION,
    create_archive,
    create_snapshot,
    list_archives,
    restore_archive,
    verify_archive,
)
from mymonee.services.backup import (
    export_full_json_bundle,
    get_db_health,
    list_backups,
    restore_backup,
    vacuum_and_optimize,
)
from mymonee.services.doctor import get_operational_status, run_diagnostics
from mymonee.services.reconciliation import run_full_reconciliation


def cmd_version(args: argparse.Namespace) -> None:
    print(f"MyMonee v{APP_VERSION}")
    print(f"  • Schema Version: {SCHEMA_VERSION}")
    print(f"  • Archive Format: v{MMB_FORMAT_VERSION} (.mmb)")


def cmd_status(args: argparse.Namespace) -> None:
    settings = load_settings()
    init_db(settings)
    st = get_operational_status(settings)

    print(f"MyMonee v{st['app_version']}\n")
    print(f"  Database        {'✓ Healthy' if st['database_healthy'] else '✗ Unhealthy'}")
    print(f"  Gmail           {'✓ Connected' if st['gmail_connected'] else '○ Disconnected'}")
    print(f"  Last Sync       {st['last_sync'] or 'Never'}")
    print(f"  Transactions    {st['transactions_count']:,}")
    print(f"  Needs Review    {st['needs_review_count']:,}")
    print(f"  Statements      {st['statements_count']:,}")
    print(f"  Last Backup     {st['last_backup'] or 'None'} ({'Verified ✓' if st['last_backup_verified'] else 'Unverified'})")


def cmd_doctor(args: argparse.Namespace) -> None:
    settings = load_settings()
    init_db(settings)
    diag = run_diagnostics(settings)

    print("MyMonee Doctor")
    print("────────────────────────────────────────────\n")

    current_cat = None
    for c in diag["checks"]:
        if c["category"] != current_cat:
            current_cat = c["category"]
            print(f"{current_cat}")

        icon = "✓" if c["status"] == "PASS" else ("!" if c["status"] == "WARN" else "✗")
        print(f"  {icon} {c['name']}: {c['detail']}")

    print(f"\nResult: {diag['status']}")

    if diag["remediations"]:
        print("\nSuggested Action:")
        for r in diag["remediations"]:
            print(f"  • {r}")


def cmd_backup_create(args: argparse.Namespace) -> None:
    settings = load_settings()
    init_db(settings)
    if args.snapshot_only:
        print("Creating point-in-time SQLite snapshot…")
        meta = create_snapshot(settings, note=args.note)
        print(f"✓ Snapshot created: {meta['filename']} ({meta['size_bytes']} bytes)")
    else:
        print("Creating complete .mmb backup archive (database + evidence + manifest)…")
        meta = create_archive(settings, note=args.note)
        print(f"✓ Archive created: {meta['filename']} ({meta['size_bytes']:,} bytes)")
        print(f"  Archive ID: {meta['archive_id']}")
        print(f"  Transactions: {meta['metrics'].get('transactions', 0):,}")


def cmd_backup_list(args: argparse.Namespace) -> None:
    settings = load_settings()
    init_db(settings)
    archives = list_archives(settings)
    snapshots = list_backups(settings)

    print(f"MyMonee Backup Archives ({len(archives)} archives, {len(snapshots)} snapshots):\n")
    if not archives and not snapshots:
        print("  No backups found. Create one with 'mymonee backup create'.")
        return

    if archives:
        print("  [Portable .mmb Archives]")
        for a in archives:
            print(f"  • {a['filename']} ({a['size_bytes']:,} B) - {a['created_at']}")

    if snapshots:
        print("\n  [Point-in-Time SQLite Snapshots]")
        for s in snapshots:
            print(f"  • {s['filename']} ({s['size_bytes']:,} B) - {s['created_at']}")


def cmd_backup_verify(args: argparse.Namespace) -> None:
    settings = load_settings()
    init_db(settings)
    path = Path(args.path)
    if not path.is_absolute():
        b_dir = settings.resolved_data_dir() / "backups"
        if (b_dir / path).exists():
            path = b_dir / path

    print(f"Verifying backup integrity for: {path.name}…")
    if path.name.endswith(".mmb"):
        res = verify_archive(path)
        if res.get("valid"):
            print("✓ Archive verification PASSED")
            print(f"  Format Version: v{res.get('format_version')}")
            print(f"  App Version:    v{res.get('app_version')}")
            print(f"  Files Count:    {res.get('files_count')}")
            print(f"  Transactions:   {res.get('metrics', {}).get('transactions', 0):,}")
        else:
            print(f"✗ Verification FAILED: {res.get('error')}")
            sys.exit(1)
    else:
        # SQLite db snapshot
        import sqlite3
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        cur = conn.cursor()
        cur.execute("PRAGMA integrity_check;")
        check = cur.fetchone()
        conn.close()
        if check and check[0] == "ok":
            print("✓ SQLite snapshot integrity check PASSED (PRAGMA ok)")
        else:
            print(f"✗ SQLite snapshot integrity check FAILED: {check}")
            sys.exit(1)


def cmd_backup_restore(args: argparse.Namespace) -> None:
    settings = load_settings()
    init_db(settings)
    path = Path(args.path)
    if not path.is_absolute():
        b_dir = settings.resolved_data_dir() / "backups"
        if (b_dir / path).exists():
            path = b_dir / path

    print(f"Starting transactional restore from: {path.name}…")
    if path.name.endswith(".mmb"):
        res = restore_archive(path, settings)
        print("✓ Restore completed successfully!")
        if res.get("safety_snapshot"):
            print(f"  Pre-restore safety snapshot saved to: {res['safety_snapshot']}")
    else:
        res = restore_backup(path.name, settings)
        print("✓ SQLite snapshot restored successfully!")


def cmd_db_integrity(args: argparse.Namespace) -> None:
    settings = load_settings()
    init_db(settings)
    health = get_db_health(settings)
    print(f"SQLite Integrity: {'✓ PASS' if health['integrity_ok'] else '✗ FAIL'}")
    print(f"Foreign Keys:     {'✓ PASS' if health['foreign_keys_ok'] else '✗ FAIL'}")
    print(f"Total Disk:       {health['total_disk_bytes']:,} bytes")
    print(f"Database Size:    {health['database_size_bytes']:,} bytes")
    print(f"WAL Journal Size: {health['wal_size_bytes']:,} bytes")


def cmd_db_vacuum(args: argparse.Namespace) -> None:
    settings = load_settings()
    init_db(settings)
    print("Running WAL checkpoint, VACUUM, and B-Tree optimization…")
    res = vacuum_and_optimize(settings)
    print(f"✓ Vacuum and optimize complete. Reclaimed {res['reclaimed_bytes']:,} bytes.")


def cmd_reconcile(args: argparse.Namespace) -> None:
    settings = load_settings()
    init_db(settings)
    from mymonee.db.session import get_session_factory
    SessionFactory = get_session_factory()
    with SessionFactory() as session:
        print("Running transfer and refund reconciliation…")
        stats = run_full_reconciliation(session)
        print("✓ Reconciliation complete:")
        print(f"  • Matched Transfers: {stats.get('transfers_paired', 0)}")
        print(f"  • Matched Refunds:   {stats.get('refunds_paired', 0)}")


def cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn
    from mymonee.config import reload_settings
    from mymonee.logging_setup import setup_logging

    settings = reload_settings()
    setup_logging(settings)
    host = args.host or settings.app.host
    port = args.port or settings.app.port
    print(f"Starting MyMonee Server on http://{host}:{port}…")
    uvicorn.run(
        "mymonee.app:create_app",
        factory=True,
        host=host,
        port=port,
        reload=args.reload,
        log_level=settings.logging.level.lower(),
    )


def cmd_data_export(args: argparse.Namespace) -> None:
    settings = load_settings()
    init_db(settings)
    bundle = export_full_json_bundle(settings)
    out_file = Path(args.output or "mymonee_ledger_export.json")
    out_file.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    print(f"✓ JSON bundle exported to {out_file} ({out_file.stat().st_size:,} bytes)")


def main() -> None:
    parser = argparse.ArgumentParser(prog="mymonee", description="MyMonee Local-First Expense Ledger CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # serve
    p_serve = subparsers.add_parser("serve", help="Start the MyMonee Web UI & API server")
    p_serve.add_argument("--host", default=None, help="Bind host (default from config)")
    p_serve.add_argument("--port", type=int, default=None, help="Bind port (default from config)")
    p_serve.add_argument("--reload", action="store_true", help="Dev auto-reload")
    p_serve.set_defaults(func=cmd_serve)

    # version
    p_ver = subparsers.add_parser("version", help="Show application version and schema details")
    p_ver.set_defaults(func=cmd_version)

    # status
    p_status = subparsers.add_parser("status", help="Quick operational status")
    p_status.set_defaults(func=cmd_status)

    # doctor
    p_doc = subparsers.add_parser("doctor", help="Deep system and database diagnostics")
    p_doc.set_defaults(func=cmd_doctor)

    # reconcile
    p_rec = subparsers.add_parser("reconcile", help="Reconcile transfers and refund pairings")
    p_rec.add_argument("--lookback", type=int, default=90, help="Days to look back")
    p_rec.set_defaults(func=cmd_reconcile)

    # backup
    p_backup = subparsers.add_parser("backup", help="Manage backup snapshots and .mmb archives")
    backup_sub = p_backup.add_subparsers(dest="backup_cmd", help="Backup subcommands")

    p_b_create = backup_sub.add_parser("create", help="Create a backup")
    p_b_create.add_argument("--note", type=str, help="Optional note")
    p_b_create.add_argument("--snapshot-only", action="store_true", help="Create .db snapshot instead of .mmb archive")
    p_b_create.set_defaults(func=cmd_backup_create)

    p_b_list = backup_sub.add_parser("list", help="List backups")
    p_b_list.set_defaults(func=cmd_backup_list)

    p_b_verify = backup_sub.add_parser("verify", help="Verify backup checksum and SQLite integrity")
    p_b_verify.add_argument("path", type=str, help="Filename or path to backup file")
    p_b_verify.set_defaults(func=cmd_backup_verify)

    p_b_restore = backup_sub.add_parser("restore", help="Restore database from backup")
    p_b_restore.add_argument("path", type=str, help="Filename or path to backup file")
    p_b_restore.set_defaults(func=cmd_backup_restore)

    # db
    p_db = subparsers.add_parser("db", help="Database maintenance commands")
    db_sub = p_db.add_subparsers(dest="db_cmd", help="DB subcommands")

    p_db_integ = db_sub.add_parser("integrity", help="Check SQLite integrity and FK validity")
    p_db_integ.set_defaults(func=cmd_db_integrity)

    p_db_vac = db_sub.add_parser("vacuum", help="Vacuum and optimize database")
    p_db_vac.set_defaults(func=cmd_db_vacuum)

    # data
    p_data = subparsers.add_parser("data", help="Data export and import")
    data_sub = p_data.add_subparsers(dest="data_cmd", help="Data subcommands")

    p_d_export = data_sub.add_parser("export", help="Export ledger into portable JSON")
    p_d_export.add_argument("--output", "-o", type=str, default="mymonee_ledger_export.json", help="Output filepath")
    p_d_export.set_defaults(func=cmd_data_export)

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
