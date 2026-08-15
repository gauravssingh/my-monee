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
    accounts = session.scalars(select(Account).order_by(Account.name)).all()
    
    # Calculate net worth
    assets = sum(a.current_balance for a in accounts if a.is_asset)
    liabilities = sum(a.current_balance for a in accounts if a.is_liability)
    net_worth = assets - liabilities

    # Calculate actual balances from Postings
    # For now, since we migrated existing txs to Postings, let's just query Postings
    # to sum up the balances dynamically if needed, but our migration set default balance 0.
    # Actually, we should calculate current balance dynamically from postings!
    from expense_tracker.db.models import Posting
    postings_summary = session.execute(
        select(
            Posting.account_id, 
            Posting.direction,
            func.sum(Posting.amount)
        ).group_by(Posting.account_id, Posting.direction)
    ).all()

    balances = {}
    for acc_id, direction, amount in postings_summary:
        if acc_id not in balances:
            balances[acc_id] = 0.0
        # If it's a debit and account is asset -> asset increase? No, in banking debit usually means money out, but in double entry debit is +Asset.
        # Let's look at migration script:
        # "asset_decrease" if direction == "debit" else "asset_increase"
        # debit (spent) = asset decrease. credit (income) = asset increase.
        if direction == "debit":
            balances[acc_id] -= float(amount)
        else:
            balances[acc_id] += float(amount)

    items = []
    total_assets = 0.0
    total_liabilities = 0.0

    for a in accounts:
        bal = balances.get(a.id, 0.0)
        a.current_balance = bal
        
        if a.is_asset:
            total_assets += bal
        if a.is_liability:
            # Liability balance: a positive balance means we owe money.
            # When we spend on credit card (debit), liability increases. 
            # In our migration, debit = asset_decrease... wait.
            # If it's a credit card (is_liability), a "debit" transaction means we spent money, so our liability increases.
            # In migration script: "asset_decrease" if direction == "debit".
            # If it's a liability, the logic is technically liability_increase. 
            # To keep it simple, if bal < 0 on a liability, it means we owe that much (it decreased our net worth).
            total_liabilities += abs(bal)

        items.append({
            "id": a.id,
            "name": a.name,
            "account_type": a.account_type,
            "is_asset": a.is_asset,
            "is_liability": a.is_liability,
            "balance": abs(bal),
            "raw_balance": bal,
            "currency": a.currency,
            "account_number_masked": a.account_number_masked,
            "card_last4": a.card_last4,
            "upi_identifier_masked": a.upi_identifier_masked,
            "credit_limit": float(a.credit_limit) if a.credit_limit else None,
            "opening_balance": float(a.opening_balance),
        })
        
    net_worth = total_assets - total_liabilities

    return {
        "net_worth": net_worth,
        "assets": total_assets,
        "liabilities": total_liabilities,
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
