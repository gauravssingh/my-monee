import sys
from mymonee.db.session import init_engine, get_session_factory
from mymonee.db.models import Email, Transaction

def run():
    init_engine()
    Session = get_session_factory()
    with Session() as session:
        # Check if the ID is a transaction ID
        tx = session.query(Transaction).filter_by(id="a1349e38-4220-4593-a6e9-61cc351f2f54").first()
        if tx:
            print("=== TRANSACTION FOUND ===")
            print(f"Amount: {tx.amount}")
            print(f"Merchant: {tx.merchant_raw}")
            print(f"Type: {tx.transaction_type}")
            print(f"Source Email ID: {tx.source_email_id}")
            
            if tx.source_email_id:
                email = session.query(Email).filter_by(id=tx.source_email_id).first()
                if email:
                    print("\n=== ASSOCIATED EMAIL ===")
                    print(f"Subject: {email.subject}")
                    print(f"Sender: {email.sender}")
                    print(f"Body Text:\n{email.body_text}")
        else:
            print("Transaction not found.")

if __name__ == "__main__":
    run()
