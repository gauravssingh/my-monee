import sys
from expense_tracker.db.session import init_engine, get_session_factory
from expense_tracker.db.models import Email
from expense_tracker.parsers.registry import registry
from expense_tracker.parsers.bootstrap import bootstrap_parsers
from expense_tracker.parsers.base import EmailContext

def run():
    init_engine()
    Session = get_session_factory()
    with Session() as session:
        email = session.query(Email).filter(Email.id == "2703e719-031b-4cc7-b47d-4a057e6da0ce").first()
        if not email:
            print("Email not found in DB")
            return
        
        ctx = EmailContext(
            message_id=email.message_id,
            subject=email.subject,
            sender=email.sender,
            received_at=email.received_at,
            body_text=email.body_text,
            body_html=email.body_html
        )
        bootstrap_parsers()
        plugin, score = registry.choose(ctx)
        if plugin:
            print(f"Chosen parser: {plugin.name} (score {score})")
            parsed_list = plugin.parse(ctx)
            for p in parsed_list:
                print("Extracted Amount:", p.amount)
                print("Extracted Merchant:", p.merchant_raw)
                print("Payment Method:", p.payment_method)
                print("Transaction Type:", p.transaction_type)
        else:
            print("No parser matched.")

if __name__ == "__main__":
    run()
