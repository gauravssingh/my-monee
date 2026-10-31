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
    print(
        f"  Last Backup     {st['last_backup'] or 'None'} ({'Verified ✓' if st['last_backup_verified'] else 'Unverified'})"
    )


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


def cmd_embeddings_status(args: argparse.Namespace) -> None:
    settings = load_settings()
    init_db(settings)
    from mymonee.db.session import get_session_factory
    from mymonee.services.embeddings import embedding_status

    with get_session_factory()() as session:
        status = embedding_status(session, settings=settings)

    print("Embedding status\n")
    print(f"  Enabled         {'✓ Yes' if status['enabled'] else '○ No'} ({status['base_url']})")
    service = status["service"]
    if service is None:
        print("  Service         ○ Not queried (embeddings disabled)")
    elif not service.get("reachable"):
        print(f"  Service         ✗ Unreachable — {service['error']}")
    elif not service.get("compatible"):
        print(f"  Service         ✗ Incompatible contract — {service['error']}")
    else:
        print(f"  Service         ✓ {service['model_id']}")
        print(f"  Model Revision  {service['model_revision']}")
        print(f"  Device          {service['device']} / {service['precision']}")
        print(f"  Dimensions      {service['dimensions']}")
    print(f"  Stored Vectors  {status['stored_vectors']:,}")
    print(f"  Indexable Rows  {status['indexable_transactions']:,}")
    if status["current_revision_vectors"] is not None:
        print(f"  Current Rev     {status['current_revision_vectors']:,}")
    if status["stale_vectors"] is not None:
        print(f"  Stale Vectors   {status['stale_vectors']:,}")
    if status["stored_by_revision"]:
        revisions = ", ".join(
            f"{rev}: {count:,}" for rev, count in status["stored_by_revision"].items()
        )
        print(f"  By Revision     {revisions}")
    jobs = status["jobs"]
    if jobs:
        summary = ", ".join(f"{name}: {count:,}" for name, count in sorted(jobs.items()))
        print(f"  Jobs            {summary}")
    else:
        print("  Jobs            none")
    if status["needs_reindex"]:
        print(
            "\n  ⚠ Some transactions have no vector for the live model revision — run: mymonee embeddings index"
        )


def cmd_embeddings_index(args: argparse.Namespace) -> None:
    settings = load_settings()
    init_db(settings)
    from mymonee.db.session import get_session_factory
    from mymonee.services.embeddings import (
        EmbeddingContractError,
        EmbeddingsDisabled,
        EmbeddingServiceUnavailable,
        index_transactions,
    )

    try:
        with get_session_factory()() as session:
            result = index_transactions(
                session, limit=args.limit, force=args.force, settings=settings
            )
    except EmbeddingsDisabled as exc:
        print(f"✗ {exc}")
        raise SystemExit(1) from exc
    except EmbeddingServiceUnavailable as exc:
        print(f"✗ Embedding service unavailable: {exc}")
        raise SystemExit(1) from exc
    except EmbeddingContractError as exc:
        print(f"✗ Embedding service contract violated: {exc}")
        raise SystemExit(1) from exc

    enqueue = result["enqueue"]
    process = result["process"]
    contract = result["contract"]
    print(f"Model           {contract.model_id} ({contract.model_revision})")
    print("✓ Enqueue:")
    print(f"  • Candidates: {enqueue['candidates']:,}")
    print(f"  • Enqueued:   {enqueue['enqueued']:,}")
    print(f"  • Refreshed:  {enqueue['refreshed']:,}")
    print(f"  • Skipped:    {enqueue['skipped']:,}")
    print("✓ Process:")
    print(f"  • Claimed:    {process['claimed']:,}")
    print(f"  • Embedded:   {process['embedded']:,}")
    print(f"  • Skipped:    {process['skipped']:,}")
    print(f"  • Retried:    {process['retried']:,}")
    print(f"  • Failed:     {process['failed']:,}")
    print(f"  • Dropped:    {process['dropped']:,}")


def cmd_embeddings_process(args: argparse.Namespace) -> None:
    settings = load_settings()
    init_db(settings)
    from mymonee.db.session import get_session_factory
    from mymonee.services.embeddings import (
        EmbeddingContractError,
        EmbeddingsDisabled,
        EmbeddingServiceUnavailable,
        process_embedding_jobs,
    )

    try:
        with get_session_factory()() as session:
            process = process_embedding_jobs(session, limit=args.limit, settings=settings)
    except EmbeddingsDisabled as exc:
        print(f"✗ {exc}")
        raise SystemExit(1) from exc
    except EmbeddingServiceUnavailable as exc:
        print(f"✗ Embedding service unavailable: {exc}")
        raise SystemExit(1) from exc
    except EmbeddingContractError as exc:
        print(f"✗ Embedding service contract violated: {exc}")
        raise SystemExit(1) from exc

    if not process["claimed"]:
        print("○ No due embedding jobs.")
        return
    print("✓ Processed embedding jobs:")
    print(f"  • Claimed:  {process['claimed']:,}")
    print(f"  • Embedded: {process['embedded']:,}")
    print(f"  • Skipped:  {process['skipped']:,}")
    print(f"  • Retried:  {process['retried']:,}")
    print(f"  • Failed:   {process['failed']:,}")
    print(f"  • Dropped:  {process['dropped']:,}")


