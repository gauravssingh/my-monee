#!/usr/bin/env python3
"""Merge one category into another, repointing every reference first.

Built for the ``Food & Dining`` duplicate of ``Food`` (0 transactions, one duplicated
``groceries`` subcategory), which the AI classifier kept picking as a decoy. The merge is
refused unless every source subcategory has a twin (matched by slug) in the target, because
several referencing columns are NOT NULL.

Destructive, so it is a dry run unless ``--apply`` is passed. Take a snapshot first:

    sqlite3 "<db>" ".backup '<backups>/mymonee_backup_$(date +%Y%m%d_%H%M%S).db'"
    python scripts/merge_duplicate_category.py                     # dry run
    python scripts/merge_duplicate_category.py --apply

It writes only category/subcategory rows and the foreign keys that point at them; transactions,
amounts and classifications are untouched.
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import func, select, text, update

from mymonee.config import load_settings
from mymonee.db.models import (
    Budget,
    Category,
    ClassificationCorrection,
    ClassificationRule,
    IncomeSource,
    Merchant,
    Posting,
    RecurringTransaction,
    Subcategory,
    Transaction,
)
from mymonee.db.session import get_session_factory, init_db

CATEGORY_REFS = [
    ("transactions.category_id", Transaction, Transaction.category_id),
    ("classification_rules.category_id", ClassificationRule, ClassificationRule.category_id),
    ("merchants.default_category_id", Merchant, Merchant.default_category_id),
    ("postings.category_id", Posting, Posting.category_id),
    ("income_sources.category_id", IncomeSource, IncomeSource.category_id),
    (
        "recurring_transactions.category_id",
        RecurringTransaction,
        RecurringTransaction.category_id,
    ),
    ("budgets.category_id", Budget, Budget.category_id),
    (
        "corrections.previous_category_id",
        ClassificationCorrection,
        ClassificationCorrection.previous_category_id,
    ),
    (
        "corrections.new_category_id",
        ClassificationCorrection,
        ClassificationCorrection.new_category_id,
    ),
]

SUBCATEGORY_REFS = [
    ("transactions.subcategory_id", Transaction, Transaction.subcategory_id),
    (
        "classification_rules.subcategory_id",
        ClassificationRule,
        ClassificationRule.subcategory_id,
    ),
    (
        "merchants.default_subcategory_id",
        Merchant,
        Merchant.default_subcategory_id,
    ),
    (
        "corrections.previous_subcategory_id",
        ClassificationCorrection,
        ClassificationCorrection.previous_subcategory_id,
    ),
    (
        "corrections.new_subcategory_id",
        ClassificationCorrection,
        ClassificationCorrection.new_subcategory_id,
    ),
]


def _count(session, model, column, value) -> int:
    return int(session.scalar(select(func.count()).select_from(model).where(column == value)) or 0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="Food & Dining")
    parser.add_argument("--target", default="Food")
    parser.add_argument("--apply", action="store_true", help="Perform the merge (default: dry run)")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow merging even when the source category has transactions",
    )
    args = parser.parse_args()

    settings = load_settings()
    init_db(settings)

    with get_session_factory(settings)() as session:
        source = session.scalar(select(Category).where(Category.name == args.source))
        target = session.scalar(select(Category).where(Category.name == args.target))
        if source is None:
            print(f"source category not found: {args.source!r}")
            return 1
        if target is None:
            print(f"target category not found: {args.target!r}")
            return 1
        if source.id == target.id:
            print("source and target are the same category")
            return 1

        source_subs = list(
            session.scalars(select(Subcategory).where(Subcategory.category_id == source.id))
        )
        target_subs = {
            sub.slug: sub
            for sub in session.scalars(
                select(Subcategory).where(Subcategory.category_id == target.id)
            )
        }
        sub_map: dict[str, str | None] = {}
        for sub in source_subs:
            twin = target_subs.get(sub.slug)
            sub_map[sub.id] = twin.id if twin else None

        print(f"source: {source.name!r} ({source.id}) is_system={source.is_system}")
        print(f"target: {target.name!r} ({target.id})")
        print("subcategory mapping:")
        for sub in source_subs:
            twin_id = sub_map[sub.id]
            twin_name = next((t.name for t in target_subs.values() if t.id == twin_id), None)
            print(
                f"  {sub.name!r} ({sub.slug}) -> "
                + (f"{twin_name!r} ({twin_id})" if twin_id else "NO TWIN")
            )

        missing = [sub.name for sub in source_subs if sub_map[sub.id] is None]
        if missing:
            print(
                "\nrefusing to merge: these source subcategories have no slug twin in the "
                f"target and would leave dangling references: {missing}"
            )
            return 1

        in_use = _count(session, Transaction, Transaction.category_id, source.id)
        print(f"\ntransactions on the source category: {in_use}")
        if in_use and not args.force:
            print("refusing to merge a category that still has transactions (use --force)")
            return 1

        print("\nreferences to repoint:")
        total_refs = 0
        for label, model, column in CATEGORY_REFS:
            n = _count(session, model, column, source.id)
            total_refs += n
            print(f"  {label:48s} {n}")
        for sub in source_subs:
            for label, model, column in SUBCATEGORY_REFS:
                n = _count(session, model, column, sub.id)
                total_refs += n
                if n:
                    print(f"  {label:48s} {n}  (sub {sub.name!r})")
        print(f"  total: {total_refs}")

        if not args.apply:
            print("\nDRY RUN — nothing written. Re-run with --apply to perform the merge.")
            session.rollback()
            return 0

        # Snapshot existing violations: unrelated orphans must not be blamed on this merge.
        before_violations = {
            tuple(row) for row in session.execute(text("PRAGMA foreign_key_check")).fetchall()
        }
        if before_violations:
            print(f"\nwarning: {len(before_violations)} pre-existing foreign-key violation(s)")
            print("         (they existed before this merge and are reported, not fixed)")

        for label, model, column in CATEGORY_REFS:
            session.execute(
                update(model).where(column == source.id).values({column.key: target.id})
            )
        for old_sub, new_sub in sub_map.items():
            for label, model, column in SUBCATEGORY_REFS:
                session.execute(
                    update(model).where(column == old_sub).values({column.key: new_sub})
                )

        for sub in source_subs:
            session.delete(sub)
        session.delete(source)
        session.commit()

        remaining = _count(session, Category, Category.name, source.name)
        dangling = sum(
            _count(session, model, column, source.id) for _, model, column in CATEGORY_REFS
        )
        dangling += sum(
            _count(session, model, column, sub.id)
            for sub in source_subs
            for _, model, column in SUBCATEGORY_REFS
        )
        after_violations = {
            tuple(row) for row in session.execute(text("PRAGMA foreign_key_check")).fetchall()
        }
        introduced = after_violations - before_violations

        print(f"\nmerged {source.name!r} into {target.name!r}")
        print(f"  categories named {source.name!r} left: {remaining}")
        print(f"  dangling references: {dangling}")
        print(f"  new foreign_key_check violations: {len(introduced)}")
        if remaining or dangling or introduced:
            print("verification failed", file=sys.stderr)
            return 1
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
