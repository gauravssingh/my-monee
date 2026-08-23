"""Category hierarchy API for Settings."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from mymonee.api.deps import db_session
from mymonee.services import categories as category_service

router = APIRouter(prefix="/api/categories", tags=["categories"])


class NameBody(BaseModel):
    name: str = Field(min_length=1, max_length=100)

class ExpenseTypeBody(BaseModel):
    expense_type: str = Field(min_length=1, max_length=32)

@router.get("")
def get_categories(session: Session = Depends(db_session)) -> dict[str, Any]:
    return {"items": category_service.list_categories(session)}


@router.post("")
def post_category(body: NameBody, session: Session = Depends(db_session)) -> dict[str, Any]:
    return category_service.create_category(session, name=body.name)


@router.patch("/{category_id}")
def patch_category(
    category_id: str,
    body: NameBody,
    session: Session = Depends(db_session),
) -> dict[str, Any]:
    return category_service.rename_category(session, category_id, name=body.name)


@router.patch("/{category_id}/expense_type")
def patch_category_expense_type(
    category_id: str,
    body: ExpenseTypeBody,
    session: Session = Depends(db_session),
) -> dict[str, Any]:
    return category_service.set_category_expense_type(session, category_id, expense_type=body.expense_type)


@router.delete("/{category_id}")
def remove_category(category_id: str, session: Session = Depends(db_session)) -> dict[str, Any]:
    return category_service.delete_category(session, category_id)


@router.post("/{category_id}/subcategories")
def post_subcategory(
    category_id: str,
    body: NameBody,
    session: Session = Depends(db_session),
) -> dict[str, Any]:
    return category_service.create_subcategory(session, category_id, name=body.name)


@router.delete("/subcategories/{subcategory_id}")
def remove_subcategory(
    subcategory_id: str,
    session: Session = Depends(db_session),
) -> dict[str, Any]:
    return category_service.delete_subcategory(session, subcategory_id)
