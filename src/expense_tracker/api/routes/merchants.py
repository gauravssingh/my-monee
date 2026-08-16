from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import case, func, select, update
from sqlalchemy.orm import Session

from expense_tracker.api.deps import db_session
from expense_tracker.db.models import Category, Merchant, MerchantAlias, Transaction, utcnow

router = APIRouter(prefix="/api/merchants", tags=["merchants"])

class MergeRequest(BaseModel):
    merchant_ids: list[str]
    canonical_name: str

@router.get("")
def list_merchants(session: Session = Depends(db_session)) -> dict[str, Any]:
    from datetime import datetime, timedelta, timezone

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)

    # Collect aliases by merchant
    aliases_by_merchant: dict[str, list[str]] = {}
    for a in session.scalars(select(MerchantAlias)).all():
        aliases_by_merchant.setdefault(a.merchant_id, []).append(a.alias_raw)

    valid_tx = (
        (Transaction.direction == "debit")
        & (Transaction.excludes_from_spending.is_(False))
        & (Transaction.is_duplicate.is_(False))
        & (Transaction.is_transfer.is_(False))
        & (Transaction.transaction_type.notin_(["not_a_transaction", "declined", "transfer"]))
    )

    stmt = (
        select(
            Merchant.id,
            Merchant.display_name,
            Merchant.canonical_name,
            Merchant.normalized_key,
            Merchant.category_hint,
            Category.name.label("default_category_name"),
            func.coalesce(
                func.sum(
                    case(
                        (valid_tx, Transaction.amount),
                        else_=0,
                    )
                ),
                0,
            ).label("total_spent"),
            func.coalesce(
                func.sum(
                    case(
                        (valid_tx & (Transaction.transaction_date >= cutoff), Transaction.amount),
                        else_=0,
                    )
                ),
                0,
            ).label("spent_last_30d"),
            func.count(
                case(
                    (valid_tx, Transaction.id),
                    else_=None,
                )
            ).label("tx_count"),
        )
        .outerjoin(Category, Category.id == Merchant.default_category_id)
        .outerjoin(Transaction, Transaction.merchant_entity_id == Merchant.id)
        .group_by(Merchant.id, Category.name)
        .having(
            func.sum(
                case(
                    (valid_tx, Transaction.amount),
                    else_=0,
                )
            ) > 0
        )
        .order_by(
            func.sum(
                case(
                    (valid_tx, Transaction.amount),
                    else_=0,
                )
            ).desc(),
            Merchant.display_name.asc(),
        )
    )

    rows = session.execute(stmt).all()

    items = []
    for r in rows:
        items.append({
            "id": r.id,
            "display_name": r.display_name,
            "canonical_name": r.canonical_name,
            "normalized_key": r.normalized_key,
            "default_category": r.default_category_name or r.category_hint or None,
            "aliases": aliases_by_merchant.get(r.id, []),
            "total_spent": float(r.total_spent or 0.0),
            "spent_last_30d": float(r.spent_last_30d or 0.0),
            "transaction_count": int(r.tx_count or 0),
        })
    return {"items": items}

@router.post("/merge")
def merge_merchants(req: MergeRequest, session: Session = Depends(db_session)) -> dict[str, Any]:
    if not req.merchant_ids:
        raise HTTPException(status_code=400, detail="No merchants selected for merge.")
        
    # Get all the selected merchants
    merchants = session.scalars(
        select(Merchant).where(Merchant.id.in_(req.merchant_ids))
    ).all()
    
    if not merchants:
        raise HTTPException(status_code=404, detail="Merchants not found.")
        
    # Check if a merchant with the canonical name already exists (or use the first one)
    normalized_canonical = req.canonical_name.lower().replace(" ", "_")
    target_merchant = session.scalar(
        select(Merchant).where(Merchant.normalized_key == normalized_canonical)
    )
    
    if not target_merchant:
        # We will transform the first selected merchant into the canonical one
        target_merchant = merchants[0]
        target_merchant.display_name = req.canonical_name
        target_merchant.canonical_name = req.canonical_name
        target_merchant.normalized_key = normalized_canonical
        target_merchant.updated_at = utcnow()
        merchants_to_merge = merchants[1:]
    else:
        # All selected merchants will be merged into the existing target
        target_merchant.display_name = req.canonical_name
        target_merchant.canonical_name = req.canonical_name
        target_merchant.updated_at = utcnow()
        merchants_to_merge = [m for m in merchants if m.id != target_merchant.id]
        
    # Perform the merge
    for old_m in merchants_to_merge:
        # Move aliases to the target merchant
        for alias in list(old_m.aliases):
            old_m.aliases.remove(alias)
            target_merchant.aliases.append(alias)

        # Update transactions that pointed to the old merchant
        session.execute(
            update(Transaction)
            .where(Transaction.merchant_entity_id == old_m.id)
            .values(merchant_entity_id=target_merchant.id)
        )
        
        # Delete the old merchant
        session.delete(old_m)
        
    session.commit()
    
    return {"status": "success", "canonical_id": target_merchant.id}
