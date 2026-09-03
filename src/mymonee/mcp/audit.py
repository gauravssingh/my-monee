"""Structured, privacy-safe audit logging for MCP agent operations."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from mymonee.mcp.principal import AgentPrincipal

logger = logging.getLogger("mymonee.mcp.audit")


def hash_query_text(query: str | None) -> str | None:
    """Hash query text with SHA-256 (truncated) to prevent logging raw PII search terms."""
    if not query:
        return None
    return hashlib.sha256(query.encode("utf-8")).hexdigest()[:12]


def log_audit_event(
    *,
    cid: str,
    tool: str,
    principal: AgentPrincipal,
    duration_ms: float,
    outcome: str = "ok",
    db_ms: float = 0.0,
    result_bytes: int = 0,
    items_count: int | None = None,
    has_more: bool | None = None,
    error_code: str | None = None,
    query_hash: str | None = None,
) -> None:
    """Record a structured, privacy-safe audit event."""
    event: dict[str, Any] = {
        "event": "mcp.tool",
        "cid": cid,
        "tool": tool,
        "tool_version": "1.0",
        "actor": principal.actor,
        "profile": principal.profile,
        "duration_ms": round(duration_ms, 2),
        "db_ms": round(db_ms, 2),
        "result_bytes": result_bytes,
        "outcome": outcome,
    }
    if items_count is not None:
        event["items"] = items_count
    if has_more is not None:
        event["has_more"] = has_more
    if error_code is not None:
        event["error_code"] = error_code
    if query_hash is not None:
        event["query_hash"] = query_hash

    logger.info(json.dumps(event))
