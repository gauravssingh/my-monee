"""Classification Rules API for Settings."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from mymonee.api.deps import db_session
from mymonee.db.models import Category, ClassificationRule, Subcategory, utcnow

router = APIRouter(prefix="/api/rules", tags=["rules"])


class UpdateRuleBody(BaseModel):
    is_active: bool | None = None
    priority: int | None = Field(default=None, ge=0, le=1000)
    category_id: str | None = None
    subcategory_id: str | None = None


@router.get("")
def get_rules(session: Session = Depends(db_session)) -> dict[str, Any]:
    """List all classification rules ordered by priority and hit count."""
    rules = session.scalars(
        select(ClassificationRule).order_by(
            ClassificationRule.priority.desc(),
            ClassificationRule.hit_count.desc(),
            ClassificationRule.created_at.desc(),
        )
    ).all()

    # Pre-fetch categories and subcategories for mapping
    categories_map = {c.id: c.name for c in session.scalars(select(Category)).all()}
    subcategories_map = {s.id: s.name for s in session.scalars(select(Subcategory)).all()}

    items = [
        {
            "id": r.id,
            "name": r.name,
            "merchant_normalized": r.merchant_normalized,
            "merchant_entity_id": r.merchant_entity_id,
            "upi_id": r.upi_id,
            "category_id": r.category_id,
            "category_name": categories_map.get(r.category_id, "Unknown"),
            "subcategory_id": r.subcategory_id,
            "subcategory_name": subcategories_map.get(r.subcategory_id) if r.subcategory_id else None,
            "priority": r.priority,
            "is_active": r.is_active,
            "hit_count": r.hit_count,
            "source": r.source,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in rules
    ]
    return {"rules": items, "count": len(items)}


@router.patch("/{rule_id}")
def update_rule(
    rule_id: str,
    body: UpdateRuleBody,
    session: Session = Depends(db_session),
) -> dict[str, Any]:
    """Update active status, priority, or category assignment for a rule."""
    rule = session.get(ClassificationRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Classification rule not found")

    if body.is_active is not None:
        rule.is_active = body.is_active

    if body.priority is not None:
        rule.priority = body.priority

    if body.category_id is not None:
        cat = session.get(Category, body.category_id)
        if not cat:
            raise HTTPException(status_code=400, detail="Category not found")
        rule.category_id = body.category_id

        if body.subcategory_id is not None:
            if body.subcategory_id:
                sub = session.get(Subcategory, body.subcategory_id)
                if not sub or sub.category_id != cat.id:
                    raise HTTPException(status_code=400, detail="Subcategory does not belong to category")
                rule.subcategory_id = body.subcategory_id
            else:
                rule.subcategory_id = None

    rule.updated_at = utcnow()
    session.flush()
    return {"ok": True, "id": rule.id, "is_active": rule.is_active}


@router.delete("/{rule_id}")
def delete_rule(rule_id: str, session: Session = Depends(db_session)) -> dict[str, Any]:
    """Permanently delete a classification rule."""
    rule = session.get(ClassificationRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Classification rule not found")

    session.delete(rule)
    session.flush()
    return {"ok": True, "deleted_id": rule_id}
