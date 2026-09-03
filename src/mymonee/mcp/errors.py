"""Controlled error model and correlation ID handling for MCP operations."""

from __future__ import annotations

import logging
import uuid
from enum import StrEnum

logger = logging.getLogger(__name__)


class ErrorCode(StrEnum):
    """Normalized error codes exposed across MCP interfaces."""

    INVALID_ARGUMENT = "invalid_argument"
    NOT_FOUND = "not_found"
    LIMIT_EXCEEDED = "limit_exceeded"
    RESPONSE_TOO_LARGE = "response_too_large"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    INTERNAL = "internal"


def generate_correlation_id() -> str:
    """Generate a short, unique correlation ID for tracing."""
    return uuid.uuid4().hex[:12]


class AgentServiceError(Exception):
    """Controlled exception raised by the Agent Service.

    Guarantees internal tracebacks and raw database messages do not leak to the agent.
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        cid: str | None = None,
        internal_detail: str | None = None,
    ) -> None:
        self.code = code
        self.cid = cid or generate_correlation_id()
        self.user_message = message
        self.internal_detail = internal_detail or message
        super().__init__(f"[{self.code}] {self.user_message} (cid: {self.cid})")

    def to_public_message(self) -> str:
        """Format a safe, correlation-tracked message for Hermes."""
        if self.code in (ErrorCode.INVALID_ARGUMENT, ErrorCode.NOT_FOUND, ErrorCode.LIMIT_EXCEEDED, ErrorCode.RATE_LIMITED):
            return f"{self.user_message} [cid: {self.cid}]"
        # All internal, timeout, or unexpected errors fail closed with a generic message
        return f"Unable to complete requested operation. [cid: {self.cid}]"
