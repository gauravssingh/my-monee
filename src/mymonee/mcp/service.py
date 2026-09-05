"""MyMonee Agent Service Layer.

Authoritative domain orchestration, input validation, resource limits,
rate limiting, and fail-closed privacy validation.
"""

from __future__ import annotations

import base64
import logging
import time
from collections import deque
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from mymonee.analytics.category import get_category_analytics
from mymonee.analytics.common import IST, month_bounds, shift_month
from mymonee.config import Settings, get_settings
from mymonee.db.models import (
    Bill,
    Category,
    RecurringTransaction,
    Subscription,
    Transaction,
)
from mymonee.mcp.audit import hash_query_text, log_audit_event
from mymonee.mcp.errors import AgentServiceError, ErrorCode, generate_correlation_id
from mymonee.mcp.limits import Limits
from mymonee.mcp.models import (
    AgentCapabilitiesResponse,
    BudgetTaxonomyResponse,
    CashFlowResponse,
    CashFlowTrendItem,
    CategoryDeepDive,
    CategoryInsightItem,
    CategorySpendingItem,
    CategorySpendingResponse,
    CategorySummaryItem,
    CategoryTaxonomyItem,
    ClassifyTransactionResult,
    FinancialSummary,
    IncomeResponse,
    IncomeSummaryItem,
    MerchantHistory,
    Page,
    RecurringExpenseItem,
    RecurringExpensesResponse,
    SalaryAttributionItem,
    SubcategorySpendingItem,
    SubcategoryTaxonomyItem,
    TopMerchantSummaryItem,
    TransactionItem,
    UnclassifiedSpendsResult,
    UnclassifiedTransactionItem,
    from_public_id,
    money_from_decimal,
    to_public_id,
)
from mymonee.mcp.principal import AgentPrincipal
from mymonee.mcp.readonly_db import get_readonly_session
from mymonee.mcp.sanitizer import (
    mask_account,
    sanitize_description,
    sanitize_merchant,
    validate_agent_dto,
)
from mymonee.mcp.validators import (
    validate_amount_arg,
    validate_date_arg,
    validate_direction_arg,
    validate_limit_arg,
    validate_month_arg,
    validate_months_arg,
    validate_query_text,
    validate_range_arg,
)
from mymonee.services.categories import list_categories
from mymonee.services.dashboard import (
    _income_candidates_around,
    _valid_spending_filters,
    financial_trends,
    get_overview,
    salary_pay_period,
)
from mymonee.services.transactions import list_transactions

logger = logging.getLogger(__name__)


