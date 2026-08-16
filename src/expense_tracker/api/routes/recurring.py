from typing import Any
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from expense_tracker.api.deps import db_session
from expense_tracker.db.models import (
    RecurringTransaction,
    Subscription,
    Bill,
    TransactionRecurringLink,
    Transaction
)

class SubscriptionCreate(BaseModel):
    name: str
    amount: float
    billing_frequency: str = "monthly"
    expected_day: int | None = None
    date_tolerance_days: int | None = 4
    annual_cost: float | None = None
    merchant_id: str | None = None
    category_id: str | None = None
    transaction_id: str | None = None

class BillCreate(BaseModel):
    name: str
    expected_amount: float
    frequency: str = "monthly"
    bill_type: str = "OTHER"
    autopay: bool = False
    expected_day: int | None = None
    date_tolerance_days: int | None = 4
    merchant_id: str | None = None
    category_id: str | None = None
    transaction_id: str | None = None

class RecurringUpdate(BaseModel):
    name: str | None = None
    expected_amount: float | None = None
    frequency: str | None = None
    expected_day: int | None = None
    status: str | None = None

router = APIRouter(prefix="/api/recurring", tags=["recurring"])

@router.get("")
def list_recurring(session: Session = Depends(db_session)) -> dict[str, Any]:
    subscriptions = session.execute(
        select(Subscription, RecurringTransaction)
        .join(RecurringTransaction, Subscription.recurring_transaction_id == RecurringTransaction.id)
    ).all()
    
    bills = session.execute(
        select(Bill, RecurringTransaction)
        .join(RecurringTransaction, Bill.recurring_transaction_id == RecurringTransaction.id)
    ).all()
    
    sub_items = []
    for s, rt in subscriptions:
        sub_items.append({
            "id": s.id,
            "name": s.name,
            "amount": float(s.amount) if s.amount else 0.0,
            "billing_frequency": rt.frequency if rt.frequency else "monthly",
            "next_billing_date": rt.next_expected_date.isoformat() if rt.next_expected_date else None,
            "status": s.status,
            "annual_cost": float(s.annual_cost) if s.annual_cost else 0.0,
            "recurring_transaction_id": rt.id
        })
        
    bill_items = []
    for b, rt in bills:
        bill_items.append({
            "id": b.id,
            "name": b.name,
            "expected_amount": float(rt.expected_amount) if rt.expected_amount else 0.0,
            "due_date": rt.next_expected_date.isoformat() if rt.next_expected_date else None,
            "frequency": rt.frequency if rt.frequency else "monthly",
            "status": b.status,
            "recurring_transaction_id": rt.id
        })
        
    return {
        "subscriptions": sub_items,
        "bills": bill_items,
        "detected": []
    }

@router.get("/{id}")
def get_recurring(id: str, session: Session = Depends(db_session)):
    rt = session.get(RecurringTransaction, id)
    if not rt:
        raise HTTPException(status_code=404, detail="Recurring transaction not found")
    sub = session.scalars(select(Subscription).where(Subscription.recurring_transaction_id == id)).first()
    bill = session.scalars(select(Bill).where(Bill.recurring_transaction_id == id)).first()
    
    return {
        "id": rt.id,
        "name": rt.name,
        "expected_amount": float(rt.expected_amount) if rt.expected_amount else None,
        "frequency": rt.frequency,
        "status": rt.status,
        "type": "subscription" if sub else "bill" if bill else "unknown",
        "subscription": sub,
        "bill": bill
    }

@router.post("/detect")
def detect_recurring():
    return {"detected": []}

@router.post("/subscriptions")
def create_subscription(body: SubscriptionCreate, session: Session = Depends(db_session)):
    m_id = body.merchant_id.strip() if body.merchant_id and body.merchant_id.strip() else None
    c_id = body.category_id.strip() if body.category_id and body.category_id.strip() else None

    rt = RecurringTransaction(
        id=str(uuid.uuid4()),
        name=body.name,
        expected_amount=body.amount,
        frequency=body.billing_frequency,
        expected_day=body.expected_day,
        date_tolerance_days=body.date_tolerance_days,
        merchant_id=m_id,
        category_id=c_id,
        status="active",
    )
    session.add(rt)
    session.flush()

    sub = Subscription(
        id=str(uuid.uuid4()),
        recurring_transaction_id=rt.id,
        name=body.name,
        amount=body.amount,
        annual_cost=body.annual_cost,
        status="active",
    )
    session.add(sub)
    
    if body.transaction_id:
        tx = session.get(Transaction, body.transaction_id)
        if tx:
            link = TransactionRecurringLink(
                id=str(uuid.uuid4()),
                transaction_id=body.transaction_id,
                recurring_transaction_id=rt.id,
                match_type="manual",
            )
            session.add(link)
        
    session.commit()
    return {"id": rt.id, "subscription_id": sub.id}

