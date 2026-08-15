from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from expense_tracker.api.deps import db_session
from expense_tracker.db.models import Merchant, MerchantAlias, Transaction, utcnow

router = APIRouter(prefix="/api/merchants", tags=["merchants"])

class MergeRequest(BaseModel):
    merchant_ids: list[str]
    canonical_name: str

@router.get("")
def list_merchants(session: Session = Depends(db_session)) -> dict[str, Any]:
    merchants = session.scalars(select(Merchant).order_by(Merchant.display_name)).all()
    
    items = []
    for m in merchants:
        aliases = [a.alias_raw for a in m.aliases]
        items.append({
            "id": m.id,
            "display_name": m.display_name,
            "canonical_name": m.canonical_name,
            "normalized_key": m.normalized_key,
            "aliases": aliases,
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
