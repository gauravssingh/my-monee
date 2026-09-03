"""MyMonee FastMCP server for Hermes Agent integration.

Operating law:
- Uses static AGENT_CAPABILITIES registry
- Annotates every tool with readOnlyHint=True
- Wraps tool execution with concurrency gate (_gate = asyncio.Semaphore(1))
- Catches errors and fails closed with correlation IDs (no traceback leaks)
- Stdio runner ensures sys.stdout is exclusively JSON-RPC wire
"""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from mymonee.config import Settings, get_settings
from mymonee.mcp.capabilities import AGENT_CAPABILITIES
from mymonee.mcp.errors import AgentServiceError, generate_correlation_id
from mymonee.mcp.models import (
    AgentCapabilitiesResponse,
    BudgetTaxonomyResponse,
    CashFlowResponse,
    CategoryDeepDive,
    CategorySpendingResponse,
    ClassifyTransactionResult,
    FinancialSummary,
    IncomeResponse,
    MerchantHistory,
    Page,
    RecurringExpensesResponse,
    TransactionItem,
    UnclassifiedSpendsResult,
)
from mymonee.mcp.principal import AgentPrincipal, create_agent_principal
from mymonee.mcp.service import AgentService

logger = logging.getLogger("mymonee.mcp.server")

# Default read-only annotations for Hermes Agent
READ_ONLY_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
)


