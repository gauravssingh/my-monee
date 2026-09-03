"""Tests for controlled error model and correlation IDs."""

from __future__ import annotations

from mymonee.mcp.errors import AgentServiceError, ErrorCode, generate_correlation_id


def test_correlation_id_format():
    cid = generate_correlation_id()
    assert isinstance(cid, str)
    assert len(cid) == 12
    assert cid.isalnum()


def test_public_error_message_does_not_leak_internal_details():
    err = AgentServiceError(
        ErrorCode.INTERNAL,
        message="Safe public description",
        cid="test_cid_999",
        internal_detail="sqlite3.OperationalError: table /Users/gauravsingh/db.sqlite locked",
    )
    public_msg = err.to_public_message()
    assert (
        "Safe public description" not in public_msg
    )  # Internal errors fail closed with generic message
    assert "Unable to complete requested operation. [cid: test_cid_999]" == public_msg
    assert "/Users/gauravsingh" not in public_msg
    assert "sqlite3" not in public_msg


def test_argument_error_message_is_safe():
    err = AgentServiceError(
        ErrorCode.INVALID_ARGUMENT,
        message="Invalid month format 'bad-date'.",
        cid="test_cid_888",
    )
    public_msg = err.to_public_message()
    assert "Invalid month format 'bad-date'. [cid: test_cid_888]" == public_msg
