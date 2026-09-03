"""CLI adapter for human and script access to the MyMonee Agent Service.

Shares the exact same AgentService as the MCP server.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from mymonee.config import load_settings
from mymonee.mcp.principal import create_agent_principal
from mymonee.mcp.service import AgentService


def get_agent_service() -> AgentService:
    settings = load_settings()
    principal = create_agent_principal(actor="cli")
    return AgentService(principal=principal, settings=settings)


def format_dto_output(dto: Any, as_json: bool = True) -> None:
    if as_json:
        if hasattr(dto, "model_dump"):
            print(json.dumps(dto.model_dump(), indent=2))
        else:
            print(json.dumps(dto, indent=2))
    else:
        # Formatted display
        print(dto)


def cmd_agent_summary(args: argparse.Namespace) -> None:
    service = get_agent_service()
    res = service.get_financial_summary(month=args.month or "current")
    format_dto_output(res, as_json=not args.text)


def cmd_agent_spending(args: argparse.Namespace) -> None:
    service = get_agent_service()
    res = service.get_category_spending(
        category=args.category,
        month=args.month or "current",
        range_str=args.range or "1m",
    )
    format_dto_output(res, as_json=not args.text)


def cmd_agent_merchant(args: argparse.Namespace) -> None:
    service = get_agent_service()
    res = service.get_merchant_history(
        merchant_name=args.name,
        months=args.months or 6,
        limit=args.limit or 5,
    )
    format_dto_output(res, as_json=not args.text)


def cmd_agent_transactions(args: argparse.Namespace) -> None:
    service = get_agent_service()
    res = service.search_transactions(
        query=args.query,
        category=args.category,
        direction=args.direction or "debit",
        start_date=args.start_date,
        end_date=args.end_date,
        min_amount=args.min_amount,
        max_amount=args.max_amount,
        limit=args.limit or 10,
    )
    format_dto_output(res, as_json=not args.text)


def cmd_agent_recurring(args: argparse.Namespace) -> None:
    service = get_agent_service()
    res = service.get_recurring_expenses()
    format_dto_output(res, as_json=not args.text)


def cmd_agent_income(args: argparse.Namespace) -> None:
    service = get_agent_service()
    res = service.get_income_and_salary(months=args.months or 6)
    format_dto_output(res, as_json=not args.text)


def cmd_agent_trends(args: argparse.Namespace) -> None:
    service = get_agent_service()
    res = service.get_cash_flow_trends(months=args.months or 6)
    format_dto_output(res, as_json=not args.text)


def cmd_agent_categories(args: argparse.Namespace) -> None:
    service = get_agent_service()
    res = service.list_budget_categories()
    format_dto_output(res, as_json=not args.text)


def setup_agent_subparsers(agent_sub: Any) -> None:
    """Register agent subcommands for CLI testing."""
    p_sum = agent_sub.add_parser("summary", help="Monthly financial summary")
    p_sum.add_argument("--month", "-m", default="current", help="'current', 'last', or YYYY-MM")
    p_sum.add_argument("--text", action="store_true", help="Print as text")
    p_sum.set_defaults(func=cmd_agent_summary)

    p_spend = agent_sub.add_parser("spending", help="Category spending breakdown or deep-dive")
    p_spend.add_argument("--category", "-c", default=None, help="Category name")
    p_spend.add_argument("--month", "-m", default="current", help="'current', 'last', or YYYY-MM")
    p_spend.add_argument("--range", "-r", default="1m", help="'1m', '3m', '6m', '12m', 'ytd'")
    p_spend.add_argument("--text", action="store_true", help="Print as text")
    p_spend.set_defaults(func=cmd_agent_spending)

    p_merch = agent_sub.add_parser("merchant", help="Merchant spending history")
    p_merch.add_argument("--name", "-n", required=True, help="Merchant name")
    p_merch.add_argument("--months", type=int, default=6, help="Lookback months")
    p_merch.add_argument("--limit", type=int, default=5, help="Recent transactions limit")
    p_merch.add_argument("--text", action="store_true", help="Print as text")
    p_merch.set_defaults(func=cmd_agent_merchant)

    p_tx = agent_sub.add_parser("transactions", help="Search and filter transactions safely")
    p_tx.add_argument("--query", "-q", default=None, help="Search text")
    p_tx.add_argument("--category", "-c", default=None, help="Category name")
    p_tx.add_argument("--direction", "-d", default="debit", help="debit/credit/all")
    p_tx.add_argument("--start-date", default=None, help="YYYY-MM-DD")
    p_tx.add_argument("--end-date", default=None, help="YYYY-MM-DD")
    p_tx.add_argument("--min-amount", type=float, default=None)
    p_tx.add_argument("--max-amount", type=float, default=None)
    p_tx.add_argument("--limit", type=int, default=10)
    p_tx.add_argument("--text", action="store_true", help="Print as text")
    p_tx.set_defaults(func=cmd_agent_transactions)

    p_rec = agent_sub.add_parser("recurring", help="Active subscriptions and bills")
    p_rec.add_argument("--text", action="store_true", help="Print as text")
    p_rec.set_defaults(func=cmd_agent_recurring)

    p_inc = agent_sub.add_parser("income", help="Pay-period salary and income attribution")
    p_inc.add_argument("--months", type=int, default=6)
    p_inc.add_argument("--text", action="store_true", help="Print as text")
    p_inc.set_defaults(func=cmd_agent_income)

    p_trends = agent_sub.add_parser("trends", help="Multi-month cash flow trends")
    p_trends.add_argument("--months", type=int, default=6)
    p_trends.add_argument("--text", action="store_true", help="Print as text")
    p_trends.set_defaults(func=cmd_agent_trends)

    p_cat = agent_sub.add_parser("categories", help="Authoritative budget category taxonomy")
    p_cat.add_argument("--text", action="store_true", help="Print as text")
    p_cat.set_defaults(func=cmd_agent_categories)
