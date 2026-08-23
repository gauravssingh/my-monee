import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from mymonee.db.models import Category, Subcategory, Transaction
from mymonee.parsers.base import ParsedTransaction

logger = logging.getLogger(__name__)


def resolve_category_ids(
    session: Session,
    *,
    category_slug: str | None,
    subcategory_slug: str | None,
) -> tuple[str | None, str | None]:
    if not category_slug:
        return None, None
    category = session.scalar(select(Category).where(Category.slug == category_slug))
    if category is None:
        return None, None
    subcategory_id = None
    if subcategory_slug:
        sub = session.scalar(
            select(Subcategory).where(
                Subcategory.category_id == category.id,
                Subcategory.slug == subcategory_slug,
            )
        )
        subcategory_id = sub.id if sub else None
    return category.id, subcategory_id


def apply_parsed_enrichment(
    session: Session,
    tx: Transaction,
    parsed: ParsedTransaction,
) -> None:
    from mymonee.classification.rules import (
        apply_classification_rule_to_transaction,
        find_matching_rule,
    )

    # 1. First priority: Check active user and persistent classification rules
    matched_rule = find_matching_rule(session, tx)
    if matched_rule:
        apply_classification_rule_to_transaction(session, tx, matched_rule)
        logger.info(
            "Enriched tx %s using persistent rule %s (%s)",
            tx.id,
            matched_rule.id,
            matched_rule.name,
        )
    else:
        # 2. Fallback to parser-provided category hints
        extra: dict[str, Any] = dict(parsed.extra or {})
        cat_id, sub_id = resolve_category_ids(
            session,
            category_slug=extra.get("category_slug"),
            subcategory_slug=extra.get("subcategory_slug"),
        )
        if cat_id:
            tx.category_id = cat_id
            tx.subcategory_id = sub_id
        if "classification_source" in extra:
            tx.classification_source = str(extra["classification_source"])
        if "classification_confidence" in extra:
            tx.classification_confidence = float(extra["classification_confidence"])
        if "classification_signals" in extra and isinstance(extra["classification_signals"], dict):
            tx.classification_signals = extra["classification_signals"]
        if "needs_review" in extra:
            tx.needs_review = bool(extra["needs_review"])

    extra: dict[str, Any] = dict(parsed.extra or {})
    if "is_transfer" in extra:
        tx.is_transfer = bool(extra["is_transfer"])
    if "is_refund" in extra:
        tx.is_refund = bool(extra["is_refund"])
    if "excludes_from_spending" in extra:
        tx.excludes_from_spending = bool(extra["excludes_from_spending"])

    # Keep income and transfers out of spending totals
    if (
        parsed.transaction_type in {"income", "transfer"}
        or tx.is_transfer
        or (parsed.direction == "credit" and tx.is_transfer)
    ):
        tx.excludes_from_spending = True
        if parsed.transaction_type == "transfer":
            tx.is_transfer = True
