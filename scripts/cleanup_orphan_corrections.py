#!/usr/bin/env python3
"""Delete classification_corrections rows whose transaction no longer exists.

These are audit rows left behind by transactions that were deleted outside the ORM (the
foreign key would otherwise have blocked the delete). They cannot be resolved to anything,
they are not part of the ledger, and they make ``PRAGMA foreign_key_check`` — and therefore
``mymonee db integrity`` — report a failure.

Dry run by default; ``--apply`` deletes. Take a snapshot first.
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import delete, func, select, text

from mymonee.config import load_settings
from mymonee.db.models import ClassificationCorrection, Transaction
from mymonee.db.session import get_session_factory, init_db


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Delete the rows (default: dry run)")
    parser.add_argument("--show", type=int, default=5, help="Sample rows to print")
    args = parser.parse_args()

    settings = load_settings()
    init_db(settings)

    with get_session_factory(settings)() as session:
        orphan_predicate = ClassificationCorrection.transaction_id.notin_(select(Transaction.id))
        total = int(
            session.scalar(
                select(func.count()).select_from(ClassificationCorrection).where(orphan_predicate)
            )
            or 0
        )
        sample = session.execute(
            select(
                ClassificationCorrection.id,
                ClassificationCorrection.transaction_id,
                ClassificationCorrection.new_category_id,
            )
            .where(orphan_predicate)
            .limit(args.show)
        ).all()

        before = session.execute(text("PRAGMA foreign_key_check")).fetchall()
        print(f"orphaned classification_corrections: {total}")
        print(f"foreign_key_check violations before: {len(before)}")
        for row in sample:
            print(f"  id={row[0]} transaction_id={row[1]} new_category_id={row[2]}")

        if not args.apply:
            print("\nDRY RUN — nothing deleted. Re-run with --apply.")
            session.rollback()
            return 0
        if total == 0:
            print("nothing to delete")
            return 0

        session.execute(delete(ClassificationCorrection).where(orphan_predicate))
        session.commit()

        remaining = int(
            session.scalar(
                select(func.count()).select_from(ClassificationCorrection).where(orphan_predicate)
            )
            or 0
        )
        after = session.execute(text("PRAGMA foreign_key_check")).fetchall()
        rows_left = int(
            session.scalar(select(func.count()).select_from(ClassificationCorrection)) or 0
        )
        print(f"\ndeleted {total - remaining} row(s); {rows_left} corrections remain")
        print(f"foreign_key_check violations after: {len(after)}")
        if remaining or after:
            print("verification failed", file=sys.stderr)
            return 1
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
