"""Deterministic classification rule engine and user preference persistence."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from expense_tracker.db.models import (
    Category,
    ClassificationRule,
    Subcategory,
    Transaction,
    utcnow,
)

logger = logging.getLogger(__name__)


def find_matching_rule(
    session: Session,
    tx: Transaction,
) -> ClassificationRule | None:
    """Find the highest-priority active ClassificationRule matching a transaction.

    Match Precedence:
    1. Direct merchant_entity_id match (priority desc, created_at desc)
    2. Normalized merchant string match (priority desc, created_at desc)
    3. UPI ID match (priority desc, created_at desc)
    """
    # 1. Match by merchant entity ID
    if tx.merchant_entity_id:
        rule = session.scalars(
            select(ClassificationRule)
            .where(
                ClassificationRule.is_active == True,
                ClassificationRule.merchant_entity_id == tx.merchant_entity_id,
            )
            .order_by(ClassificationRule.priority.desc(), ClassificationRule.created_at.desc())
        ).first()
        if rule:
            return rule

    # 2. Match by normalized merchant name
    merchant_name = (tx.merchant_normalized or tx.merchant_raw or "").strip().lower()
    if merchant_name:
        rules = session.scalars(
            select(ClassificationRule)
            .where(
                ClassificationRule.is_active == True,
                ClassificationRule.merchant_normalized.is_not(None),
            )
            .order_by(ClassificationRule.priority.desc(), ClassificationRule.created_at.desc())
        ).all()

        for rule in rules:
            if rule.merchant_normalized and rule.merchant_normalized.strip().lower() == merchant_name:
                return rule

    # 3. Match by UPI ID
    if tx.upi_id:
        upi_clean = tx.upi_id.strip().lower()
        rule = session.scalars(
            select(ClassificationRule)
            .where(
                ClassificationRule.is_active == True,
                ClassificationRule.upi_id.is_not(None),
            )
            .order_by(ClassificationRule.priority.desc(), ClassificationRule.created_at.desc())
        ).first()
        if rule and rule.upi_id and rule.upi_id.strip().lower() == upi_clean:
            return rule

    return None


def upsert_user_classification_rule(
    session: Session,
    tx: Transaction,
    category_id: str,
    subcategory_id: str | None = None,
) -> ClassificationRule:
    """Create or update a high-priority user classification rule from a manual categorization."""
    merchant_name = (tx.merchant_normalized or tx.merchant_raw or "").strip()
    category = session.get(Category, category_id)
    cat_name = category.name if category else "Category"

    # Check for existing rule for this merchant entity or merchant name
    existing_rule: ClassificationRule | None = None
    if tx.merchant_entity_id:
        existing_rule = session.scalars(
            select(ClassificationRule).where(
                ClassificationRule.merchant_entity_id == tx.merchant_entity_id
            )
        ).first()

    if not existing_rule and merchant_name:
        existing_rule = session.scalars(
            select(ClassificationRule).where(
                ClassificationRule.merchant_normalized.ilike(merchant_name)
            )
        ).first()

    if existing_rule:
        existing_rule.category_id = category_id
        existing_rule.subcategory_id = subcategory_id
        existing_rule.priority = 100
        existing_rule.source = "user"
        existing_rule.is_active = True
        existing_rule.name = f"{merchant_name or 'Merchant'} -> {cat_name}"
        existing_rule.updated_at = utcnow()
        logger.info("Updated existing user classification rule %s for %s", existing_rule.id, merchant_name)
        return existing_rule

    rule = ClassificationRule(
        name=f"{merchant_name or 'Merchant'} -> {cat_name}",
        priority=100,
        is_active=True,
        merchant_entity_id=tx.merchant_entity_id,
        merchant_normalized=merchant_name if merchant_name else None,
        upi_id=tx.upi_id if (not merchant_name and tx.upi_id) else None,
        category_id=category_id,
        subcategory_id=subcategory_id,
        source="user",
        hit_count=1,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    session.add(rule)
    session.flush()
    logger.info("Created new user classification rule %s for %s -> %s", rule.id, merchant_name, cat_name)
    return rule


def apply_classification_rule_to_transaction(
    session: Session,
    tx: Transaction,
    rule: ClassificationRule,
) -> None:
    """Apply a matched ClassificationRule onto a transaction."""
    tx.category_id = rule.category_id
    tx.subcategory_id = rule.subcategory_id
    tx.classification_source = rule.source
    tx.classification_confidence = 1.0 if rule.source == "user" else 0.90
    
    category = session.get(Category, rule.category_id)
    subcategory = session.get(Subcategory, rule.subcategory_id) if rule.subcategory_id else None

    tx.classification_signals = {
        "rule": "user_rule" if rule.source == "user" else "classification_rule",
        "rule_id": rule.id,
        "rule_name": rule.name,
        "priority": rule.priority,
        "category_slug": category.slug if category else None,
        "subcategory_slug": subcategory.slug if subcategory else None,
    }

    if rule.source == "user":
        tx.needs_review = False
        tx.user_verified = True

    rule.hit_count = (rule.hit_count or 0) + 1
    rule.updated_at = utcnow()
    tx.updated_at = utcnow()
