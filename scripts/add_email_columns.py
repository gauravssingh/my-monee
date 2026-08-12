import sys
from sqlalchemy import text
from expense_tracker.db.session import init_engine, get_session_factory
from expense_tracker.config import get_settings

def run():
    init_engine()
    settings = get_settings()
    Session = get_session_factory()
    with Session() as session:
        try:
            session.execute(text("ALTER TABLE emails ADD COLUMN body_text TEXT;"))
            session.execute(text("ALTER TABLE emails ADD COLUMN body_html TEXT;"))
            session.commit()
            print("Columns added successfully.")
        except Exception as e:
            print("Error adding columns (they might already exist):", e)
            session.rollback()

if __name__ == "__main__":
    run()
