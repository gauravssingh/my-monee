"""Backfill merchant_raw and merchant_normalized on historical Axis Bank transactions."""

from __future__ import annotations

import argparse
import sys
from sqlalchemy import select
from sqlalchemy.orm import Session

from expense_tracker.db.session import get_session_factory
from expense_tracker.db.models import Email, Transaction, Merchant, MerchantAlias
from expense_tracker.merchants.normalize import normalize_merchant
from expense_tracker.parsers.axis import AxisBankParser
from expense_tracker.parsers.base import EmailContext


def resolve_merchant_entity_id(session: Session, raw: str | None, norm: str | None) -> str | None:
    if not raw and not norm:
        return None
    raw_val = raw or norm or "Unknown Merchant"
    norm_val = norm or raw_val.lower().replace(" ", "_").strip() or "unknown_merchant"

    # 1. Alias match
    if raw:
        alias = session.scalar(select(MerchantAlias).where(MerchantAlias.alias_raw == raw).limit(1))
        if alias:
            return alias.merchant_id

    # 2. Key match
    merchant = session.scalar(select(Merchant).where(Merchant.normalized_key == norm_val).limit(1))
    if merchant:
        return merchant.id

    # 3. Create
    display_name = raw_val.upper() if len(raw_val) < 4 else raw_val.title()
    merchant = Merchant(
        display_name=display_name,
        normalized_key=norm_val,
        canonical_name=None,
    )
    session.add(merchant)
    session.flush()

    if raw:
        try:
            alias = MerchantAlias(
                merchant_id=merchant.id,
                alias_raw=raw,
                alias_normalized=norm_val,
                source="ingestion",
            )
            session.add(alias)
            session.flush()
        except Exception:
            pass

    return merchant.id


def backfill_axis_merchants(*, dry_run: bool = True) -> None:
    SessionLocal = get_session_factory()
    parser = AxisBankParser()

    with SessionLocal() as session:
        stmt = select(Transaction).where(
            Transaction.source.ilike("%axis%"),
            Transaction.merchant_raw.is_(None),
        )
        txs = session.scalars(stmt).all()
        print(f"Found {len(txs)} Axis transactions without merchant_raw.")

        updated_count = 0
        for tx in txs:
            if not tx.source_email_id:
                continue
            email = session.get(Email, tx.source_email_id)
            if not email:
                continue

            ctx = EmailContext(
                message_id=email.id,
                thread_id=email.thread_id or "",
                sender=email.sender or "",
                subject=email.subject or "",
                received_at=email.received_at,
                body_text=email.body_text or "",
                body_html=email.body_html,
            )
            parsed_list = parser.parse(ctx)
            if not parsed_list or not parsed_list[0].merchant_raw:
                continue

            parsed = parsed_list[0]
            new_raw = parsed.merchant_raw
            new_norm = normalize_merchant(new_raw)
            new_entity_id = resolve_merchant_entity_id(session, new_raw, new_norm)

            if updated_count < 10:
                print(f"[{'DRY-RUN' if dry_run else 'APPLY'}] Tx {tx.id} ({tx.amount} {tx.currency}) -> raw: '{new_raw}', norm: '{new_norm}'")

            if not dry_run:
                tx.merchant_raw = new_raw
                tx.merchant_normalized = new_norm
                tx.merchant_entity_id = new_entity_id
                if parsed.card and not tx.card:
                    tx.card = parsed.card

            updated_count += 1

        if not dry_run:
            session.commit()
            print(f"Successfully backfilled {updated_count} Axis transactions.")
        else:
            print(f"[DRY-RUN] Would backfill {updated_count} Axis transactions. Pass --apply to persist changes.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill merchant_raw on Axis Bank transactions.")
    parser.add_argument("--apply", action="store_true", help="Apply changes to SQLite database.")
    args = parser.parse_args()
    backfill_axis_merchants(dry_run=not args.apply)