@router.post("/bills")
def create_bill(body: BillCreate, session: Session = Depends(db_session)):
    m_id = body.merchant_id.strip() if body.merchant_id and body.merchant_id.strip() else None
    c_id = body.category_id.strip() if body.category_id and body.category_id.strip() else None

    rt = RecurringTransaction(
        id=str(uuid.uuid4()),
        name=body.name,
        expected_amount=body.expected_amount,
        frequency=body.frequency,
        expected_day=body.expected_day,
        date_tolerance_days=body.date_tolerance_days,
        merchant_id=m_id,
        category_id=c_id,
        status="active",
    )
    session.add(rt)
    session.flush()

    bill = Bill(
        id=str(uuid.uuid4()),
        recurring_transaction_id=rt.id,
        name=body.name,
        bill_type=body.bill_type,
        autopay=body.autopay,
        status="active",
    )
    session.add(bill)
    
    if body.transaction_id:
        tx = session.get(Transaction, body.transaction_id)
        if tx:
            link = TransactionRecurringLink(
                id=str(uuid.uuid4()),
                transaction_id=body.transaction_id,
                recurring_transaction_id=rt.id,
                match_type="manual",
            )
            session.add(link)
        
    session.commit()
    return {"id": rt.id, "bill_id": bill.id}

@router.post("/{id}/confirm")
def confirm_recurring(id: str, session: Session = Depends(db_session)):
    rt = session.get(RecurringTransaction, id)
    if not rt:
        raise HTTPException(status_code=404)
    rt.status = "active"
    sub = session.scalars(select(Subscription).where(Subscription.recurring_transaction_id == id)).first()
    if sub:
        sub.status = "active"
    bill = session.scalars(select(Bill).where(Bill.recurring_transaction_id == id)).first()
    if bill:
        bill.status = "active"
    session.commit()
    return {"status": "ok"}

@router.post("/{id}/ignore")
def ignore_recurring(id: str, session: Session = Depends(db_session)):
    rt = session.get(RecurringTransaction, id)
    if not rt:
        raise HTTPException(status_code=404)
    rt.status = "ignored"
    sub = session.scalars(select(Subscription).where(Subscription.recurring_transaction_id == id)).first()
    if sub:
        sub.status = "ignored"
    bill = session.scalars(select(Bill).where(Bill.recurring_transaction_id == id)).first()
    if bill:
        bill.status = "ignored"
    session.commit()
    return {"status": "ok"}

@router.patch("/{id}")
def update_recurring(id: str, body: RecurringUpdate, session: Session = Depends(db_session)):
    rt = session.get(RecurringTransaction, id)
    if not rt:
        raise HTTPException(status_code=404)
    if body.name is not None:
        rt.name = body.name
    if body.expected_amount is not None:
        rt.expected_amount = body.expected_amount
    if body.frequency is not None:
        rt.frequency = body.frequency
    if body.expected_day is not None:
        rt.expected_day = body.expected_day
    if body.status is not None:
        rt.status = body.status
    session.commit()
    return {"status": "ok"}

@router.delete("/{id}")
def delete_recurring(id: str, session: Session = Depends(db_session)):
    rt = session.get(RecurringTransaction, id)
    if not rt:
        raise HTTPException(status_code=404)
    session.execute(TransactionRecurringLink.__table__.delete().where(TransactionRecurringLink.recurring_transaction_id == id))
    session.execute(Subscription.__table__.delete().where(Subscription.recurring_transaction_id == id))
    session.execute(Bill.__table__.delete().where(Bill.recurring_transaction_id == id))
    session.delete(rt)
    session.commit()
    return {"status": "ok"}

@router.get("/{id}/transactions")
def get_recurring_transactions(id: str, session: Session = Depends(db_session)):
    links = session.scalars(select(TransactionRecurringLink).where(TransactionRecurringLink.recurring_transaction_id == id)).all()
    tx_ids = [l.transaction_id for l in links]
    if not tx_ids:
        return {"items": []}
    transactions = session.scalars(select(Transaction).where(Transaction.id.in_(tx_ids))).all()
    return {"items": transactions}
