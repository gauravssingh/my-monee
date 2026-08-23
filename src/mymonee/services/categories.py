"""Category hierarchy management."""

from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from mymonee.db.models import Category, Subcategory, Transaction, new_id


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def list_categories(session: Session) -> list[dict[str, Any]]:
    categories = session.execute(
        select(Category).options(selectinload(Category.subcategories)).order_by(Category.sort_order)
    ).scalars().all()

    result: list[dict[str, Any]] = []
    for cat in categories:
        tx_count = session.scalar(
            select(func.count()).select_from(Transaction).where(Transaction.category_id == cat.id)
        ) or 0
        subs = sorted(cat.subcategories, key=lambda s: s.sort_order)
        result.append(
            {
                "id": cat.id,
                "name": cat.name,
                "slug": cat.slug,
                "sort_order": cat.sort_order,
                "is_system": cat.is_system,
                "expense_type": cat.expense_type,
                "transaction_count": int(tx_count),
                "subcategories": [
                    {
                        "id": sub.id,
                        "name": sub.name,
                        "slug": sub.slug,
                        "sort_order": sub.sort_order,
                    }
                    for sub in subs
                ],
            }
        )
    return result


def create_category(session: Session, *, name: str) -> dict[str, Any]:
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Category name is required")
    slug = _slugify(name)
    existing = session.scalar(select(Category).where(Category.slug == slug))
    if existing:
        raise HTTPException(status_code=409, detail="Category already exists")
    max_order = session.scalar(select(func.max(Category.sort_order))) or 0
    cat = Category(
        id=new_id(),
        name=name,
        slug=slug,
        sort_order=int(max_order) + 1,
        is_system=False,
        expense_type="discretionary",
    )
    session.add(cat)
    session.flush()
    return {
        "id": cat.id,
        "name": cat.name,
        "slug": cat.slug,
        "sort_order": cat.sort_order,
        "is_system": cat.is_system,
        "expense_type": cat.expense_type,
        "transaction_count": 0,
        "subcategories": [],
    }


def rename_category(session: Session, category_id: str, *, name: str) -> dict[str, Any]:
    cat = session.get(Category, category_id)
    if cat is None:
        raise HTTPException(status_code=404, detail="Category not found")
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Category name is required")
    cat.name = name
    cat.slug = _slugify(name)
    session.flush()
    return next(c for c in list_categories(session) if c["id"] == category_id)

def set_category_expense_type(session: Session, category_id: str, *, expense_type: str) -> dict[str, Any]:
    cat = session.get(Category, category_id)
    if cat is None:
        raise HTTPException(status_code=404, detail="Category not found")
    if expense_type not in ["essential", "discretionary", "financial", "investment", "transfer"]:
        raise HTTPException(status_code=400, detail="Invalid expense type")
    cat.expense_type = expense_type
    session.flush()
    return next(c for c in list_categories(session) if c["id"] == category_id)


def delete_category(session: Session, category_id: str) -> dict[str, Any]:
    cat = session.get(Category, category_id)
    if cat is None:
        raise HTTPException(status_code=404, detail="Category not found")
    if cat.is_system:
        raise HTTPException(status_code=400, detail="System categories cannot be deleted")
    in_use = session.scalar(
        select(func.count()).select_from(Transaction).where(Transaction.category_id == category_id)
    ) or 0
    if in_use:
        raise HTTPException(
            status_code=400,
            detail=f"Category is used by {in_use} transactions; reassign them first",
        )
    for sub in list(cat.subcategories):
        session.delete(sub)
    session.delete(cat)
    return {"deleted": True, "id": category_id}


def create_subcategory(session: Session, category_id: str, *, name: str) -> dict[str, Any]:
    cat = session.get(Category, category_id)
    if cat is None:
        raise HTTPException(status_code=404, detail="Category not found")
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Subcategory name is required")
    slug = _slugify(name)
    existing = session.scalar(
        select(Subcategory).where(
            Subcategory.category_id == category_id,
            Subcategory.slug == slug,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="Subcategory already exists")
    max_order = session.scalar(
        select(func.max(Subcategory.sort_order)).where(Subcategory.category_id == category_id)
    ) or 0
    sub = Subcategory(
        id=new_id(),
        category_id=category_id,
        name=name,
        slug=slug,
        sort_order=int(max_order) + 1,
    )
    session.add(sub)
    session.flush()
    return {
        "id": sub.id,
        "name": sub.name,
        "slug": sub.slug,
        "sort_order": sub.sort_order,
        "category_id": category_id,
    }


def delete_subcategory(session: Session, subcategory_id: str) -> dict[str, Any]:
    sub = session.get(Subcategory, subcategory_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="Subcategory not found")
    in_use = session.scalar(
        select(func.count())
        .select_from(Transaction)
        .where(Transaction.subcategory_id == subcategory_id)
    ) or 0
    if in_use:
        raise HTTPException(
            status_code=400,
            detail=f"Subcategory is used by {in_use} transactions; reassign them first",
        )
    session.delete(sub)
    return {"deleted": True, "id": subcategory_id}
