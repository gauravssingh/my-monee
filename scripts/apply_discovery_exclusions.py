#!/usr/bin/env python3
"""Retroactively apply discovery exclusion rules to existing emails and transactions in SQLite."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from pathlib import Path

import yaml

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("apply_discovery_exclusions")


def get_db_path() -> Path:
    # Try local config or standard default path
    default_path = Path.home() / "Library" / "Application Support" / "ExpenseTracker" / "mymonee.db"
    return default_path


def load_exclusion_rules(config_path: Path) -> tuple[list[re.Pattern], list[re.Pattern]]:
    if not config_path.exists():
        logger.error("Configuration file not found at %s", config_path)
        sys.exit(1)
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    sender_pats = [re.compile(p, re.IGNORECASE) for p in data.get("exclude_sender_patterns", [])]
    subject_pats = [re.compile(p, re.IGNORECASE) for p in data.get("exclude_subject_patterns", [])]
    return sender_pats, subject_pats


def apply_exclusions(db_path: Path, config_path: Path, *, dry_run: bool = False) -> None:
    import sqlite3

    if not db_path.exists():
        logger.error("Database not found at %s", db_path)
        sys.exit(1)

    sender_pats, subject_pats = load_exclusion_rules(config_path)
    logger.info("Loaded %d sender exclusion rules and %d subject exclusion rules", len(sender_pats), len(subject_pats))

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # 1. Scan and update emails table
    cur.execute("SELECT id, sender, subject, parse_status FROM emails")
    email_rows = cur.fetchall()

    matching_email_ids: list[tuple[str, str]] = []
    for eid, sender, subject, status in email_rows:
        sender_str = sender or ""
        subject_str = subject or ""
        matched_rule = None

        for pat in sender_pats:
            if pat.search(sender_str):
                matched_rule = f"exclude_sender:{pat.pattern}"
                break
        if not matched_rule:
            for pat in subject_pats:
                if pat.search(subject_str):
                    matched_rule = f"exclude_subject:{pat.pattern}"
                    break

        if matched_rule:
            matching_email_ids.append((eid, matched_rule))

    logger.info("Found %d matching emails out of %d total emails", len(matching_email_ids), len(email_rows))

    if not dry_run and matching_email_ids:
        for eid, rule in matching_email_ids:
            cur.execute(
                """
                UPDATE emails
                SET parse_status = 'SKIPPED',
                    parse_error = ?
                WHERE id = ?
                """,
                (f"discovery_exclusion:{rule}", eid),
            )
        conn.commit()
        logger.info("Updated %d emails to parse_status='SKIPPED'", len(matching_email_ids))

    # 2. Scan and update transactions table
    cur.execute(
        """
        SELECT t.id, t.transaction_type, t.excludes_from_spending, e.sender, e.subject, t.description, t.merchant_raw
        FROM transactions t
        LEFT JOIN emails e ON t.source_email_id = e.id
        """
    )
    tx_rows = cur.fetchall()

    matching_tx_ids: list[tuple[str, str]] = []
    for tid, tx_type, excluded, sender, subject, desc, merch in tx_rows:
        sender_str = sender or ""
        subject_str = subject or desc or ""
        matched_rule = None

        for pat in sender_pats:
            if pat.search(sender_str):
                matched_rule = f"exclude_sender:{pat.pattern}"
                break
        if not matched_rule:
            for pat in subject_pats:
                if pat.search(subject_str):
                    matched_rule = f"exclude_subject:{pat.pattern}"
                    break

        if matched_rule:
            matching_tx_ids.append((tid, matched_rule))

    logger.info("Found %d matching transactions out of %d total transactions", len(matching_tx_ids), len(tx_rows))

    if not dry_run and matching_tx_ids:
        for tid, rule in matching_tx_ids:
            signals = json.dumps({"rule": "discovery_exclusion", "matched": rule})
            cur.execute(
                """
                UPDATE transactions
                SET transaction_type = 'not_a_transaction',
                    excludes_from_spending = 1,
                    needs_review = 0,
                    category_id = NULL,
                    subcategory_id = NULL,
                    classification_source = 'rule',
                    classification_signals = json(?)
                WHERE id = ?
                """,
                (signals, tid),
            )
        conn.commit()
        logger.info("Updated %d transactions to not_a_transaction / excluded", len(matching_tx_ids))

    conn.close()
    logger.info("Finished applying discovery exclusion rules.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Retroactively apply discovery exclusions to SQLite ledger")
    parser.add_argument("--dry-run", action="store_true", help="Inspect matches without making changes")
    parser.add_argument("--config", type=Path, default=Path("config/providers/discovery.yaml"), help="Path to discovery.yaml")
    parser.add_argument("--db", type=Path, default=None, help="Custom path to SQLite database")
    args = parser.parse_args()

    db_path = args.db or get_db_path()
    apply_exclusions(db_path, args.config, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
