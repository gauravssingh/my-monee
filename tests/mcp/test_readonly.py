"""Read-only enforcement and automated statement tracing tests."""

from __future__ import annotations

import pytest
from sqlalchemy import event, text

from mymonee.config import get_settings
from mymonee.mcp.errors import AgentServiceError
from mymonee.mcp.principal import create_agent_principal
from mymonee.mcp.readonly_db import get_readonly_engine, get_readonly_session
from mymonee.mcp.service import AgentService

MUTATION_KEYWORDS = [
    "INSERT",
    "UPDATE",
    "DELETE",
    "REPLACE",
    "UPSERT",
    "DROP",
    "ALTER",
    "CREATE",
    "VACUUM",
    "ATTACH",
    "DETACH",
]


def test_sqlite_runtime_readonly_enforcement():
    """Verify that the SQLite engine at the connection level actively rejects writes."""
    settings = get_settings()

    with pytest.raises((Exception, AgentServiceError)), get_readonly_session(settings) as session:
        session.execute(text("CREATE TABLE evil_table (id INT)"))
        session.commit()

    with pytest.raises((Exception, AgentServiceError)), get_readonly_session(settings) as session:
        session.execute(text("DELETE FROM transactions WHERE 1=1"))
        session.commit()


def test_automated_sql_statement_tracing_on_tool_execution():
    """Verify via SQLAlchemy cursor events that zero mutation statements occur during tool execution."""
    settings = get_settings()
    engine = get_readonly_engine(settings)
    executed_statements: list[str] = []

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        executed_statements.append(statement.strip())

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    try:
        principal = create_agent_principal()
        service = AgentService(principal, settings=settings)

        # Run multiple domain capabilities
        service.get_financial_summary(month="current")
        service.get_category_spending()
        service.list_budget_categories()
        service.get_recurring_expenses()
        service.get_cash_flow_trends(months=3)
        service.search_transactions(limit=5)

        # Assert statements were executed
        assert len(executed_statements) > 0, "Expected SQL queries to be executed during tool calls"

        # Check every statement for prohibited mutation keywords
        for stmt in executed_statements:
            normalized = stmt.upper().split()
            first_word = normalized[0] if normalized else ""
            assert first_word not in MUTATION_KEYWORDS, (
                f"Prohibited mutation SQL operation detected: {stmt}"
            )
            for kw in MUTATION_KEYWORDS:
                # Ensure statement does not begin with or contain mutation keywords as standalone command
                assert not stmt.upper().startswith(kw + " "), f"Statement begins with mutation keyword {kw}: {stmt}"
    finally:
        event.remove(engine, "before_cursor_execute", before_cursor_execute)
