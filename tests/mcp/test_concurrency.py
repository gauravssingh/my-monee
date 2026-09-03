"""Concurrency gate tests for sequential MCP execution."""

from __future__ import annotations

import asyncio

from mymonee.mcp.server import create_mcp_server


def test_concurrent_tool_calls_execute_safely():
    async def _run():
        server = create_mcp_server()

        # Launch 5 concurrent calls to test the semaphore gate
        tasks = [
            server.call_tool("get_agent_capabilities", {}),
            server.call_tool("list_budget_categories", {}),
            server.call_tool("get_financial_summary", {"month": "current"}),
            server.call_tool("get_recurring_expenses", {}),
            server.call_tool("get_cash_flow_trends", {"months": 3}),
        ]
        results = await asyncio.gather(*tasks)

        assert len(results) == 5
        for r in results:
            assert not r.is_error
            assert r.structured_content is not None

    asyncio.run(_run())