class AgentService:
    """Core Agent Service providing secure, read-only financial data to AI agents."""

    def __init__(
        self,
        principal: AgentPrincipal,
        settings: Settings | None = None,
    ) -> None:
        if not principal.is_authorized():
            raise AgentServiceError(
                ErrorCode.INTERNAL,
                "Unauthorized agent principal.",
            )
        self.principal = principal
        self.settings = settings or get_settings()
        self._call_timestamps: deque[float] = deque()

    def _check_rate_limit(self) -> None:
        """Enforce rate limiting (120 calls/min, burst 20)."""
        now = time.monotonic()
        cutoff = now - 60.0
        while self._call_timestamps and self._call_timestamps[0] < cutoff:
            self._call_timestamps.popleft()

        if len(self._call_timestamps) >= Limits.RATE_LIMIT_PER_MINUTE:
            raise AgentServiceError(
                ErrorCode.RATE_LIMITED,
                "Rate limit exceeded (maximum 120 calls per minute).",
            )
        self._call_timestamps.append(now)

    def _resolve_year_month(self, month_arg: str) -> tuple[int, int]:
        """Convert 'current', 'last', or 'YYYY-MM' to (year, month)."""
        now = datetime.now(IST)
        if month_arg == "current":
            return now.year, now.month
        if month_arg == "last":
            return shift_month(now.year, now.month, -1)
        # Assumed valid YYYY-MM
        parts = month_arg.split("-")
        return int(parts[0]), int(parts[1])

    # -------------------------------------------------------------------------
    # 1. get_financial_summary
    # -------------------------------------------------------------------------
    def get_financial_summary(self, month: str = "current") -> FinancialSummary:
        """Return authoritative high-level monthly financial overview."""
        self._check_rate_limit()
        cid = generate_correlation_id()
        month_val = validate_month_arg(month)
        y, m = self._resolve_year_month(month_val)
        period_str = f"{y:04d}-{m:02d}"

        t0 = time.monotonic()
        with get_readonly_session(self.settings) as session:
            db_t0 = time.monotonic()
            overview = get_overview(session, year=y, month=m)
            db_duration = (time.monotonic() - db_t0) * 1000

        summary = overview.get("summary", {})
        top_cats = [
            CategorySummaryItem(
                name=c["category"],
                amount=money_from_decimal(c["total"]),
                percentage=float(c.get("percentage", 0.0)),
            )
            for c in overview.get("category_breakdown", [])[:5]
        ]
        top_merchants = [
            TopMerchantSummaryItem(
                name=sanitize_merchant(None, m_info["merchant"]),
                amount=money_from_decimal(m_info["total"]),
                count=int(m_info.get("count", 0)),
                public_id=to_public_id("merch", m_info["merchant"], self.principal.profile),
            )
            for m_info in overview.get("top_merchants", [])[:5]
        ]

        result = FinancialSummary(
            period=period_str,
            currency="INR",
            total_spent=money_from_decimal(summary.get("spent", 0.0)),
            consumer_spent=money_from_decimal(summary.get("consumer_spent", 0.0)),
            commitments_spent=money_from_decimal(summary.get("commitments_spent", 0.0)),
            income=money_from_decimal(summary.get("income", 0.0)),
            net_cash_flow=money_from_decimal(summary.get("net_cash_flow", 0.0)),
            previous_month_spent=money_from_decimal(
                overview.get("month_comparison", {}).get("previous_spent", 0.0)
            ),
            spent_change_pct=overview.get("month_comparison", {}).get("spent_change_pct"),
            transaction_count=int(summary.get("transaction_count", 0)),
            top_categories=top_cats,
            top_merchants=top_merchants,
        )

        validate_agent_dto(result, cid=cid)
        duration_ms = (time.monotonic() - t0) * 1000
        log_audit_event(
            cid=cid,
            tool="get_financial_summary",
            principal=self.principal,
            duration_ms=duration_ms,
            db_ms=db_duration,
            result_bytes=len(result.model_dump_json()),
        )
        return result

    # -------------------------------------------------------------------------
    # 2. get_category_spending
    # -------------------------------------------------------------------------
    def get_category_spending(
        self,
        category: str | None = None,
        month: str = "current",
        range_str: str = "1m",
    ) -> CategorySpendingResponse | CategoryDeepDive:
        """Return category spending breakdown across categories or deep-dive for one."""
        self._check_rate_limit()
        cid = generate_correlation_id()
        month_val = validate_month_arg(month)
        range_val = validate_range_arg(range_str)
        y, m = self._resolve_year_month(month_val)

        t0 = time.monotonic()
        with get_readonly_session(self.settings) as session:
            db_t0 = time.monotonic()
            if not category or not category.strip():
                # Cross-category spending breakdown
                overview = get_overview(session, year=y, month=m)
                db_duration = (time.monotonic() - db_t0) * 1000
                items = [
                    CategorySpendingItem(
                        category=c["category"],
                        total=money_from_decimal(c["total"]),
                        previous_total=money_from_decimal(c.get("previous_total", 0.0)),
                        change_pct=round(
                            ((c["total"] - c["previous_total"]) / c["previous_total"] * 100.0), 1
                        )
                        if c.get("previous_total", 0.0) > 0
                        else None,
                        transaction_count=int(c.get("count", 0)),
                        share_pct=float(c.get("percentage", 0.0)),
                    )
                    for c in overview.get("category_breakdown", [])
                ]
                total_qual = overview.get("summary", {}).get("spent", 0.0)
                res_cross = CategorySpendingResponse(
                    period=f"{y:04d}-{m:02d}",
                    range=range_val,
                    categories=items,
                    total_qualifying_spent=money_from_decimal(total_qual),
                )
                validate_agent_dto(res_cross, cid=cid)
                log_audit_event(
                    cid=cid,
                    tool="get_category_spending",
                    principal=self.principal,
                    duration_ms=(time.monotonic() - t0) * 1000,
                    db_ms=db_duration,
                    items_count=len(items),
                )
                return res_cross

            # Single category deep-dive
            cat_query = category.strip()
            cat_db = session.scalars(
                select(Category).where(
                    (func.lower(Category.name) == cat_query.lower())
                    | (func.lower(Category.slug) == cat_query.lower())
                )
            ).first()
            if not cat_db:
                raise AgentServiceError(
                    ErrorCode.NOT_FOUND,
                    f"Category '{category}' not found in budget taxonomy.",
                    cid=cid,
                )

            cat_name = cat_db.name
            analytics = get_category_analytics(
                session, cat_db.id, range_str=range_val, year=y, month=m
            )
            db_duration = (time.monotonic() - db_t0) * 1000

        summary = analytics.get("summary", {})
        subcats = [
            SubcategorySpendingItem(
                subcategory=s.get("name", "Unknown"),
                total=money_from_decimal(s.get("period_spend", 0.0)),
                transaction_count=int(s.get("transaction_count", 0)),
                mom_change_pct=s.get("mom_change_pct"),
            )
            for s in analytics.get("subcategories", [])
        ]
        top_merchants = [
            TopMerchantSummaryItem(
                name=sanitize_merchant(None, m_info.get("name")),
                amount=money_from_decimal(m_info.get("spend", 0.0)),
                count=int(m_info.get("tx_count", 0)),
                public_id=to_public_id(
                    "merch", m_info.get("name", "unknown"), self.principal.profile
                ),
            )
            for m_info in analytics.get("merchants", [])[:10]
        ]
        insights = [
            CategoryInsightItem(
                type=i.get("type", "insight"),
                title=i.get("title", "Insight"),
                message=i.get("message", ""),
                severity=i.get("severity", "info"),
            )
            for i in analytics.get("insights", [])
        ]

        res_deep = CategoryDeepDive(
            category=cat_name,
            period_range=range_val,
            total_spent=money_from_decimal(summary.get("period_total_spend", 0.0)),
            previous_period_spent=money_from_decimal(summary.get("previous_period_spend", 0.0)),
            period_change_pct=summary.get("period_change_pct"),
            current_month_spent=money_from_decimal(summary.get("current_month_spend", 0.0)),
            previous_month_spent=money_from_decimal(summary.get("previous_month_spend", 0.0)),
            current_month_mom_change_pct=summary.get("current_month_mom_change_pct"),
            avg_ticket=money_from_decimal(summary.get("avg_ticket", 0.0)),
            median_ticket=money_from_decimal(summary.get("median_ticket", 0.0)),
            share_of_living_pct=round(float(summary.get("share_of_living_spend", 0.0)) * 100.0, 1),
            subcategories=subcats,
            top_merchants=top_merchants,
            insights=insights,
        )
        validate_agent_dto(res_deep, cid=cid)
        log_audit_event(
            cid=cid,
            tool="get_category_spending",
            principal=self.principal,
            duration_ms=(time.monotonic() - t0) * 1000,
            db_ms=db_duration,
        )
        return res_deep

    # -------------------------------------------------------------------------
    # 3. get_merchant_history
    # -------------------------------------------------------------------------
    def get_merchant_history(
        self,
        merchant_name: str,
        months: int = 6,
        limit: int = 5,
    ) -> MerchantHistory:
        """Lookup merchant spend, history, and recent purchases."""
        self._check_rate_limit()
        cid = generate_correlation_id()
        if not merchant_name or not merchant_name.strip():
            raise AgentServiceError(
                ErrorCode.INVALID_ARGUMENT, "Merchant name is required.", cid=cid
            )

        clean_name = validate_query_text(merchant_name)
        months_val = validate_months_arg(months)
        limit_val = validate_limit_arg(
            limit, default=Limits.DEFAULT_MERCHANT_RECENT, max_limit=Limits.MAX_MERCHANT_RECENT
        )

        now = datetime.now(IST)
        start_year, start_month = shift_month(now.year, now.month, -(months_val - 1))
        start_dt, _ = month_bounds(start_year, start_month)

        t0 = time.monotonic()
        with get_readonly_session(self.settings) as session:
            db_t0 = time.monotonic()
            # Find merchant matching query string or display name
            like_term = f"%{clean_name}%"
            stmt = (
                select(Transaction)
                .options(joinedload(Transaction.category), joinedload(Transaction.subcategory))
                .where(
                    (Transaction.merchant_normalized.ilike(like_term))
                    | (Transaction.merchant_raw.ilike(like_term))
                )
                .where(Transaction.transaction_date >= start_dt)
                .where(*_valid_spending_filters())
                .order_by(Transaction.transaction_date.desc())
            )
            txs = session.scalars(stmt).unique().all()
            db_duration = (time.monotonic() - db_t0) * 1000

            if not txs:
                raise AgentServiceError(
                    ErrorCode.NOT_FOUND,
                    f"No transaction history found for merchant '{clean_name}'.",
                    cid=cid,
                )

            total_amount = sum(Decimal(str(tx.amount or 0)) for tx in txs)
            tx_count = len(txs)
            avg_amount = total_amount / tx_count if tx_count > 0 else Decimal("0.00")
            first_seen = min(tx.transaction_date for tx in txs).strftime("%Y-%m-%d")
            last_seen = max(tx.transaction_date for tx in txs).strftime("%Y-%m-%d")

            canonical_merchant = sanitize_merchant(txs[0].merchant_raw, txs[0].merchant_normalized)
            recent_items = [
                TransactionItem(
                    public_id=to_public_id("txn", tx.id, self.principal.profile),
                    date=tx.transaction_date.strftime("%Y-%m-%d") if tx.transaction_date else "",
                    amount=money_from_decimal(tx.amount),
                    merchant=sanitize_merchant(tx.merchant_raw, tx.merchant_normalized),
                    category=tx.category.name if tx.category else None,
                    subcategory=tx.subcategory.name if tx.subcategory else None,
                    account_masked=mask_account(tx.account),
                    payment_method=tx.payment_method,
                    description=sanitize_description(tx.description),
                )
                for tx in txs[:limit_val]
            ]

            result = MerchantHistory(
                public_id=to_public_id("merch", canonical_merchant, self.principal.profile),
                merchant_name=canonical_merchant,
                total_spent=money_from_decimal(total_amount),
                transaction_count=tx_count,
                average_ticket=money_from_decimal(avg_amount),
                first_seen=first_seen,
                last_seen=last_seen,
                recent_transactions=recent_items,
            )
        validate_agent_dto(result, cid=cid)
        log_audit_event(
            cid=cid,
            tool="get_merchant_history",
            principal=self.principal,
            duration_ms=(time.monotonic() - t0) * 1000,
            db_ms=db_duration,
            query_hash=hash_query_text(clean_name),
            items_count=len(recent_items),
        )
        return result

    # -------------------------------------------------------------------------
    # 4. search_transactions
    # -------------------------------------------------------------------------
    def search_transactions(
        self,
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
        """Search and filter transactions with strict privacy masking and pagination."""
        self._check_rate_limit()
        cid = generate_correlation_id()

        clean_query = validate_query_text(query)
        clean_dir = validate_direction_arg(direction)
        parsed_start = validate_date_arg(start_date, "start_date")
        parsed_end = validate_date_arg(end_date, "end_date")
        min_amt = validate_amount_arg(min_amount, "min_amount")
        max_amt = validate_amount_arg(max_amount, "max_amount")
        limit_val = validate_limit_arg(
            limit, default=Limits.DEFAULT_RESULTS, max_limit=Limits.MAX_RESULTS
        )

        offset = 0
        if cursor:
            try:
                decoded = base64.b64decode(cursor).decode("utf-8")
                offset = int(decoded.split(":")[-1])
            except Exception:  # noqa: BLE001
                raise AgentServiceError(
                    ErrorCode.INVALID_ARGUMENT, "Invalid pagination cursor.", cid=cid
                )

        t0 = time.monotonic()
        with get_readonly_session(self.settings) as session:
            db_t0 = time.monotonic()
            raw_res = list_transactions(
                session,
                limit=limit_val + 1,  # fetch one extra to know if has_more
                offset=offset,
                direction=None if clean_dir == "all" else clean_dir,
                q=clean_query,
                date_from=parsed_start,
                date_to=parsed_end,
                category_id=category,
                sort_by="date",
                sort_dir="desc",
            )
            db_duration = (time.monotonic() - db_t0) * 1000

        tx_list = raw_res.get("items", [])
        if min_amt is not None:
            tx_list = [tx for tx in tx_list if float(tx.get("amount") or 0.0) >= min_amt]
        if max_amt is not None:
            tx_list = [tx for tx in tx_list if float(tx.get("amount") or 0.0) <= max_amt]

        has_more = len(tx_list) > limit_val
        items_slice = tx_list[:limit_val]

        items = [
            TransactionItem(
                public_id=to_public_id("txn", tx["id"], self.principal.profile),
                date=tx["transaction_date"][:10] if tx.get("transaction_date") else "",
                amount=money_from_decimal(tx.get("amount")),
                merchant=sanitize_merchant(tx.get("merchant_raw"), tx.get("merchant_normalized")),
                category=tx.get("category"),
                subcategory=tx.get("subcategory"),
                account_masked=mask_account(tx.get("account")),
                payment_method=tx.get("payment_method"),
                description=sanitize_description(tx.get("description")),
            )
            for tx in items_slice
        ]

        next_cursor = None
        if has_more:
            next_offset = offset + limit_val
            next_cursor = base64.b64encode(f"cursor:{next_offset}".encode()).decode("utf-8")

        result = Page[TransactionItem](
            items=items,
            has_more=has_more,
            next_cursor=next_cursor,
            total_count=raw_res.get("total"),
        )
        validate_agent_dto(result, cid=cid)
        log_audit_event(
            cid=cid,
            tool="search_transactions",
            principal=self.principal,
            duration_ms=(time.monotonic() - t0) * 1000,
            db_ms=db_duration,
            query_hash=hash_query_text(clean_query),
            items_count=len(items),
            has_more=has_more,
        )
        return result

    # -------------------------------------------------------------------------
    # 5. get_recurring_expenses
    # -------------------------------------------------------------------------
    def get_recurring_expenses(self) -> RecurringExpensesResponse:
        """List active recurring subscriptions and scheduled bills."""
        self._check_rate_limit()
        cid = generate_correlation_id()

        t0 = time.monotonic()
        with get_readonly_session(self.settings) as session:
            db_t0 = time.monotonic()
            subscriptions_db = session.execute(
                select(Subscription, RecurringTransaction).join(
                    RecurringTransaction,
                    Subscription.recurring_transaction_id == RecurringTransaction.id,
                )
            ).all()

            bills_db = session.execute(
                select(Bill, RecurringTransaction).join(
                    RecurringTransaction, Bill.recurring_transaction_id == RecurringTransaction.id
                )
            ).all()
            db_duration = (time.monotonic() - db_t0) * 1000

            subs: list[RecurringExpenseItem] = []
            total_monthly = Decimal("0.00")
            total_annual = Decimal("0.00")

            for s, rt in subscriptions_db:
                amt = Decimal(str(s.amount or 0.0))
                freq = (rt.frequency or "monthly").lower()
                annual = (
                    Decimal(str(s.annual_cost))
                    if s.annual_cost
                    else (amt if freq == "yearly" else amt * 12)
                )
                monthly = (
                    amt if freq == "monthly" else (annual / 12 if annual > 0 else Decimal("0.00"))
                )
                total_monthly += monthly
                total_annual += annual

                subs.append(
                    RecurringExpenseItem(
                        service_name=s.name[:50],
                        amount=money_from_decimal(amt),
                        billing_frequency=freq,
                        next_expected_date=rt.next_expected_date.strftime("%Y-%m-%d")
                        if rt.next_expected_date
                        else None,
                        annual_cost=money_from_decimal(annual),
                        status=s.status or "active",
                    )
                )

            bills: list[RecurringExpenseItem] = []
            for b, rt in bills_db:
                amt = Decimal(str(rt.expected_amount or 0.0))
                freq = (rt.frequency or "monthly").lower()
                annual = amt * 12 if freq == "monthly" else amt
                monthly = amt if freq == "monthly" else annual / 12
                total_monthly += monthly
                total_annual += annual

                bills.append(
                    RecurringExpenseItem(
                        service_name=b.name[:50],
                        amount=money_from_decimal(amt),
                        billing_frequency=freq,
                        next_expected_date=rt.next_expected_date.strftime("%Y-%m-%d")
                        if rt.next_expected_date
                        else None,
                        annual_cost=money_from_decimal(annual),
                        status=b.status or "active",
                    )
                )

            result = RecurringExpensesResponse(
                subscriptions=subs,
                bills=bills,
                total_monthly_burn=money_from_decimal(total_monthly),
                total_annual_cost=money_from_decimal(total_annual),
            )
        validate_agent_dto(result, cid=cid)
        log_audit_event(
            cid=cid,
            tool="get_recurring_expenses",
            principal=self.principal,
            duration_ms=(time.monotonic() - t0) * 1000,
            db_ms=db_duration,
            items_count=len(subs) + len(bills),
        )
        return result

    # -------------------------------------------------------------------------
    # 6. get_income_and_salary
    # -------------------------------------------------------------------------
    def get_income_and_salary(self, months: int = 6) -> IncomeResponse:
        """Report salary and income by pay-period over the last N months."""
        self._check_rate_limit()
        cid = generate_correlation_id()
        months_val = validate_months_arg(months)

        now = datetime.now(IST)
        monthly_totals: list[IncomeSummaryItem] = []
        salary_credits: list[SalaryAttributionItem] = []

        t0 = time.monotonic()
        with get_readonly_session(self.settings) as session:
            db_t0 = time.monotonic()
            for offset in range(-(months_val - 1), 1):
                y, m = shift_month(now.year, now.month, offset)
                candidates = _income_candidates_around(session, y, m)

                sal_month = Decimal("0.00")
                oth_month = Decimal("0.00")

                for tx in candidates:
                    if not tx.transaction_date:
                        continue
                    dt = (
                        tx.transaction_date.astimezone(IST)
                        if tx.transaction_date.tzinfo
                        else tx.transaction_date
                    )
                    is_salary = tx.subcategory and tx.subcategory.slug == "salary"

                    if is_salary:
                        py, pm = salary_pay_period(tx.transaction_date)
                        if py == y and pm == m:
                            amt = Decimal(str(tx.amount or 0.0))
                            sal_month += amt
                            # Add to recent salary credits list if in the last 3 months
                            if offset >= -2:
                                salary_credits.append(
                                    SalaryAttributionItem(
                                        calendar_month=f"{dt.year:04d}-{dt.month:02d}",
                                        pay_period_month=f"{py:04d}-{pm:02d}",
                                        amount=money_from_decimal(amt),
                                        received_date=dt.strftime("%Y-%m-%d"),
                                        attribution_note=(
                                            "Credit received on or before day 2 pays current month"
                                            if dt.day <= 2
                                            else "Credit received after day 2 pays next month"
                                        ),
                                    )
                                )
                    else:
                        if dt.year == y and dt.month == m:
                            oth_month += Decimal(str(tx.amount or 0.0))

                tot = sal_month + oth_month
                monthly_totals.append(
                    IncomeSummaryItem(
                        month=f"{y:04d}-{m:02d}",
                        salary_income=money_from_decimal(sal_month),
                        other_income=money_from_decimal(oth_month),
                        total_income=money_from_decimal(tot),
                    )
                )
            db_duration = (time.monotonic() - db_t0) * 1000

        result = IncomeResponse(
            months_count=months_val,
            monthly_totals=monthly_totals,
            recent_salary_credits=salary_credits,
        )
        validate_agent_dto(result, cid=cid)
        log_audit_event(
            cid=cid,
            tool="get_income_and_salary",
            principal=self.principal,
            duration_ms=(time.monotonic() - t0) * 1000,
            db_ms=db_duration,
            items_count=len(monthly_totals),
        )
        return result

    # -------------------------------------------------------------------------
    # 7. get_cash_flow_trends
    # -------------------------------------------------------------------------
    def get_cash_flow_trends(self, months: int = 6) -> CashFlowResponse:
        """Report multi-month cash flow trajectory comparing spending vs income."""
        self._check_rate_limit()
        cid = generate_correlation_id()
        months_val = validate_months_arg(months)

        t0 = time.monotonic()
        with get_readonly_session(self.settings) as session:
            db_t0 = time.monotonic()
            raw_trends = financial_trends(session, months=months_val)
            db_duration = (time.monotonic() - db_t0) * 1000

        points = [
            CashFlowTrendItem(
                month=f"{p['year']:04d}-{p['month']:02d}",
                label=p.get("label", ""),
                spent=money_from_decimal(p.get("spent")),
                income=money_from_decimal(p.get("income")),
                net_cash_flow=money_from_decimal(p.get("net_cash_flow")),
            )
            for p in raw_trends.get("points", [])
        ]

        result = CashFlowResponse(
            currency="INR",
            points=points,
        )
        validate_agent_dto(result, cid=cid)
        log_audit_event(
            cid=cid,
            tool="get_cash_flow_trends",
            principal=self.principal,
            duration_ms=(time.monotonic() - t0) * 1000,
            db_ms=db_duration,
            items_count=len(points),
        )
        return result

    # -------------------------------------------------------------------------
    # 8. list_budget_categories
    # -------------------------------------------------------------------------
    def list_budget_categories(self) -> BudgetTaxonomyResponse:
        """List authoritative budget category taxonomy configured in MyMonee."""
        self._check_rate_limit()
        cid = generate_correlation_id()

        t0 = time.monotonic()
        with get_readonly_session(self.settings) as session:
            db_t0 = time.monotonic()
            cats_db = list_categories(session)
            db_duration = (time.monotonic() - db_t0) * 1000

        categories = [
            CategoryTaxonomyItem(
                name=c["name"],
                slug=c["slug"],
                subcategories=[
                    SubcategoryTaxonomyItem(name=s["name"], slug=s["slug"])
                    for s in c.get("subcategories", [])
                ],
            )
            for c in cats_db
        ]

        result = BudgetTaxonomyResponse(categories=categories)
        validate_agent_dto(result, cid=cid)
        log_audit_event(
            cid=cid,
            tool="list_budget_categories",
            principal=self.principal,
            duration_ms=(time.monotonic() - t0) * 1000,
            db_ms=db_duration,
            items_count=len(categories),
        )
        return result

    # -------------------------------------------------------------------------
    # 9. get_agent_capabilities
    # -------------------------------------------------------------------------
    def get_agent_capabilities(self) -> AgentCapabilitiesResponse:
        """Return contract metadata and supported capability list."""
        self._check_rate_limit()
        cid = generate_correlation_id()

        from mymonee.mcp.capabilities import AGENT_CAPABILITY_NAMES

        result = AgentCapabilitiesResponse(
            agent_api_version="1.0",
            application_version="0.8.0",
            currency="INR",
            capabilities=list(AGENT_CAPABILITY_NAMES),
        )
        validate_agent_dto(result, cid=cid)
        log_audit_event(
            cid=cid,
            tool="get_agent_capabilities",
            principal=self.principal,
            duration_ms=0.5,
        )
        return result

    # -------------------------------------------------------------------------
    # 10. get_unclassified_spends
    # -------------------------------------------------------------------------
    def get_unclassified_spends(
        self,
        limit: int | None = 10,
        cursor: str | None = None,
    ) -> UnclassifiedSpendsResult:
        """List transactions needing user or agent category review."""
        self._check_rate_limit()
        cid = generate_correlation_id()
        safe_limit = validate_limit_arg(limit, default=10, max_limit=Limits.MAX_RESULTS)
        offset = 0
        if cursor:
            try:
                decoded = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("ascii")
                offset = int(decoded.split(":")[-1])
                offset = max(offset, 0)
            except Exception:  # noqa: BLE001
                raise AgentServiceError(
                    ErrorCode.INVALID_ARGUMENT, "Invalid pagination cursor.", cid=cid
                )

        t0 = time.monotonic()
        with get_readonly_session(self.settings) as session:
            db_t0 = time.monotonic()
            raw_res = list_transactions(
                session,
                needs_review=True,
                limit=safe_limit + 1,
                offset=offset,
                sort_by="date",
                sort_dir="desc",
            )
            db_duration = (time.monotonic() - db_t0) * 1000

        raw_items = raw_res.get("items", [])
        total_count = raw_res.get("total", len(raw_items))
        has_more = len(raw_items) > safe_limit
        page_items = raw_items[:safe_limit]

        next_cursor = None
        if has_more:
            next_cursor = base64.urlsafe_b64encode(
                f"unclassified:{offset + safe_limit}".encode("ascii")
            ).decode("ascii")

        items = [
            UnclassifiedTransactionItem(
                public_id=to_public_id("txn", tx["id"], self.principal.profile),
                date=tx["transaction_date"][:10] if tx.get("transaction_date") else "",
                amount=money_from_decimal(tx.get("amount")),
                merchant=sanitize_merchant(tx.get("merchant_raw"), tx.get("merchant_normalized")),
                description=sanitize_description(tx.get("description")),
                payment_method=tx.get("payment_method"),
                account_masked=mask_account(tx.get("account")),
                direction=tx.get("direction", "debit"),
                suggested_category=tx.get("category"),
            )
            for tx in page_items
        ]

        result = UnclassifiedSpendsResult(
            total_count=total_count,
            items=items,
            has_more=has_more,
            next_cursor=next_cursor,
        )
        validate_agent_dto(result, cid=cid)
        log_audit_event(
            cid=cid,
            tool="get_unclassified_spends",
            principal=self.principal,
            duration_ms=(time.monotonic() - t0) * 1000,
            db_ms=db_duration,
            items_count=len(items),
        )
        return result

    # -------------------------------------------------------------------------
    # 11. classify_transaction
    # -------------------------------------------------------------------------
    def classify_transaction(
        self,
        transaction_id: str,
        category: str,
        subcategory: str | None = None,
        create_rule: bool = True,
        apply_to_past: bool = False,
        reasoning: str | None = None,
    ) -> ClassifyTransactionResult:
        """Classify an unreviewed transaction and optionally persist a merchant rule."""
        self._check_rate_limit()
        cid = generate_correlation_id()
        t0 = time.monotonic()

        # 1. Resolve opaque public ID to internal UUID
        try:
            internal_tx_id = from_public_id("txn", transaction_id.strip(), self.principal.profile)
        except ValueError as err:
            raise AgentServiceError(
                ErrorCode.INVALID_ARGUMENT,
                f"Invalid transaction identifier '{transaction_id}'. Please retrieve a valid ID via get_unclassified_spends.",
                cid=cid,
            ) from err

        category_clean = category.strip()
        subcategory_clean = subcategory.strip() if subcategory else None

        # 2. Open dedicated short-lived writable session for classification
        from mymonee.db.models import Category as CatModel
        from mymonee.db.models import Subcategory as SubCatModel
        from mymonee.db.session import get_session_factory
        from mymonee.services.transactions import classify_transaction as core_classify

        SessionFactory = get_session_factory(self.settings)
        with SessionFactory() as session:
            # Resolve category by name or slug
            matched_cat = session.scalar(
                select(CatModel).where(func.lower(CatModel.name) == category_clean.lower())
            )
            if not matched_cat:
                matched_cat = session.scalar(
                    select(CatModel).where(func.lower(CatModel.slug) == category_clean.lower())
                )

            if not matched_cat:
                raise AgentServiceError(
                    ErrorCode.INVALID_ARGUMENT,
                    f"Unknown category '{category_clean}'. Use list_budget_categories to view valid categories.",
                    cid=cid,
                )

            # Resolve subcategory if provided
            matched_sub = None
            if subcategory_clean:
                matched_sub = session.scalar(
                    select(SubCatModel).where(
                        SubCatModel.category_id == matched_cat.id,
                        func.lower(SubCatModel.name) == subcategory_clean.lower(),
                    )
                )
                if not matched_sub:
                    matched_sub = session.scalar(
                        select(SubCatModel).where(
                            SubCatModel.category_id == matched_cat.id,
                            func.lower(SubCatModel.slug) == subcategory_clean.lower(),
                        )
                    )
                if not matched_sub:
                    raise AgentServiceError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"Unknown or mismatched subcategory '{subcategory_clean}' for category '{matched_cat.name}'.",
                        cid=cid,
                    )

            # Check if transaction exists
            tx = session.get(Transaction, internal_tx_id)
            if not tx:
                raise AgentServiceError(
                    ErrorCode.NOT_FOUND,
                    f"Transaction '{transaction_id}' was not found in the ledger.",
                    cid=cid,
                )

            # Count past candidates if apply_to_past is requested
            backfilled_count = 0
            if apply_to_past and tx.merchant_name:
                past_candidates = session.scalars(
                    select(Transaction).where(
                        Transaction.merchant_name == tx.merchant_name,
                        Transaction.id != tx.id,
                        Transaction.user_verified.is_(False),
                    )
                ).all()
                backfilled_count = len(past_candidates)

            # Execute authoritative domain classification
            try:
                updated_tx = core_classify(
                    session,
                    internal_tx_id,
                    category_id=matched_cat.id,
                    subcategory_id=matched_sub.id if matched_sub else None,
                    create_rule=create_rule,
                    apply_to_past=apply_to_past,
                )
                session.commit()
            except Exception as err:
                session.rollback()
                logger.exception("Failed to classify transaction %s", internal_tx_id)
                raise AgentServiceError(
                    ErrorCode.INTERNAL_ERROR,
                    f"Failed to execute classification: {err}",
                    cid=cid,
                ) from err

            msg = (
                f"Successfully classified transaction as '{matched_cat.name}'"
                f"{f' > {matched_sub.name}' if matched_sub else ''}."
            )
            if create_rule:
                msg += " Created persistent merchant rule."
            if apply_to_past and backfilled_count > 0:
                merchant_display = (
                    updated_tx.merchant_normalized or updated_tx.merchant_raw or "merchant"
                )
                msg += f" Backfilled {backfilled_count} past transactions for '{merchant_display}'."

            result = ClassifyTransactionResult(
                public_id=transaction_id,
                status="classified",
                category=matched_cat.name,
                category_slug=matched_cat.slug,
                subcategory=matched_sub.name if matched_sub else None,
                subcategory_slug=matched_sub.slug if matched_sub else None,
                rule_created=create_rule,
                backfilled_count=backfilled_count,
                message=msg,
            )

        validate_agent_dto(result, cid=cid)
        log_audit_event(
            cid=cid,
            tool="classify_transaction",
            principal=self.principal,
            duration_ms=(time.monotonic() - t0) * 1000,
            outcome="classified",
            items_count=1 + backfilled_count,
        )
        return result
