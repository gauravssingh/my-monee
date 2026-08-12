import sys
from expense_tracker.db.session import init_engine, get_session_factory
from expense_tracker.config import get_settings
from expense_tracker.ingestion.gmail.client import GmailApiSource
from expense_tracker.ingestion.pipeline import _to_email_context
from expense_tracker.parsers.registry import registry
from expense_tracker.parsers.bootstrap import bootstrap_parsers
import re
from expense_tracker.parsers.extract import AMOUNT_PATTERNS

def run():
    init_engine()
    settings = get_settings()
    source = GmailApiSource(settings)
    msg = source.get_message("19ff57281dec333d")
    if not msg:
        print("Message not found on Gmail.")
        return
        
    ctx = _to_email_context(msg)
    print("Subject:", ctx.subject)
    
    # Check regex directly against subject
    for pattern in AMOUNT_PATTERNS:
        match = pattern.search(ctx.subject)
        if match:
            print("Regex Matched:", match.group(1))
    
    bootstrap_parsers()
    plugin, score = registry.choose(ctx)
    if plugin:
        print(f"Chosen parser: {plugin.name} (score {score})")
        parsed_list = plugin.parse(ctx)
        for p in parsed_list:
            print("Extracted Amount:", p.amount)
            print("Extracted Merchant:", p.merchant_raw)
    else:
        print("No parser matched.")

if __name__ == "__main__":
    run()
