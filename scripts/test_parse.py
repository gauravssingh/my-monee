import sys
from mymonee.db.session import init_engine, get_session_factory
from mymonee.config import get_settings
from mymonee.ingestion.gmail.client import GmailApiSource
from mymonee.ingestion.pipeline import _to_email_context
from mymonee.parsers.registry import registry
from mymonee.parsers.bootstrap import bootstrap_parsers
import re
from mymonee.parsers.extract import AMOUNT_PATTERNS

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
