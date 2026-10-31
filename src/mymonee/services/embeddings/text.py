"""Canonical embeddable text for a transaction.

This is the single source of truth for what gets embedded. The content hash is taken over the
exact string this module produces, so changing the composition re-embeds affected rows instead of
silently mixing two text conventions in one index.

Deliberate choices:
- Timestamps are excluded. Semantic search over "late delivery"-style text gains almost nothing
  from a date string, and date filtering belongs in SQL, not in the vector space.
- Amount, direction, and currency are included so "large refund" / "salary credit" style queries
  can match, and so two identical merchants with different amounts stay distinguishable.
- Only non-empty parts are included, making the text deterministic for a given row.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal, InvalidOperation
from typing import Any

from mymonee.db.models import Transaction


def format_amount(amount: object) -> str:
    """Format a ledger amount as a plain two-decimal string (e.g. '249.00')."""
    try:
        value = Decimal(str(amount))
    except (InvalidOperation, TypeError):
        return str(amount)
    return f"{value.quantize(Decimal('0.01'))}"


_UNSET: Any = object()


def transaction_embedding_text(
    transaction: Transaction,
    *,
    category_name: Any = _UNSET,
    subcategory_name: Any = _UNSET,
) -> str:
    """Compose the canonical embeddable text for one transaction.

    Reads joined category/subcategory names, so callers should eager-load those relationships to
    avoid a query per row when batching.

    `category_name`/`subcategory_name` override the relationship lookup. Session-level flush hooks
    use them because a transaction whose `category_id` just changed may still hold a stale
    relationship object until the flush completes.
    """
    merchant = (transaction.merchant_normalized or transaction.merchant_raw or "").strip()

    parts: list[str] = [
        f"{transaction.direction} {transaction.currency} {format_amount(transaction.amount)}"
    ]
    if merchant:
        parts.append(f"merchant: {merchant}")
    description = (transaction.description or "").strip()
    if description:
        parts.append(f"description: {description}")
    if transaction.transaction_type:
        parts.append(f"type: {transaction.transaction_type}")

    if category_name is _UNSET:
        category_name = transaction.category.name if transaction.category is not None else None
    if category_name:
        parts.append(f"category: {category_name}")
    if subcategory_name is _UNSET:
        subcategory_name = (
            transaction.subcategory.name if transaction.subcategory is not None else None
        )
    if subcategory_name:
        parts.append(f"subcategory: {subcategory_name}")

    if transaction.account:
        parts.append(f"account: {transaction.account.strip()}")
    if transaction.payment_method:
        parts.append(f"method: {transaction.payment_method.strip()}")
    if transaction.location:
        parts.append(f"location: {transaction.location.strip()}")

    return " | ".join(parts)


def transaction_content_hash(text: str) -> str:
    """SHA-256 of the exact text that was embedded (detects changed content)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
