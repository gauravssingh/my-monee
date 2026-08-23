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
    def set_sqlite_pragma(dbapi_connection, connection_record) -> None:  # noqa: ARG001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


def init_engine(settings: Settings | None = None) -> Engine:
    global _engine, _SessionLocal
    settings = settings or get_settings()
    db_path = settings.database_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(
        _sqlite_url(db_path),
        echo=settings.database.echo,
        future=True,
    )
    _configure_sqlite(engine)
    _engine = engine
    _SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return engine


def get_engine() -> Engine:
    if _engine is None:
        return init_engine()
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    if _SessionLocal is None:
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


def init_db(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    engine = init_engine(settings)
    Base.metadata.create_all(bind=engine)
    _migrate_columns(engine)
    with Session(engine) as session:
        seed_defaults(session)
        session.commit()
    # Record schema version for future migrations
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS schema_meta ("
                "key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
        )
        conn.execute(
            text(
                "INSERT OR IGNORE INTO schema_meta (key, value) VALUES ('schema_version', '1')"
            )
        )


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
