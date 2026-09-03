"""Protocol and tool registration tests for MyMonee MCP Server."""

from __future__ import annotations

import asyncio

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from mymonee.mcp.capabilities import AGENT_CAPABILITY_NAMES
from mymonee.mcp.server import create_mcp_server


def test_server_tool_registration_matches_capabilities():
    async def _run():
        server = create_mcp_server()
        tools = await server.list_tools()
        registered_names = {t.name for t in tools}

        assert registered_names == AGENT_CAPABILITY_NAMES, (
            f"Mismatch between registered MCP tools and AGENT_CAPABILITY_NAMES: {registered_names ^ AGENT_CAPABILITY_NAMES}"
        )
        for tool in tools:
            assert tool.annotations is not None
            if tool.name == "classify_transaction":
                assert tool.annotations.read_only_hint is False, (
                    f"{tool.name} should declare read_only_hint=False"
                )
            else:
                assert tool.annotations.read_only_hint is True, (
                    f"{tool.name} does not declare read_only_hint=True"
                )

    asyncio.run(_run())


def test_server_call_tool_success():
    async def _run():
        server = create_mcp_server()
        res = await server.call_tool("get_agent_capabilities", {})
        assert not res.is_error
        assert res.structured_content is not None
        assert res.structured_content.get("agent_api_version") == "1.0"
        assert len(res.structured_content.get("capabilities", [])) == 11

    asyncio.run(_run())


def test_server_call_tool_invalid_argument_error_boundary():
    async def _run():
        server = create_mcp_server()
        with pytest.raises(ToolError) as exc_info:
            await server.call_tool("get_financial_summary", {"month": "bad-month-99"})

        err_str = str(exc_info.value)
        assert "Invalid month format" in err_str
        assert "cid:" in err_str
        assert "Traceback" not in err_str

    asyncio.run(_run())
