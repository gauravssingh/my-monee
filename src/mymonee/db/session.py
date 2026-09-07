"""Database engine and session helpers."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from mymonee.config import Settings, get_settings
from mymonee.db.models import Base
from mymonee.db.seed import seed_defaults

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _sqlite_url(path: Path) -> str:
    return f"sqlite:///{path}"


def _configure_sqlite(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA cache_size=-64000")
        cursor.execute("PRAGMA mmap_size=268435456")
        cursor.execute("PRAGMA temp_store=MEMORY")
        cursor.close()


def init_engine(settings: Settings | None = None) -> Engine:
    global _engine, _SessionLocal
    if _engine is not None:
        try:
            _engine.dispose()
        except Exception:  # noqa: BLE001, S110
            pass
    settings = settings or get_settings()
    db_path = settings.database_path().resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(
        _sqlite_url(db_path),
        echo=settings.database.echo,
        future=True,
    )
    engine._mymonee_db_path = db_path
    _configure_sqlite(engine)
    _engine = engine
    _SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return engine


def get_engine(settings: Settings | None = None) -> Engine:
    if settings is not None:
        target_path = settings.database_path().resolve()
        if _engine is not None and getattr(_engine, "_mymonee_db_path", None) == target_path:
            return _engine
        return init_engine(settings)
    if _engine is None:
        return init_engine()
    return _engine


def get_session_factory(settings: Settings | None = None) -> sessionmaker[Session]:
    if settings is not None:
        target_path = settings.database_path().resolve()
        if (
            _engine is not None
            and _SessionLocal is not None
            and getattr(_engine, "_mymonee_db_path", None) == target_path
        ):
            return _SessionLocal
        init_engine(settings)
    elif _SessionLocal is None:
        init_engine()
    assert _SessionLocal is not None
    return _SessionLocal


def _migrate_columns(engine: Engine) -> None:
    """Safe additive migrations for SQLite columns."""
    with engine.begin() as conn:
        cursor = conn.exec_driver_sql("PRAGMA table_info(credit_card_statements)")
        cols = {row[1] for row in cursor.fetchall()}
        if cols:
            if "validation_status" not in cols:
                conn.exec_driver_sql(
                    "ALTER TABLE credit_card_statements ADD COLUMN validation_status VARCHAR(32) DEFAULT 'PENDING'"
                )
            if "validation_details_json" not in cols:
                conn.exec_driver_sql(
                    "ALTER TABLE credit_card_statements ADD COLUMN validation_details_json JSON"
                )
            if "parser_name" not in cols:
                conn.exec_driver_sql(
                    "ALTER TABLE credit_card_statements ADD COLUMN parser_name VARCHAR(64)"
                )
            if "parser_version" not in cols:
                conn.exec_driver_sql(
                    "ALTER TABLE credit_card_statements ADD COLUMN parser_version VARCHAR(32)"
                )
            if "page_count" not in cols:
                conn.exec_driver_sql(
                    "ALTER TABLE credit_card_statements ADD COLUMN page_count INTEGER"
                )


def _migrate_indexes(engine: Engine) -> None:
    """Additive migration ensuring critical performance and foreign key indexes exist."""
    indexes = [
        "CREATE INDEX IF NOT EXISTS ix_tx_category ON transactions (category_id);",
        "CREATE INDEX IF NOT EXISTS ix_tx_subcategory ON transactions (subcategory_id);",
        "CREATE INDEX IF NOT EXISTS ix_tx_merchant_entity ON transactions (merchant_entity_id);",
        "CREATE INDEX IF NOT EXISTS ix_tx_source_email ON transactions (source_email_id);",
        "CREATE INDEX IF NOT EXISTS ix_data_issue_tx_status ON data_issue_flags (transaction_id, status);",
        "CREATE INDEX IF NOT EXISTS ix_subcategories_slug ON subcategories (slug);",
        "CREATE INDEX IF NOT EXISTS ix_emails_received_at ON emails (received_at);",
        "CREATE INDEX IF NOT EXISTS ix_emails_parse_status ON emails (parse_status);",
        "CREATE INDEX IF NOT EXISTS ix_postings_event_id ON postings (event_id);",
        "CREATE INDEX IF NOT EXISTS ix_postings_acc_dir ON postings (account_id, direction);",
        "CREATE INDEX IF NOT EXISTS ix_merchant_aliases_merchant_id ON merchant_aliases (merchant_id);",
        "CREATE INDEX IF NOT EXISTS ix_subscriptions_recurring_tx_id ON subscriptions (recurring_transaction_id);",
        "CREATE INDEX IF NOT EXISTS ix_bills_recurring_tx_id ON bills (recurring_transaction_id);",
        "CREATE INDEX IF NOT EXISTS ix_tx_link_to ON transaction_links (to_transaction_id);",
        "CREATE INDEX IF NOT EXISTS ix_ingestion_events_run_id ON ingestion_events (run_id);",
        "CREATE INDEX IF NOT EXISTS ix_ingestion_runs_started_at ON ingestion_runs (started_at);",
        "CREATE INDEX IF NOT EXISTS ix_classification_rules_merchant_entity ON classification_rules (merchant_entity_id);",
        "CREATE INDEX IF NOT EXISTS ix_stmt_val_status ON credit_card_statements (validation_status);",
    ]
    with engine.begin() as conn:
        for idx_sql in indexes:
            conn.exec_driver_sql(idx_sql)


def init_db(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    engine = init_engine(settings)
    Base.metadata.create_all(bind=engine)
    _migrate_columns(engine)
    _migrate_indexes(engine)
    with Session(engine) as session:
        seed_defaults(session)
        session.commit()
    # Record schema version for future migrations and run PRAGMA optimize
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
        )
        conn.execute(
            text("INSERT OR IGNORE INTO schema_meta (key, value) VALUES ('schema_version', '1')")
        )
        conn.exec_driver_sql("PRAGMA optimize;")


def get_db() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
