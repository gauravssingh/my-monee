from expense_tracker.db.session import get_session_factory
from expense_tracker.db.models import Transaction, Merchant, MerchantAlias
from sqlalchemy import select

def migrate():
    SessionLocal = get_session_factory()
    with SessionLocal() as session:
        transactions = session.scalars(select(Transaction).where(Transaction.merchant_entity_id.is_(None))).all()
        
        merchants_cache = {}
        
        count = 0
        for tx in transactions:
            raw = tx.merchant_raw or "Unknown Merchant"
            norm = tx.merchant_normalized or raw.lower().replace(" ", "_").strip()
            if not norm:
                norm = "unknown_merchant"
                
            if norm not in merchants_cache:
                merchant = session.scalar(select(Merchant).where(Merchant.normalized_key == norm))
                if not merchant:
                    merchant = Merchant(
                        display_name=raw.upper() if len(raw) < 4 else raw.title(),
                        normalized_key=norm,
                        canonical_name=None, # Leave canonical null until user merges
                    )
                    session.add(merchant)
                    session.flush()
                    
                    try:
                        alias = MerchantAlias(
                            merchant_id=merchant.id,
                            alias_raw=raw,
                            alias_normalized=norm,
                            source="migration"
                        )
                        session.add(alias)
                        session.flush()
                    except Exception:
                        session.rollback()
                        # If alias already exists somehow, just skip adding it
                        pass
                        
                merchants_cache[norm] = merchant
                
            tx.merchant_entity_id = merchants_cache[norm].id
            count += 1
            if count % 100 == 0:
                print(f"Processed {count} transactions...")
                session.commit()
                
        session.commit()
        print(f"Merchant migration complete. Processed {count} transactions.")

if __name__ == "__main__":
    migrate()
