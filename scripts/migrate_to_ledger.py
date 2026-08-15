from expense_tracker.db.session import init_db, get_session_factory, get_engine
from expense_tracker.db.models import (
    Transaction,
    Account,
    Institution,
    FinancialEvent,
    Posting,
    Category,
)
from sqlalchemy import text

def alter_existing_tables():
    engine = get_engine()
    with engine.begin() as conn:
        try:
            conn.execute(text("ALTER TABLE categories ADD COLUMN expense_type TEXT DEFAULT 'discretionary'"))
        except Exception as e:
            print("categories.expense_type may already exist:", e)

        try:
            conn.execute(text("ALTER TABLE merchants ADD COLUMN canonical_name TEXT"))
            conn.execute(text("ALTER TABLE merchants ADD COLUMN category_hint TEXT"))
            conn.execute(text("ALTER TABLE merchants ADD COLUMN merchant_type TEXT"))
        except Exception as e:
            print("merchants new columns may already exist:", e)

        try:
            conn.execute(text("ALTER TABLE transactions ADD COLUMN financial_event_id TEXT"))
        except Exception as e:
            print("transactions.financial_event_id may already exist:", e)


def migrate():
    print("Altering existing tables...")
    alter_existing_tables()

    print("Creating new tables...")
    init_db()
    
    SessionLocal = get_session_factory()
    with SessionLocal() as session:
        # Create a default institution
        inst = session.query(Institution).filter_by(name="Unknown Institution").first()
        if not inst:
            inst = Institution(name="Unknown Institution", institution_type="BANK")
            session.add(inst)
            session.commit()

        # Cache for accounts
        accounts_cache = {}

        def get_or_create_account(tx: Transaction) -> Account:
            # Determine account name from legacy fields
            if tx.account:
                name = f"{tx.account} Account"
                acc_type = "BANK"
                is_liability = False
            elif tx.card:
                name = f"Credit Card {tx.card}"
                acc_type = "CREDIT_CARD"
                is_liability = True
            elif tx.upi_id:
                name = f"UPI {tx.upi_id.split('@')[-1] if '@' in tx.upi_id else tx.upi_id}"
                acc_type = "BANK"
                is_liability = False
            elif tx.payment_method:
                name = f"{tx.payment_method} Account"
                acc_type = "BANK"
                is_liability = False
            else:
                name = "Default Cash Account"
                acc_type = "CASH"
                is_liability = False
                
            if name in accounts_cache:
                return accounts_cache[name]
                
            acc = session.query(Account).filter_by(name=name).first()
            if not acc:
                acc = Account(
                    name=name,
                    institution_id=inst.id,
                    account_type=acc_type,
                    is_asset=not is_liability,
                    is_liability=is_liability,
                )
                session.add(acc)
                session.commit()
                
            accounts_cache[name] = acc
            return acc
            
        print("Migrating transactions to financial events...")
        txs = session.query(Transaction).filter(Transaction.financial_event_id.is_(None)).all()
        
        count = 0
        for tx in txs:
            acc = get_or_create_account(tx)
            
            # Create Event
            event = FinancialEvent(
                event_type="purchase" if tx.direction == "debit" else "deposit",
                event_date=tx.transaction_date,
                source=tx.source,
                description=tx.description or tx.merchant_raw or "Migration",
            )
            session.add(event)
            session.flush() # get id
            
            # Create Postings
            # 1. Account Posting
            session.add(Posting(
                event_id=event.id,
                account_id=acc.id,
                amount=tx.amount,
                direction=tx.direction,
                posting_type="asset_decrease" if tx.direction == "debit" else "asset_increase"
            ))
            
            # 2. Category Posting (if categorized)
            if tx.category_id:
                session.add(Posting(
                    event_id=event.id,
                    category_id=tx.category_id,
                    amount=tx.amount,
                    direction="credit" if tx.direction == "debit" else "debit",
                    posting_type="expense" if tx.direction == "debit" else "income"
                ))
            
            # Link back to tx
            tx.financial_event_id = event.id
            
            count += 1
            if count % 100 == 0:
                print(f"Processed {count} transactions...")
                session.commit()
                
        session.commit()
        print(f"Migration complete. Processed {count} transactions.")

if __name__ == "__main__":
    migrate()
