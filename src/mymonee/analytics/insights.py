"""Deterministic rule-based category intelligence and insights engine."""

from __future__ import annotations

from typing import Any


def generate_category_insights(
    category_name: str,
    summary: dict[str, Any],
    subcategories: list[dict[str, Any]],
    merchants: list[dict[str, Any]],
    trend: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Generate deterministic, explainable financial insights for a category."""
    insights: list[dict[str, Any]] = []

    period_total = summary.get("period_total_spend", 0.0)
    current_month_spend = summary.get("current_month_spend", 0.0)
    avg_ticket = summary.get("avg_ticket", 0.0)
    median_ticket = summary.get("median_ticket", 0.0)

    # 1. Subcategory MoM shift detection (biggest gainer / dropper)
    active_subs_with_mom = [
        s for s in subcategories if s.get("mom_change_pct") is not None and s.get("current_month_spend", 0) > 0
    ]
    if active_subs_with_mom:
        # Find subcategory with largest positive shift
        largest_gainer = max(active_subs_with_mom, key=lambda s: s.get("mom_change_pct", 0))
        if (largest_gainer.get("mom_change_pct") or 0) >= 15.0:
            pct = largest_gainer["mom_change_pct"]
            spend_cur = largest_gainer.get("current_month_spend", 0)
            insights.append(
                {
                    "type": "subcategory_shift",
                    "severity": "info",
                    "title": f"{largest_gainer['name']} increased MoM",
                    "message": f"{largest_gainer['name']} spending rose {pct:.1f}% this month ({spend_cur:,.0f} spent).",
                }
            )

        # Find subcategory with largest drop
        largest_dropper = min(active_subs_with_mom, key=lambda s: s.get("mom_change_pct", 0))
        if (largest_dropper.get("mom_change_pct") or 0) <= -15.0 and largest_dropper != largest_gainer:
            pct = abs(largest_dropper["mom_change_pct"])
            insights.append(
                {
                    "type": "subcategory_reduction",
                    "severity": "positive",
                    "title": f"{largest_dropper['name']} decreased MoM",
                    "message": f"{largest_dropper['name']} spending dropped {pct:.1f}% vs last month.",
                }
            )

    # 2. Top Merchant Concentration analysis
    if merchants and period_total > 0:
        top_merchant = merchants[0]
        top_share = top_merchant.get("share_of_category", 0.0)
        if top_share >= 0.20:
            insights.append(
                {
                    "type": "merchant_concentration",
                    "severity": "info" if top_share < 0.40 else "warning",
                    "title": f"High Concentration in {top_merchant['name']}",
                    "message": f"{top_merchant['name']} accounts for {top_share * 100:.1f}% of all {category_name} spend in this period.",
                }
            )

    # 3. Trajectory vs 3-Month Rolling Average
    if len(trend) >= 3:
        recent_totals = [m.get("total", 0.0) for m in trend[-4:-1]]  # previous 3 months
        if recent_totals and sum(recent_totals) > 0:
            rolling_avg = sum(recent_totals) / len(recent_totals)
            if current_month_spend > 0 and rolling_avg > 0:
                diff_pct = ((current_month_spend - rolling_avg) / rolling_avg) * 100.0
                if diff_pct >= 20.0:
                    insights.append(
                        {
                            "type": "trajectory_spike",
                            "severity": "warning",
                            "title": "Above 3-Month Average",
                            "message": f"{category_name} spending this month is {diff_pct:.1f}% above your 3-month trailing average.",
                        }
                    )
                elif diff_pct <= -20.0:
                    insights.append(
                        {
                            "type": "trajectory_savings",
                            "severity": "positive",
                            "title": "Below 3-Month Average",
                            "message": f"{category_name} spending this month is {abs(diff_pct):.1f}% below your 3-month trailing average.",
                        }
                    )

    # 4. Ticket Size Dispersion (Skew between Average vs Median)
    if avg_ticket > 0 and median_ticket > 0 and avg_ticket >= 1.8 * median_ticket:
        insights.append(
            {
                "type": "ticket_dispersion",
                "severity": "info",
                "title": "High Ticket Variance",
                "message": f"Average ticket size (₹{avg_ticket:,.0f}) is skewed by larger transactions; your median transaction is ₹{median_ticket:,.0f}.",
            }
        )

    return insights[:4]
