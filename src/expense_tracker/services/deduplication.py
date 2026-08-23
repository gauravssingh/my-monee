"""Fuzzy deduplication engine for cross-provider transaction pairs."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from expense_tracker.db.models import (
    Account,
    Transaction,
    TransactionLink,
    new_id,
    utcnow,
)
from expense_tracker.merchants.normalize import normalize_merchant

logger = logging.getLogger(__name__)


def compute_string_similarity(str1: str | None, str2: str | None) -> float:
    """Compute token overlap similarity between two strings."""
    if not str1 or not str2:
        return 0.0
    tokens1 = set(re.findall(r"\w+", str1.lower()))
    tokens2 = set(re.findall(r"\w+", str2.lower()))
    if not tokens1 or not tokens2:
        return 0.0
    intersection = tokens1.intersection(tokens2)
    union = tokens1.union(tokens2)
    return len(intersection) / len(union) if union else 0.0


@dataclass
class DuplicateCandidate:
    primary_id: str
    duplicate_id: str
    confidence: float
    reason: str
    amount: float
    currency: str
    primary_merchant: str | None
    duplicate_merchant: str | None
    primary_date: str
    duplicate_date: str
    primary_source: str
    duplicate_source: str
    time_diff_seconds: int


def find_duplicate_candidates(
    session: Session,
    lookback_days: int = 90,
) -> list[DuplicateCandidate]:
    """Scan ledger for near-duplicate cross-provider transaction pairs."""
    since_date = utcnow() - timedelta(days=lookback_days)

    txs = session.scalars(
        select(Transaction)
        .where(
            Transaction.transaction_date >= since_date,
            Transaction.is_duplicate.is_(False),
            Transaction.is_transfer.is_(False),
        )
        .order_by(Transaction.transaction_date.desc())
    ).all()

    candidates: list[DuplicateCandidate] = []
    seen_pairs: set[tuple[str, str]] = set()

    for i, t1 in enumerate(txs):
        for t2 in txs[i + 1 :]:
            # Same direction only (debit/debit or credit/credit)
            if t1.direction != t2.direction:
                continue

            time_diff = abs((t1.transaction_date - t2.transaction_date).total_seconds())
            # Limit candidate search to within 48 hours (mostly within a few minutes)
            if time_diff > 48 * 3600:
                break

            pair_key = (min(t1.id, t2.id), max(t1.id, t2.id))
            if pair_key in seen_pairs:
                continue

            amt1 = float(t1.amount)
            amt2 = float(t2.amount)
            amount_diff = abs(amt1 - amt2)

            # Amounts must be within ₹1.00 (usually identical)
            if amount_diff > 1.00:
                continue

            score = 0.0
            reasons = []

            # 1. Exact reference / UPI RRN match
            rrn1 = (t1.reference_number or t1.bank_reference or "").strip()
            rrn2 = (t2.reference_number or t2.bank_reference or "").strip()
            if rrn1 and rrn2 and len(rrn1) >= 6 and (rrn1 in rrn2 or rrn2 in rrn1):
                score += 0.50
                reasons.append(f"Matching reference '{rrn1}'")

            # 2. Time proximity
            if time_diff <= 120:  # within 2 minutes (typical SMS + App notification delay)
                score += 0.40
                reasons.append(f"Occurred within {int(time_diff)} seconds of each other")
            elif time_diff <= 3600:  # within 1 hour
                score += 0.25
                reasons.append(f"Occurred within {int(time_diff // 60)} minutes")
            elif time_diff <= 86400:  # within 24 hours
                score += 0.10

            # 3. Exact or normalized merchant similarity
            m1 = (t1.merchant_normalized or t1.merchant_raw or "").lower()
            m2 = (t2.merchant_normalized or t2.merchant_raw or "").lower()
            sim = compute_string_similarity(m1, m2)
            if sim >= 0.8:
                score += 0.35
                reasons.append(f"High merchant name similarity ({int(sim * 100)}%)")
            elif sim >= 0.4:
                score += 0.20
                reasons.append(f"Partial merchant name match ({int(sim * 100)}%)")

            # 4. Cross-provider bonus (e.g. PhonePe vs Bank alert for same event)
            if t1.source != t2.source:
                score += 0.15
                reasons.append(f"Cross-provider alert: {t1.source} vs {t2.source}")

            # 5. Exact amount match
            if amount_diff == 0:
                score += 0.10

            final_confidence = min(1.0, score)

            # Threshold for candidate duplicates
            if final_confidence >= 0.65:
                seen_pairs.add(pair_key)
                # Pick the more detailed transaction as primary
                t1_details = len(t1.description or "") + len(t1.merchant_raw or "")
                t2_details = len(t2.description or "") + len(t2.merchant_raw or "")
                primary, duplicate = (t1, t2) if t1_details >= t2_details else (t2, t1)

                candidates.append(
                    DuplicateCandidate(
                        primary_id=primary.id,
                        duplicate_id=duplicate.id,
                        confidence=round(final_confidence, 2),
                        reason=" · ".join(reasons),
                        amount=amt1,
                        currency=t1.currency,
                        primary_merchant=primary.merchant_normalized or primary.merchant_raw,
                        duplicate_merchant=duplicate.merchant_normalized or duplicate.merchant_raw,
                        primary_date=primary.transaction_date.isoformat(),
                        duplicate_date=duplicate.transaction_date.isoformat(),
                        primary_source=primary.source,
                        duplicate_source=duplicate.source,
                        time_diff_seconds=int(time_diff),
                    )
                )

    return sorted(candidates, key=lambda c: c.confidence, reverse=True)


def merge_duplicate_transactions(
    session: Session,
    primary_id: str,
    duplicate_id: str,
) -> dict[str, Any]:
    """Link and exclude duplicate transaction from spending."""
    primary = session.get(Transaction, primary_id)
    duplicate = session.get(Transaction, duplicate_id)

    if not primary or not duplicate:
        raise ValueError("One or both transaction records not found.")

    duplicate.is_duplicate = True
    duplicate.parent_transaction_id = primary.id
    duplicate.excludes_from_spending = True

    # Record provenance link
    existing_link = session.scalars(
        select(TransactionLink).where(
            TransactionLink.from_transaction_id == primary.id,
            TransactionLink.to_transaction_id == duplicate.id,
            TransactionLink.kind == "duplicate",
        )
    ).first()

    if not existing_link:
        link = TransactionLink(
            from_transaction_id=primary.id,
            to_transaction_id=duplicate.id,
            kind="duplicate",
            confidence=1.0,
            notes=f"Merged duplicate of {primary.id}",
        )
        session.add(link)

    session.commit()
    return {
        "success": True,
        "primary_id": primary.id,
        "duplicate_id": duplicate.id,
    }


def unmark_duplicate_transaction(
    session: Session,
    tx_id: str,
) -> dict[str, Any]:
    """Revert duplicate marking on a transaction."""
    tx = session.get(Transaction, tx_id)
    if not tx:
        raise ValueError("Transaction not found.")

    tx.is_duplicate = False
    tx.parent_transaction_id = None
    tx.excludes_from_spending = False

    links = session.scalars(
        select(TransactionLink).where(
            (TransactionLink.from_transaction_id == tx_id)
            | (TransactionLink.to_transaction_id == tx_id),
            TransactionLink.kind == "duplicate",
        )
    ).all()
    for l in links:
        session.delete(l)

    session.commit()
    return {"success": True, "transaction_id": tx.id}
