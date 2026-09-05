"""Security tests for SQL injection resistance and input tampering."""

from __future__ import annotations

import pytest

from mymonee.config import Settings
from mymonee.mcp.errors import AgentServiceError, ErrorCode
from mymonee.mcp.principal import create_agent_principal
from mymonee.mcp.service import AgentService
from mymonee.mcp.validators import (
    validate_amount_arg,
    validate_date_arg,
    validate_month_arg,
)


@pytest.fixture
def service(db_session, test_settings: Settings) -> AgentService:
    principal = create_agent_principal()
    return AgentService(principal=principal, settings=test_settings)


def test_sql_injection_treated_as_literal_text(service: AgentService):
    """Verify malicious SQL payloads in search queries are parameterized safely."""
    malicious_payloads = [
        "'; DROP TABLE transactions; --",
        "' OR '1'='1",
        "1; SELECT * FROM users --",
        "' UNION SELECT NULL, NULL, NULL --",
    ]
    for payload in malicious_payloads:
        # Should execute safely without database errors or syntax errors
        res = service.search_transactions(query=payload, limit=5)
        assert hasattr(res, "items")
        assert isinstance(res.items, list)


def test_invalid_dates_rejected():
    with pytest.raises(AgentServiceError) as exc_info:
        validate_date_arg("0001-01-01")
    assert exc_info.value.code == ErrorCode.INVALID_ARGUMENT

    with pytest.raises(AgentServiceError) as exc_info:
        validate_date_arg("9999-12-31")
    assert exc_info.value.code == ErrorCode.INVALID_ARGUMENT

    with pytest.raises(AgentServiceError) as exc_info:
        validate_date_arg("not-a-date")
    assert exc_info.value.code == ErrorCode.INVALID_ARGUMENT


def test_invalid_months_rejected():
    with pytest.raises(AgentServiceError) as exc_info:
        validate_month_arg("2026-13")
    assert exc_info.value.code == ErrorCode.INVALID_ARGUMENT

    with pytest.raises(AgentServiceError) as exc_info:
        validate_month_arg("yesterday")
    assert exc_info.value.code == ErrorCode.INVALID_ARGUMENT


def test_negative_amounts_rejected():
    with pytest.raises(AgentServiceError) as exc_info:
        validate_amount_arg(-50.0)
    assert exc_info.value.code == ErrorCode.INVALID_ARGUMENT
