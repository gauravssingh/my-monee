"""Dedicated runtime read-only SQLite database connection for MCP.

Operating law:
- Connects using URI format: file:...db?mode=ro
- Enforces PRAGMA query_only = ON; at connection level
- Progress handler deadline timeout
- Writable application engine is NOT importable from this module
"""

from __future__ import annotations

import logging
import sqlite3
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from mymonee.config import Settings, get_settings
from mymonee.mcp.errors import AgentServiceError, ErrorCode
from mymonee.mcp.limits import Limits

logger = logging.getLogger(__name__)

_readonly_engine: Engine | None = None
_ReadonlySessionFactory: sessionmaker[Session] | None = None


def _build_readonly_uri(db_path: Path) -> str:
    # Use URI mode=ro for strict OS-level read-only access
    resolved = db_path.resolve()
    return f"sqlite:///file:{resolved}?mode=ro&uri=true"


def _configure_readonly_connection(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def set_sqlite_readonly_pragma(dbapi_connection: Any, connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA query_only = ON;")
            cursor.execute("PRAGMA busy_timeout = 2000;")
        finally:
            cursor.close()

    @event.listens_for(engine, "before_cursor_execute")
    def set_query_deadline(conn: Any, cursor: Any, statement: Any, parameters: Any, context: Any, executemany: Any) -> None:
        t0 = time.monotonic()
        try:
            dbapi_conn = conn.connection.dbapi_connection

            def timeout_progress_handler() -> int:
                if time.monotonic() - t0 > Limits.DB_TIMEOUT_SECONDS:
                    return 1
                return 0

            dbapi_conn.set_progress_handler(timeout_progress_handler, 1000)
        except Exception:  # noqa: BLE001, S110
            pass

    @event.listens_for(engine, "after_cursor_execute")
    def clear_query_deadline(conn: Any, cursor: Any, statement: Any, parameters: Any, context: Any, executemany: Any) -> None:
        try:
            conn.connection.dbapi_connection.set_progress_handler(None, 1000)
        except Exception:  # noqa: BLE001, S110
            pass


def get_readonly_engine(settings: Settings | None = None) -> Engine:
    """Initialize or return the dedicated read-only SQLite engine."""
    global _readonly_engine, _ReadonlySessionFactory
    if _readonly_engine is not None:
        return _readonly_engine

    settings = settings or get_settings()
    db_path = settings.database_path()
    if not db_path.exists():
        # Ensure database file exists before opening read-only
        from mymonee.db.session import init_db
        init_db(settings)

    engine = create_engine(
        _build_readonly_uri(db_path),
        echo=False,
        future=True,
    )
    _configure_readonly_connection(engine)
    _readonly_engine = engine
    _ReadonlySessionFactory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        future=True,
    )
    return engine


@contextmanager
def get_readonly_session(settings: Settings | None = None) -> Generator[Session, None, None]:
    """Context manager yielding a strictly read-only SQLAlchemy session with auto-rollback."""
    if _ReadonlySessionFactory is None:
        get_readonly_engine(settings)
    assert _ReadonlySessionFactory is not None

    session: Session = _ReadonlySessionFactory()
    try:
        yield session
    except sqlite3.OperationalError as err:
        if "readonly database" in str(err) or "query_only" in str(err):
            logger.error("Attempt to mutate read-only database rejected by SQLite pragma: %s", err)
            raise AgentServiceError(
                ErrorCode.INTERNAL,
                "Write operations are strictly prohibited on agent connections.",
            ) from err
        if "interrupted" in str(err) or "progress" in str(err):
            raise AgentServiceError(ErrorCode.TIMEOUT, "Database query timed out.") from err
        raise
    finally:
        try:
            session.rollback()
        except Exception:  # noqa: BLE001, S110
            pass
        session.close()
