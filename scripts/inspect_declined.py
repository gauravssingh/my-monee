import sys
from mymonee.db.session import init_engine, get_session_factory
from mymonee.db.models import Transaction, Email

def run():
    init_engine()
    Session = get_session_factory()
    with Session() as session:
        tx = session.query(Transaction).filter_by(id="721a3fbd-637f-47be-b1a3-46bf48e0093e").first()
        if tx:
            print("=== TRANSACTION ===")
            print(f"Amount: {tx.amount}")
            print(f"Type: {tx.transaction_type}")
            print(f"Merchant: {tx.merchant_raw}")
            print(f"Source Email ID: {tx.source_email_id}")
            
            if tx.source_email_id:
                email = session.query(Email).filter_by(id=tx.source_email_id).first()
                if email:
                    print("\n=== EMAIL ===")
                    print(f"Subject: {email.subject}")
                    print(f"Sender: {email.sender}")
                    
if __name__ == "__main__":
    run()
