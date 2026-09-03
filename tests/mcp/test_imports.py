"""Ensure the writable database engine is never imported inside the MCP package."""

from __future__ import annotations

import importlib


def test_writable_engine_not_imported_in_mcp():
    """Verify that mymonee.mcp does not import writable engine or session factory from mymonee.db.session."""
    # Ensure fresh inspection
    mcp_modules = [
        "mymonee.mcp.principal",
        "mymonee.mcp.limits",
        "mymonee.mcp.errors",
        "mymonee.mcp.models",
        "mymonee.mcp.sanitizer",
        "mymonee.mcp.validators",
        "mymonee.mcp.readonly_db",
        "mymonee.mcp.audit",
        "mymonee.mcp.capabilities",
        "mymonee.mcp.service",
        "mymonee.mcp.server",
    ]

    for mod_name in mcp_modules:
        mod = importlib.import_module(mod_name)
        # Verify writable symbols are not present in module namespace
        assert not hasattr(mod, "get_engine"), f"{mod_name} exposes writable get_engine"
        assert not hasattr(mod, "get_session_factory"), f"{mod_name} exposes writable get_session_factory"
        assert not hasattr(mod, "init_engine"), f"{mod_name} exposes writable init_engine"
