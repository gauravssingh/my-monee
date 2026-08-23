from collections import defaultdict
from datetime import datetime, timedelta
import statistics

from sqlalchemy import select, delete

from mymonee.db.session import get_session_factory
from mymonee.db.models import Transaction, Merchant, Subscription, Bill

def detect_recurring():
    SessionLocal = get_session_factory()
    with SessionLocal() as session:
        # Clear existing
        session.execute(delete(Subscription))
        session.execute(delete(Bill))
        session.flush()

        txs = session.scalars(
            select(Transaction)
            .where(Transaction.merchant_entity_id.isnot(None))
            .where(Transaction.direction == "debit")
            .order_by(Transaction.transaction_date)
        ).all()
        
        # Group by merchant
        by_merchant = defaultdict(list)
        for tx in txs:
            if tx.transaction_date:
                by_merchant[tx.merchant_entity_id].append(tx)
                
        subs_created = 0
        bills_created = 0
                
        for merchant_id, merchant_txs in by_merchant.items():
            if len(merchant_txs) < 3:
                continue
                
            # Calculate days between txs
            dates = sorted([tx.transaction_date.date() if isinstance(tx.transaction_date, datetime) else tx.transaction_date for tx in merchant_txs])
            deltas = [(dates[i] - dates[i-1]).days for i in range(1, len(dates))]
            
            avg_delta = sum(deltas) / len(deltas)
            
            # Check if monthly (25 to 35 days) or yearly (350 to 380 days)
            frequency = None
            if 25 <= avg_delta <= 35:
                frequency = "monthly"
            elif 350 <= avg_delta <= 380:
                frequency = "yearly"
                
            if not frequency:
                continue
                
            # Calculate amount variance
            amounts = [float(tx.amount) for tx in merchant_txs if tx.amount]
            if not amounts:
                continue
                
            avg_amount = sum(amounts) / len(amounts)
            if len(amounts) > 1:
                variance = statistics.stdev(amounts) / avg_amount
            else:
                variance = 0.0
                
            # If variance < 0.1, it's a fixed Subscription
            # Else, it's a variable Bill
            
            merchant = session.get(Merchant, merchant_id)
            if not merchant:
                continue
                
            name = merchant.display_name
            last_date = dates[-1]
            next_date = last_date + timedelta(days=avg_delta)
            
            # Use last transaction's account as default
            account_id = merchant_txs[-1].account_id if hasattr(merchant_txs[-1], 'account_id') else None 
            # In our schema, transaction doesn't have account_id directly, it uses account/card string. But we linked events to accounts.
            
            if variance < 0.1:
                sub = Subscription(
                    merchant_id=merchant_id,
                    name=name,
                    amount=avg_amount,
                    billing_frequency=frequency,
                    next_billing_date=datetime.combine(next_date, datetime.min.time()),
                    annual_cost=avg_amount * 12 if frequency == "monthly" else avg_amount,
                    status="active"
                )
                session.add(sub)
                subs_created += 1
            else:
                bill = Bill(
                    merchant_id=merchant_id,
                    name=name,
                    expected_amount=avg_amount,
                    due_date=datetime.combine(next_date, datetime.min.time()),
                    frequency=frequency,
                    status="pending"
                )
                session.add(bill)
                bills_created += 1
                
        session.commit()
        print(f"Detected {subs_created} fixed subscriptions and {bills_created} variable bills.")

if __name__ == "__main__":
    detect_recurring()
