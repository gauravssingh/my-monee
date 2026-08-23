from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from pydantic import BaseModel

from expense_tracker.api.deps import db_session
from expense_tracker.db.models import Account, Institution

router = APIRouter(prefix="/api/accounts", tags=["accounts"])

class AccountCreate(BaseModel):
    name: str
    account_type: str
    is_asset: bool
    is_liability: bool
    currency: str = "INR"
    account_number_masked: str | None = None
    card_last4: str | None = None
    upi_identifier_masked: str | None = None
    credit_limit: float | None = None
    opening_balance: float = 0.0

class AccountUpdate(AccountCreate):
    pass

@router.get("")
def list_accounts(session: Session = Depends(db_session)) -> dict[str, Any]:
    from expense_tracker.services.ledger import calculate_ledger_balances
    
    summary = calculate_ledger_balances(session)
    accounts_by_id = {a.id: a for a in session.scalars(select(Account)).all()}

    items = []
    for proj in summary.accounts:
        acc = accounts_by_id.get(proj.account_id)
        if not acc:
            continue
        items.append({
            "id": acc.id,
            "name": acc.name,
            "account_type": acc.account_type,
            "is_asset": acc.is_asset,
            "is_liability": acc.is_liability,
            "balance": float(proj.current_balance),
            "raw_balance": float(proj.current_balance),
            "currency": acc.currency,
            "account_number_masked": acc.account_number_masked,
            "card_last4": acc.card_last4,
            "upi_identifier_masked": acc.upi_identifier_masked,
            "credit_limit": float(acc.credit_limit) if acc.credit_limit else None,
            "opening_balance": float(acc.opening_balance),
        })

    return {
        "net_worth": float(summary.net_worth),
        "assets": float(summary.total_assets),
        "liabilities": float(summary.total_liabilities),
        "accounts": items,
    }


@router.post("")
def create_account(
    body: AccountCreate,
    session: Session = Depends(db_session),
) -> dict[str, Any]:
    acc = Account(
        name=body.name,
        account_type=body.account_type,
        is_asset=body.is_asset,
        is_liability=body.is_liability,
        currency=body.currency,
        account_number_masked=body.account_number_masked,
        card_last4=body.card_last4,
        upi_identifier_masked=body.upi_identifier_masked,
        credit_limit=body.credit_limit,
        opening_balance=body.opening_balance,
        current_balance=body.opening_balance,
    )
    session.add(acc)
    session.commit()
    return {"id": acc.id}

@router.patch("/{account_id}")
def update_account(
    account_id: str,
    body: AccountUpdate,
    session: Session = Depends(db_session),
) -> dict[str, Any]:
    acc = session.get(Account, account_id)
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")
        
    acc.name = body.name
    acc.account_type = body.account_type
    acc.is_asset = body.is_asset
    acc.is_liability = body.is_liability
    acc.currency = body.currency
    acc.account_number_masked = body.account_number_masked
    acc.card_last4 = body.card_last4
    acc.upi_identifier_masked = body.upi_identifier_masked
    acc.credit_limit = body.credit_limit
    acc.opening_balance = body.opening_balance
    
    session.commit()
    return {"id": acc.id}

@router.delete("/{account_id}")
def delete_account(
    account_id: str,
    session: Session = Depends(db_session),
) -> dict[str, Any]:
    acc = session.get(Account, account_id)
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")
    
    from sqlalchemy.exc import IntegrityError
    try:
        session.delete(acc)
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=400, 
            detail="Cannot delete this account because it has linked transactions or recurring bills. Please reassign or delete them first."
        )
    return {"deleted": True}