def create_mcp_server(
    principal: AgentPrincipal | None = None,
    settings: Settings | None = None,
) -> MCPServer:
    """Instantiate and configure the MyMonee MCP server with static capabilities."""
    principal = principal or create_agent_principal()
    settings = settings or get_settings()
    service = AgentService(principal, settings=settings)

    # Concurrency control: serialize tool queries initially
    gate = asyncio.Semaphore(1)

    server = MCPServer(
        name="mymonee",
        title="MyMonee Personal Finance",
        description="Local-first personal expense and financial intelligence server for Hermes Agent.",
        version="1.0.0",
        instructions=(
            "Use MyMonee tools to answer user questions about expenses, income, categories, "
            "and transactions. Aggregate values returned by MyMonee are authoritative; do not "
            "attempt to independently reconstruct totals. All identifiers are opaque and masked."
        ),
    )

    # Helper wrapper to enforce concurrency gate and error boundary
    async def _execute_with_gate(fn: Any, *args: Any, **kwargs: Any) -> Any:
        async with gate:
            try:
                # AgentService methods are sync; run in thread to avoid blocking event loop
                return await asyncio.to_thread(fn, *args, **kwargs)
            except AgentServiceError as err:
                logger.warning("Agent service error during tool execution: %s", err)
                raise ToolError(err.to_public_message()) from None
            except Exception:
                cid = generate_correlation_id()
                logger.exception("Unexpected error during tool execution [cid=%s]", cid)
                raise ToolError(f"Unable to complete requested operation. [cid: {cid}]") from None

    # 1. get_financial_summary
    spec_summary = AGENT_CAPABILITIES["get_financial_summary"]

    @server.tool(
        name=spec_summary.name,
        description=spec_summary.description,
        annotations=READ_ONLY_ANNOTATIONS,
    )
    async def get_financial_summary(month: str = "current") -> FinancialSummary:
        return await _execute_with_gate(service.get_financial_summary, month=month)

    # 2. get_category_spending
    spec_cat = AGENT_CAPABILITIES["get_category_spending"]

    @server.tool(
        name=spec_cat.name,
        description=spec_cat.description,
        annotations=READ_ONLY_ANNOTATIONS,
    )
    async def get_category_spending(
        category: str | None = None,
        month: str = "current",
        range: str = "1m",
    ) -> CategorySpendingResponse | CategoryDeepDive:
        return await _execute_with_gate(
            service.get_category_spending,
            category=category,
            month=month,
            range_str=range,
        )

    # 3. get_merchant_history
    spec_merch = AGENT_CAPABILITIES["get_merchant_history"]

    @server.tool(
        name=spec_merch.name,
        description=spec_merch.description,
        annotations=READ_ONLY_ANNOTATIONS,
    )
    async def get_merchant_history(
        merchant_name: str,
        months: int = 6,
        limit: int = 5,
    ) -> MerchantHistory:
        return await _execute_with_gate(
            service.get_merchant_history,
            merchant_name=merchant_name,
            months=months,
            limit=limit,
        )

    # 4. search_transactions
    spec_txs = AGENT_CAPABILITIES["search_transactions"]

    @server.tool(
        name=spec_txs.name,
        description=spec_txs.description,
        annotations=READ_ONLY_ANNOTATIONS,
    )
    async def search_transactions(
        query: str | None = None,
        category: str | None = None,
        direction: str = "debit",
        start_date: str | None = None,
        end_date: str | None = None,
        min_amount: float | None = None,
        max_amount: float | None = None,
        limit: int = 10,
        cursor: str | None = None,
    ) -> Page[TransactionItem]:
        return await _execute_with_gate(
            service.search_transactions,
            query=query,
            category=category,
            direction=direction,
            start_date=start_date,
            end_date=end_date,
            min_amount=min_amount,
            max_amount=max_amount,
            limit=limit,
            cursor=cursor,
        )

    # 5. get_recurring_expenses
    spec_rec = AGENT_CAPABILITIES["get_recurring_expenses"]

    @server.tool(
        name=spec_rec.name,
        description=spec_rec.description,
        annotations=READ_ONLY_ANNOTATIONS,
    )
    async def get_recurring_expenses() -> RecurringExpensesResponse:
        return await _execute_with_gate(service.get_recurring_expenses)

    # 6. get_income_and_salary
    spec_inc = AGENT_CAPABILITIES["get_income_and_salary"]

    @server.tool(
        name=spec_inc.name,
        description=spec_inc.description,
        annotations=READ_ONLY_ANNOTATIONS,
    )
    async def get_income_and_salary(months: int = 6) -> IncomeResponse:
        return await _execute_with_gate(service.get_income_and_salary, months=months)

    # 7. get_cash_flow_trends
    spec_trends = AGENT_CAPABILITIES["get_cash_flow_trends"]

    @server.tool(
        name=spec_trends.name,
        description=spec_trends.description,
        annotations=READ_ONLY_ANNOTATIONS,
    )
    async def get_cash_flow_trends(months: int = 6) -> CashFlowResponse:
        return await _execute_with_gate(service.get_cash_flow_trends, months=months)

    # 8. list_budget_categories
    spec_budg = AGENT_CAPABILITIES["list_budget_categories"]

    @server.tool(
        name=spec_budg.name,
        description=spec_budg.description,
        annotations=READ_ONLY_ANNOTATIONS,
    )
    async def list_budget_categories() -> BudgetTaxonomyResponse:
        return await _execute_with_gate(service.list_budget_categories)

    # 9. get_agent_capabilities
    spec_cap = AGENT_CAPABILITIES["get_agent_capabilities"]

    @server.tool(
        name=spec_cap.name,
        description=spec_cap.description,
        annotations=READ_ONLY_ANNOTATIONS,
    )
    async def get_agent_capabilities() -> AgentCapabilitiesResponse:
        return await _execute_with_gate(service.get_agent_capabilities)

    # 10. get_unclassified_spends
    spec_unc = AGENT_CAPABILITIES["get_unclassified_spends"]

    @server.tool(
        name=spec_unc.name,
        description=spec_unc.description,
        annotations=READ_ONLY_ANNOTATIONS,
    )
    async def get_unclassified_spends(
        limit: int = 10,
        cursor: str | None = None,
    ) -> UnclassifiedSpendsResult:
        return await _execute_with_gate(service.get_unclassified_spends, limit=limit, cursor=cursor)

    # 11. classify_transaction
    spec_cls = AGENT_CAPABILITIES["classify_transaction"]

    WRITE_ANNOTATIONS = ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
    )

    @server.tool(
        name=spec_cls.name,
        description=spec_cls.description,
        annotations=WRITE_ANNOTATIONS,
    )
    async def classify_transaction(
        transaction_id: str,
        category: str,
        subcategory: str | None = None,
        create_rule: bool = True,
        apply_to_past: bool = False,
        reasoning: str | None = None,
    ) -> ClassifyTransactionResult:
        return await _execute_with_gate(
            service.classify_transaction,
            transaction_id=transaction_id,
            category=category,
            subcategory=subcategory,
            create_rule=create_rule,
            apply_to_past=apply_to_past,
            reasoning=reasoning,
        )

    return server


def run_mcp_stdio() -> None:
    """Launch the MyMonee FastMCP server on standard I/O for Hermes Agent.

    CRITICAL: Does NOT print human-readable text to stdout. All logs go to stderr.
    """
    # Direct standard root logging to stderr exclusively
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger.info("Initializing MyMonee MCP Server on stdio transport...")

    server = create_mcp_server()
    asyncio.run(server.run_stdio_async())