def cmd_embeddings_search(args: argparse.Namespace) -> None:
    settings = load_settings()
    init_db(settings)
    from mymonee.db.session import get_session_factory
    from mymonee.services.embeddings import (
        EmbeddingContractError,
        EmbeddingsDisabled,
        EmbeddingServiceUnavailable,
        search_transactions_semantic,
    )

    try:
        with get_session_factory()() as session:
            results = search_transactions_semantic(
                session, args.query, limit=args.limit, settings=settings
            )
    except EmbeddingsDisabled as exc:
        print(f"✗ {exc}")
        raise SystemExit(1) from exc
    except EmbeddingServiceUnavailable as exc:
        print(f"✗ Embedding service unavailable: {exc}")
        raise SystemExit(1) from exc
    except EmbeddingContractError as exc:
        print(f"✗ Embedding service contract violated: {exc}")
        raise SystemExit(1) from exc

    if not results:
        print("○ No stored vectors match the live model revision — run: mymonee embeddings index")
        return

    print(f"Semantic results for {args.query!r} ({len(results)} of top matches):\n")
    for rank, item in enumerate(results, start=1):
        tx = item["transaction"]
        date = (tx.get("transaction_date") or "")[:10]
        merchant = tx.get("merchant_normalized") or tx.get("merchant_raw") or "Unknown Merchant"
        print(
            f"  {rank:>2}. {item['score']:.4f}  {date}  {tx.get('direction')} "
            f"{tx.get('currency')} {tx.get('amount')}  {merchant}"
        )
        if tx.get("description"):
            print(f"      {tx['description'][:100]}")


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


def cmd_mcp(args: argparse.Namespace) -> None:
    from mymonee.mcp.server import run_mcp_stdio

    run_mcp_stdio()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="mymonee", description="MyMonee Local-First Expense Ledger CLI"
    )
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
    p_b_create.add_argument(
        "--snapshot-only", action="store_true", help="Create .db snapshot instead of .mmb archive"
    )
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
    p_d_export.add_argument(
        "--output", "-o", type=str, default="mymonee_ledger_export.json", help="Output filepath"
    )
    p_d_export.set_defaults(func=cmd_data_export)

    # embeddings
    p_emb = subparsers.add_parser(
        "embeddings", help="Semantic indexing and search via the local embedding-g2 service"
    )
    emb_sub = p_emb.add_subparsers(dest="embeddings_cmd", help="Embedding subcommands")

    p_e_status = emb_sub.add_parser("status", help="Indexing coverage and service compatibility")
    p_e_status.set_defaults(func=cmd_embeddings_status)

    p_e_index = emb_sub.add_parser("index", help="Enqueue and embed missing transaction vectors")
    p_e_index.add_argument("--limit", type=int, default=None, help="Max transactions to consider")
    p_e_index.add_argument(
        "--force", action="store_true", help="Re-embed even when the content hash is unchanged"
    )
    p_e_index.set_defaults(func=cmd_embeddings_index)

    p_e_process = emb_sub.add_parser("process", help="Process due embedding jobs (durable queue)")
    p_e_process.add_argument("--limit", type=int, default=200, help="Max jobs to process")
    p_e_process.set_defaults(func=cmd_embeddings_process)

    p_e_search = emb_sub.add_parser(
        "search", help="Semantic search over stored transaction vectors"
    )
    p_e_search.add_argument("query", type=str, help="Natural-language search query")
    p_e_search.add_argument("--limit", type=int, default=10, help="Max results")
    p_e_search.set_defaults(func=cmd_embeddings_search)

    # mcp
    p_mcp = subparsers.add_parser(
        "mcp", help="Start the MyMonee FastMCP server (stdio transport for Hermes Agent)"
    )
    p_mcp.set_defaults(func=cmd_mcp)

    # agent
    p_agent = subparsers.add_parser(
        "agent", help="Agent service CLI adapter for testing and scripts"
    )
    agent_sub = p_agent.add_subparsers(dest="agent_cmd", help="Agent subcommands")
    from mymonee.cli.agent_adapter import setup_agent_subparsers

    setup_agent_subparsers(agent_sub)

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
