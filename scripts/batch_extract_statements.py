#!/usr/bin/env python3
"""Batch extract and validate statements from the local statement vault."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add src to sys.path
repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root / "src"))

from sqlalchemy import select
from sqlalchemy.orm import Session

from expense_tracker.config import get_settings
from expense_tracker.db.models import CreditCardStatement
from expense_tracker.db.session import get_session_factory, init_db
from expense_tracker.statements.reconciliation import reconcile_statement_in_db
from expense_tracker.statements.service import extract_and_validate_statement


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch statement extraction and validation.")
    parser.add_argument("--limit", type=int, default=200, help="Maximum statements to process (default: 200)")
    parser.add_argument("--issuer", type=str, default=None, help="Filter by issuer (e.g. AXIS, SCAPIA)")
    parser.add_argument("--account-id", type=str, default=None, help="Filter by account ID")
    parser.add_argument("--reconcile", action="store_true", default=True, help="Reconcile against ledger alerts")
    parser.add_argument("--no-reconcile", dest="reconcile", action="store_false")
    args = parser.parse_args()

    settings = get_settings()
    init_db(settings)
    session_factory = get_session_factory()

    with session_factory() as session:
        query = select(CreditCardStatement).where(
            CreditCardStatement.unlocked_file_path.isnot(None),
            CreditCardStatement.status.in_(["READY_FOR_EXTRACTION", "UNLOCKED", "VALIDATED", "REVIEW_REQUIRED"]),
        )
        if args.issuer:
            query = query.where(CreditCardStatement.issuer == args.issuer.upper())
        if args.account_id:
            query = query.where(CreditCardStatement.account_id == args.account_id)

        query = query.order_by(CreditCardStatement.statement_date.desc()).limit(args.limit)
        statements = session.scalars(query).all()

        total = len(statements)
        print(f"\n=======================================================")
        print(f"  MyMonee Statement Batch Extractor")
        print(f"  Found {total} ready statement(s) to process")
        print(f"=======================================================\n")

        if total == 0:
            print("No ready statements to extract.")
            return

        validated_count = 0
        review_count = 0
        failed_count = 0
        total_tx_count = 0

        for i, stmt in enumerate(statements, 1):
            print(f"[{i}/{total}] {stmt.issuer} | {stmt.original_filename} ... ", end="", flush=True)
            try:
                updated = extract_and_validate_statement(session, stmt)
                tx_count = len(updated.transactions)
                total_tx_count += tx_count

                if updated.validation_status == "VALIDATED":
                    validated_count += 1
                    status_str = "✓ VALIDATED"
                elif updated.validation_status == "REVIEW_REQUIRED":
                    review_count += 1
                    status_str = "⚠ REVIEW REQUIRED"
                else:
                    failed_count += 1
                    status_str = f"✕ {updated.status}"

                reconcile_info = ""
                if args.reconcile and tx_count > 0:
                    rec_res = reconcile_statement_in_db(session, updated.id)
                    reconcile_info = f" | {rec_res.get('matched', 0)} matched"

                print(f"{status_str} ({tx_count} txs{reconcile_info})")

            except Exception as exc:
                failed_count += 1
                print(f"✕ ERROR: {exc}")

        print(f"\n=======================================================")
        print(f"  Batch Extraction Summary")
        print(f"  Total Processed: {total}")
        print(f"  Validated:       {validated_count}")
        print(f"  Review Required: {review_count}")
        print(f"  Failed/Skipped:  {failed_count}")
        print(f"  Transactions:    {total_tx_count}")
        print(f"=======================================================\n")


if __name__ == "__main__":
    main()
