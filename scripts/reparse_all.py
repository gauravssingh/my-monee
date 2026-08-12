import sys
from expense_tracker.db.session import init_engine, get_session_factory
from expense_tracker.config import get_settings
from expense_tracker.ingestion.pipeline import run_ingestion_pipeline

def run():
    init_engine()
    settings = get_settings()
    Session = get_session_factory()
    with Session() as session:
        print("Running ingestion pipeline with force_reparse=True...")
        result = run_ingestion_pipeline(
            session,
            settings,
            max_messages=2000,
            force_reparse=True,
            ignore_watermark=True
        )
        session.commit()
        print(f"Result: {result.status.value}")
        print(f"Processed: {result.emails_processed}, Extracted: {result.transactions_extracted}")
        print(f"Skipped: {result.emails_skipped}, Duplicates: {result.transactions_duplicated}")

if __name__ == "__main__":
    run()
