"""Tests for resource limits, clamping, and rate limiting."""

from __future__ import annotations

import pytest

from mymonee.config import get_settings
from mymonee.mcp.errors import AgentServiceError, ErrorCode
from mymonee.mcp.limits import Limits
from mymonee.mcp.principal import create_agent_principal
from mymonee.mcp.service import AgentService
from mymonee.mcp.validators import (
    validate_limit_arg,
    validate_months_arg,
    validate_query_text,
)


def test_limit_bounding():
    # Clamping above max
    assert validate_limit_arg(100) == Limits.MAX_RESULTS
    assert validate_limit_arg(None) == Limits.DEFAULT_RESULTS
    assert validate_limit_arg(25) == 25

    # Rejection of zero or negative
    with pytest.raises(AgentServiceError) as exc_info:
        validate_limit_arg(0)
    assert exc_info.value.code == ErrorCode.INVALID_ARGUMENT

    with pytest.raises(AgentServiceError) as exc_info:
        validate_limit_arg(-10)
    assert exc_info.value.code == ErrorCode.INVALID_ARGUMENT


def test_months_bounding():
    # Clamping above max
    assert validate_months_arg(36) == Limits.MAX_HISTORY_MONTHS
    assert validate_months_arg(None) == Limits.DEFAULT_HISTORY_MONTHS
    assert validate_months_arg(12) == 12

    # Rejection of negative
    with pytest.raises(AgentServiceError) as exc_info:
        validate_months_arg(0)
    assert exc_info.value.code == ErrorCode.INVALID_ARGUMENT


def test_query_length_bounding():
    valid = "Amazon grocery order"
    assert validate_query_text(valid) == valid

    oversized = "x" * (Limits.MAX_QUERY_LENGTH + 1)
    with pytest.raises(AgentServiceError) as exc_info:
        validate_query_text(oversized)
    assert exc_info.value.code == ErrorCode.LIMIT_EXCEEDED


def test_service_rate_limiter():
    """Verify that rapid successive calls trigger RATE_LIMITED error."""
    settings = get_settings()
    principal = create_agent_principal()
    service = AgentService(principal, settings=settings)

    # Exhaust rate limit
    for _ in range(Limits.RATE_LIMIT_PER_MINUTE):
        service._check_rate_limit()

    with pytest.raises(AgentServiceError) as exc_info:
        service._check_rate_limit()
    assert exc_info.value.code == ErrorCode.RATE_LIMITED
