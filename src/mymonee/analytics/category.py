"""Category deep dive analytics aggregation engine."""

from __future__ import annotations

from typing import Any
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from mymonee.analytics.common import (
    calculate_delta_pct,
    calculate_median,
    calculate_rolling_average,
    resolve_period,
)
from mymonee.analytics.insights import generate_category_insights
from mymonee.analytics.queries import (
    query_category_merchants,
    query_category_spend_and_count,
    query_category_transaction_amounts,
    query_subcategory_monthly_series,
    query_subcategory_period_totals,
    query_total_living_spend,
)
from mymonee.db.models import Category, Subcategory


def get_category_analytics(
    session: Session,
    category_id: str,
    *,
    range_str: str = "6m",
    year: int | None = None,
    month: int | None = None,
) -> dict[str, Any]:
    """Assemble a comprehensive, ledger-grounded deep dive dataset for a specific category."""
    category = session.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")

    period = resolve_period(range_str=range_str, year=year, month=month)

    # 1. Category Period Summary & Invariant Aggregates
    period_spend, period_tx_count = query_category_spend_and_count(
        session, category.id, period["start"], period["end"]
    )
    prev_period_spend, _ = query_category_spend_and_count(
        session, category.id, period["comparison_start"], period["comparison_end"]
    )
    cur_month_spend, _ = query_category_spend_and_count(
        session, category.id, period["cur_month_start"], period["cur_month_end"]
    )
    prev_month_spend, _ = query_category_spend_and_count(
        session, category.id, period["prev_month_start"], period["prev_month_end"]
    )

    total_living_period_spend = query_total_living_spend(
        session, period["start"], period["end"]
    )
    share_of_living = (
        round(period_spend / total_living_period_spend, 4)
        if total_living_period_spend > 0
        else 0.0
    )

    all_tx_amounts = query_category_transaction_amounts(
        session, category.id, period["start"], period["end"]
    )
    avg_ticket = round(period_spend / period_tx_count, 2) if period_tx_count > 0 else 0.0
    median_ticket = calculate_median(all_tx_amounts)

    summary = {
        "period_total_spend": round(period_spend, 2),
        "previous_period_spend": round(prev_period_spend, 2),
        "period_change_pct": calculate_delta_pct(period_spend, prev_period_spend),
        "current_month_spend": round(cur_month_spend, 2),
        "previous_month_spend": round(prev_month_spend, 2),
        "current_month_mom_change_pct": calculate_delta_pct(cur_month_spend, prev_month_spend),
        "transaction_count": period_tx_count,
        "avg_ticket": avg_ticket,
        "median_ticket": median_ticket,
        "share_of_living_spend": share_of_living,
    }

    # 2. Subcategories Metadata Map
    subcategories_db = session.scalars(
        select(Subcategory).where(Subcategory.category_id == category.id).order_by(Subcategory.sort_order.asc())
    ).all()
    subcat_map = {s.id: s for s in subcategories_db}

    # 3. Multi-Month Trend Breakdown
    raw_monthly_series = query_subcategory_monthly_series(
        session, category.id, period["start"], period["end"]
    )

    # Index by (month_str, subcategory_id)
    monthly_sub_index: dict[tuple[str, str | None], dict[str, Any]] = {}
    for item in raw_monthly_series:
        monthly_sub_index[(item["month_str"], item["subcategory_id"])] = item

    trend: list[dict[str, Any]] = []
    # Track monthly spend history for each subcategory for rolling 3M averages
    subcat_monthly_spends: dict[str | None, list[float]] = {s.id: [] for s in subcategories_db}
    subcat_monthly_spends[None] = []

    for y, m in period["month_buckets"]:
        m_str = f"{y:04d}-{m:02d}"
        month_total = 0.0
        month_subs: list[dict[str, Any]] = []

        # Known subcategories
        for sub in subcategories_db:
            data = monthly_sub_index.get((m_str, sub.id))
            spend = data["spend"] if data else 0.0
            count = data["tx_count"] if data else 0
            month_total += spend
            subcat_monthly_spends[sub.id].append(spend)
            month_subs.append(
                {
                    "id": sub.id,
                    "name": sub.name,
                    "slug": sub.slug,
                    "spend": round(spend, 2),
                    "count": count,
                }
            )

        # Unassigned / General subcategory
        unassigned_data = monthly_sub_index.get((m_str, None))
        if unassigned_data:
            unassigned_spend = unassigned_data["spend"]
            month_total += unassigned_spend
            subcat_monthly_spends[None].append(unassigned_spend)
            month_subs.append(
                {
                    "id": "unassigned",
                    "name": "General / Other",
                    "slug": "general",
                    "spend": round(unassigned_spend, 2),
                    "count": unassigned_data["tx_count"],
                }
            )
        else:
            subcat_monthly_spends[None].append(0.0)

        trend.append(
            {
                "month": m_str,
                "year": y,
                "month_num": m,
                "total": round(month_total, 2),
                "subcategories": month_subs,
            }
        )

    # 4. Subcategory Summary & MoM Calculations
    raw_sub_totals = query_subcategory_period_totals(
        session, category.id, period["start"], period["end"]
    )
    sub_total_map = {item["subcategory_id"]: item for item in raw_sub_totals}

    cur_sub_totals = query_subcategory_period_totals(
        session, category.id, period["cur_month_start"], period["cur_month_end"]
    )
    cur_sub_map = {item["subcategory_id"]: item["spend"] for item in cur_sub_totals}

    prev_sub_totals = query_subcategory_period_totals(
        session, category.id, period["prev_month_start"], period["prev_month_end"]
    )
    prev_sub_map = {item["subcategory_id"]: item["spend"] for item in prev_sub_totals}

    subcategories_summary: list[dict[str, Any]] = []
    for sub in subcategories_db:
        period_data = sub_total_map.get(sub.id, {"spend": 0.0, "tx_count": 0})
        s_spend = period_data["spend"]
        s_count = period_data["tx_count"]
        s_cur = cur_sub_map.get(sub.id, 0.0)
        s_prev = prev_sub_map.get(sub.id, 0.0)
        history = subcat_monthly_spends.get(sub.id, [])

        subcategories_summary.append(
            {
                "id": sub.id,
                "name": sub.name,
                "slug": sub.slug,
                "spend": round(s_spend, 2),
                "share_of_category": round(s_spend / period_spend, 4) if period_spend > 0 else 0.0,
                "transaction_count": s_count,
                "avg_ticket": round(s_spend / s_count, 2) if s_count > 0 else 0.0,
                "current_month_spend": round(s_cur, 2),
                "previous_month_spend": round(s_prev, 2),
                "mom_change_pct": calculate_delta_pct(s_cur, s_prev),
                "rolling_3m_avg": calculate_rolling_average(history, window=3),
            }
        )

    # Unassigned subcategory if spend exists
    if None in sub_total_map:
        u_data = sub_total_map[None]
        u_spend = u_data["spend"]
        u_count = u_data["tx_count"]
        u_cur = cur_sub_map.get(None, 0.0)
        u_prev = prev_sub_map.get(None, 0.0)
        u_history = subcat_monthly_spends.get(None, [])
        subcategories_summary.append(
            {
                "id": "unassigned",
                "name": "General / Other",
                "slug": "general",
                "spend": round(u_spend, 2),
                "share_of_category": round(u_spend / period_spend, 4) if period_spend > 0 else 0.0,
                "transaction_count": u_count,
                "avg_ticket": round(u_spend / u_count, 2) if u_count > 0 else 0.0,
                "current_month_spend": round(u_cur, 2),
                "previous_month_spend": round(u_prev, 2),
                "mom_change_pct": calculate_delta_pct(u_cur, u_prev),
                "rolling_3m_avg": calculate_rolling_average(u_history, window=3),
            }
        )

    # Sort subcategories by period spend descending
    subcategories_summary.sort(key=lambda s: s["spend"], reverse=True)

    # 5. Top Merchants & Concentration Metrics
    merchants_raw = query_category_merchants(
        session, category.id, period["start"], period["end"], limit=15
    )
    merchants: list[dict[str, Any]] = []
    for m in merchants_raw:
        m_spend = m["spend"]
        m_count = m["tx_count"]
        merchants.append(
            {
                "merchant_id": m["merchant_id"],
                "name": m["name"],
                "spend": round(m_spend, 2),
                "transaction_count": m_count,
                "share_of_category": round(m_spend / period_spend, 4) if period_spend > 0 else 0.0,
                "avg_ticket": round(m_spend / m_count, 2) if m_count > 0 else 0.0,
            }
        )

    top_1_spend = merchants[0]["spend"] if len(merchants) >= 1 else 0.0
    top_3_spend = sum(m["spend"] for m in merchants[:3])
    top_5_spend = sum(m["spend"] for m in merchants[:5])

    concentration = {
        "top_1_share": round(top_1_spend / period_spend, 4) if period_spend > 0 else 0.0,
        "top_3_share": round(top_3_spend / period_spend, 4) if period_spend > 0 else 0.0,
        "top_5_share": round(top_5_spend / period_spend, 4) if period_spend > 0 else 0.0,
    }

    # 6. Deterministic Insights
    insights = generate_category_insights(
        category.name, summary, subcategories_summary, merchants, trend
    )

    return {
        "category": {
            "id": category.id,
            "name": category.name,
            "slug": category.slug,
            "expense_type": category.expense_type,
        },
        "period": {
            "start": period["start"].isoformat(),
            "end": period["end"].isoformat(),
            "months": period["months_count"],
            "year": period["year"],
            "month": period["month"],
            "range": period["range"],
        },
        "comparison": {
            "type": "previous_period",
            "start": period["comparison_start"].isoformat(),
            "end": period["comparison_end"].isoformat(),
        },
        "summary": summary,
        "trend": trend,
        "subcategories": subcategories_summary,
        "merchants": merchants,
        "concentration": concentration,
        "insights": insights,
    }
