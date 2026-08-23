"""CLI: re-fetch Scapia card alerts and fix debit/merchant parsing."""

from __future__ import annotations

import argparse
import json
import logging
import sys

from mymonee.config import reload_settings
from mymonee.db.session import get_session_factory, init_db
from mymonee.ingestion.gmail.client import GmailApiSource
from mymonee.ingestion.gmail.oauth import is_connected
from mymonee.ingestion.pipeline import run_ingestion_pipeline, run_ingestion_result_dict
from mymonee.logging_setup import setup_logging
from mymonee.parsers.bootstrap import bootstrap_parsers


SCAPIA_QUERY = (
    'from:(scapiacards@federalbank.co.in OR scapia) '
    'subject:"Your transaction was successful" '
    "after:2026/01/01"
)


class _FixedIdSource:
    def __init__(self, inner: GmailApiSource, ids: list[str]) -> None:
        self._inner = inner
        self._ids = ids

    def list_message_ids(self, query: str, *, max_results: int) -> list[str]:  # noqa: ARG002
        return self._ids[:max_results]

    def get_message(self, message_id: str):
        return self._inner.get_message(message_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill Scapia card purchase classifications")
    parser.add_argument("--max-messages", type=int, default=500)
    parser.add_argument("--query", default=SCAPIA_QUERY)
    args = parser.parse_args(argv)

    settings = reload_settings()
    setup_logging(settings)
    log = logging.getLogger("mymonee.reclassify_scapia")

    if not is_connected(settings):
        print("Gmail is not connected. Run: python -m mymonee.connect_gmail", file=sys.stderr)
        return 1

    init_db(settings)
    bootstrap_parsers(force=True)

    gmail = GmailApiSource(settings)
    ids = gmail.list_message_ids(args.query, max_results=args.max_messages)
    log.info("Found %s Scapia messages", len(ids))
    if not ids:
        print(json.dumps({"status": "success", "emails_discovered": 0}))
        return 0

    session = get_session_factory()()
    try:
        result = run_ingestion_pipeline(
            session,
            settings,
            source=_FixedIdSource(gmail, ids),
            max_messages=args.max_messages,
            force_reparse=True,
            ignore_watermark=True,
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
