"""CLI: sync Gmail into the local database."""

from __future__ import annotations

import argparse
import json
import logging
import sys

from mymonee.config import reload_settings
from mymonee.db.session import get_session_factory, init_db
from mymonee.ingestion.gmail.oauth import is_connected
from mymonee.ingestion.pipeline import run_ingestion_pipeline, run_ingestion_result_dict
from mymonee.logging_setup import setup_logging
from mymonee.parsers.bootstrap import bootstrap_parsers


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync Gmail transactions")
    parser.add_argument("--after", default=None, help="Gmail after:YYYY/MM/DD")
    parser.add_argument("--full-year", action="store_true", help="Ignore watermark; use sync_after_date")
    parser.add_argument("--max-messages", type=int, default=None)
    parser.add_argument("--force-reparse", action="store_true")
    args = parser.parse_args(argv)

    settings = reload_settings()
    setup_logging(settings)
    log = logging.getLogger("mymonee.sync_gmail")

    if not is_connected(settings):
        print("Gmail is not connected. Run: python -m mymonee.connect_gmail", file=sys.stderr)
        return 1

    init_db(settings)
    bootstrap_parsers()
    after = args.after
    ignore = False
    if args.full_year:
        after = after or settings.gmail.sync_after_date or "2026/01/01"
        ignore = True

    log.info("Starting sync after=%s max=%s", after, args.max_messages)
    session = get_session_factory()()
    try:
        result = run_ingestion_pipeline(
            session,
            settings,
            max_messages=args.max_messages,
            force_reparse=args.force_reparse,
            after_date=after,
            ignore_watermark=ignore or bool(after),
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    print(json.dumps(run_ingestion_result_dict(result), indent=2))
    return 0 if result.status in {"success", "partial"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
