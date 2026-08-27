import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, type Overview, type FinancialTrends } from "../api";
import FinancialTrendModal, { type TrendMetricType } from "../components/FinancialTrendModal";
import MonthStrip from "../components/MonthStrip";
import LedgerIntelligencePanel from "../components/LedgerIntelligencePanel";
import AccountBadge from "../components/common/AccountBadge";
import { formatMoney, formatCompactMoney, formatLakhOrK, formatDate } from "../format";


function getHumanSummary(overview: Overview, date: { year: number; month: number }) {
  const spentStr = formatLakhOrK(overview.summary.spent, overview.currency);
  const incomeStr = formatLakhOrK(overview.summary.income, overview.currency);
  const netAbsStr = formatLakhOrK(Math.abs(overview.summary.net_cash_flow), overview.currency);
  const prevMonthName = new Date(date.year, date.month - 2, 1).toLocaleDateString("en-GB", { month: "short" });

  let diffText = "";
  if (overview.month_comparison.spent_change_pct != null) {
    const isLess = overview.month_comparison.spent_change_pct < 0;
    const absPct = Math.abs(overview.month_comparison.spent_change_pct).toFixed(1);
    diffText = `, ${absPct}% ${isLess ? "less" : "more"} than ${prevMonthName}`;
  }

  const consumerSpent = overview.summary.consumer_spent != null ? overview.summary.consumer_spent : overview.summary.spent;
  const commitmentsSpent = overview.summary.commitments_spent || 0;

  let compositionText = "";
  if (commitmentsSpent > 0 && consumerSpent > 0) {
    const consStr = formatLakhOrK(consumerSpent, overview.currency);
    const commStr = formatLakhOrK(commitmentsSpent, overview.currency);
    compositionText = ` (${consStr} living expenses + ${commStr} loan commitments)`;
  }

  const flowType = overview.summary.net_cash_flow >= 0 ? "positive cash flow" : "net deficit";
  const flowSign = overview.summary.net_cash_flow >= 0 ? "+" : "-";

  return `Income was ${incomeStr}, with ${spentStr} spent this month${compositionText}${diffText}, leaving a ${flowType} of ${flowSign}${netAbsStr}.`;
}

export default function OverviewPage() {
  const navigate = useNavigate();
  const [date, setDate] = useState(() => {
    const now = new Date();
    return { year: now.getFullYear(), month: now.getMonth() + 1 };
  });
  const [overview, setOverview] = useState<Overview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAllLiving, setShowAllLiving] = useState(false);
  const [hoveredDay, setHoveredDay] = useState<{ day: number; dateStr: string; spent: number; count: number } | null>(null);

  // Financial trend modal state (Spent, Income, Net Cash Flow)
  const [trendModalOpen, setTrendModalOpen] = useState(false);
  const [trendMetric, setTrendMetric] = useState<TrendMetricType>("spent");
  const [financialTrends, setFinancialTrends] = useState<FinancialTrends | null>(null);
  const [trendsLoading, setTrendsLoading] = useState(false);
  const [trendsError, setTrendsError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setShowAllLiving(false);

    api
      .overview(date.year, date.month)
      .then((o) => {
        if (cancelled) return;
        setOverview(o);
        setError(null);
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [date.year, date.month]);


  function openTrend(metric: TrendMetricType) {
    setTrendMetric(metric);
    setTrendModalOpen(true);
    setTrendsLoading(true);
    setTrendsError(null);
    api
      .financialTrends(12, date.year, date.month)
      .then((t) => {
        setFinancialTrends(t);
      })
      .catch((err: Error) => {
        setTrendsError(err.message);
      })
      .finally(() => {
        setTrendsLoading(false);
      });
  }


  const daysInMonth = new Date(date.year, date.month, 0).getDate();

  const dailyMap = useMemo(() => {
    const map = new Map<string, number>();
    if (overview?.daily_spending) {
      for (const d of overview.daily_spending) {
        map.set(d.date, d.spent);
      }
    }
    return map;
  }, [overview]);

  const dailyCountMap = useMemo(() => {
    const map = new Map<string, number>();
    if (overview?.daily_spending) {
      for (const d of overview.daily_spending) {
        map.set(d.date, d.count || (d.spent > 0 ? 1 : 0));
      }
    }
    return map;
  }, [overview]);

  const fullDailyData = useMemo(() => {
    const data: Array<{ day: number; dateStr: string; spent: number; count: number }> = [];
    for (let day = 1; day <= daysInMonth; day++) {
      const padM = String(date.month).padStart(2, "0");
      const padD = String(day).padStart(2, "0");
      const dateStr = `${date.year}-${padM}-${padD}`;
      data.push({
        day,
        dateStr,
        spent: dailyMap.get(dateStr) || 0,
        count: dailyCountMap.get(dateStr) || 0,
      });
    }
    return data;
  }, [daysInMonth, date.year, date.month, dailyMap, dailyCountMap]);

  type CategoryBreakdownItem = Overview["category_breakdown"][number];

  const { biggestIncrease, biggestDecrease, maxInc, maxDec } = useMemo<{
    biggestIncrease: CategoryBreakdownItem | null;
    biggestDecrease: CategoryBreakdownItem | null;
    maxInc: number;
    maxDec: number;
  }>(() => {
    let inc: CategoryBreakdownItem | null = null;
    let dec: CategoryBreakdownItem | null = null;
    let maxI = 0;
    let maxD = 0;

    if (overview?.category_breakdown) {
      overview.category_breakdown.forEach((c) => {
        const diff = c.total - (c.previous_total || 0);
        if (diff > maxI) {
          maxI = diff;
          inc = c;
        }
        if (diff < maxD) {
          maxD = diff;
          dec = c;
        }
      });
    }
    return { biggestIncrease: inc, biggestDecrease: dec, maxInc: maxI, maxDec: maxD };
  }, [overview?.category_breakdown]);

  if (error) return <p className="error">Could not load overview: {error}</p>;
  if (!overview && loading) return <p className="empty">Loading monthly analysis…</p>;
  if (!overview) return null;

  const maxDaily = fullDailyData.length > 0 ? Math.max(1, ...fullDailyData.map((d) => d.spent)) : 1;
  const avgDaily = daysInMonth > 0 ? overview.summary.spent / daysInMonth : 0;

  const spendingDiff = overview.summary.spent - overview.month_comparison.previous_spent;
  const incomeDiff = overview.summary.income - overview.month_comparison.previous_income;

  // Split Living Expenses vs Financial Commitments
  const commitmentCategories = overview.category_breakdown.filter((c) =>
    ["essential", "financial", "commitment"].includes(c.expense_type || "") ||
    ["loans", "loan", "fees & interest", "fees-interest", "emi", "family"].includes(c.category.toLowerCase())
  );
  const livingCategories = overview.category_breakdown.filter((c) =>
    !commitmentCategories.some((cc) => cc.category_id === c.category_id) && c.total > 0
  );

  const livingTotal = livingCategories.reduce((acc, c) => acc + c.total, 0);
  const commitmentTotal = commitmentCategories.reduce((acc, c) => acc + c.total, 0);

  function renderCategoryList(cats: Overview["category_breakdown"], totalSum: number, isLivingGroup = false) {
    if (cats.length === 0) return <p className="empty" style={{ fontSize: "0.85rem", padding: "8px 0" }}>None recorded</p>;
    const maxCat = Math.max(1, ...cats.map((c) => c.total));
    const displayCats = isLivingGroup && !showAllLiving ? cats.slice(0, 5) : cats;

    return (
      <div className="category-list">
        {displayCats.map((c) => {
          const groupPct = totalSum > 0 ? (c.total / totalSum) * 100 : 0;
          return (
            <div
              key={c.category_id}
              className="category-row"
              style={{ cursor: "pointer" }}
              title={`View ${c.category} deep dive analytics`}
              onClick={() => {
                navigate(`/analytics/category/${encodeURIComponent(c.category_id)}?year=${date.year}&month=${date.month}&range=6m`);
              }}
            >
              <div className="category-name" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {c.category}
              </div>
              <div className="bar-track">
                <div className="bar-fill" style={{ width: `${Math.min(100, (c.total / maxCat) * 100)}%` }} />
              </div>
              <div className="category-total" style={{ display: "flex", gap: "8px", alignItems: "baseline" }}>
                <span style={{ color: "var(--ink-muted)", fontSize: "0.8rem", fontWeight: 500 }}>
                  {groupPct.toFixed(1)}%
                </span>
                <span>{formatMoney(c.total, overview!.currency)}</span>
              </div>
            </div>
          );
        })}
      </div>
    );
  }

  // Increase/Decrease context helpers
  const prevInc = biggestIncrease ? biggestIncrease.previous_total || 0 : 0;
  const incContext = prevInc === 0 ? "New this month" : `vs ${formatMoney(prevInc, overview.currency)}`;

  const prevDec = biggestDecrease ? biggestDecrease.previous_total || 0 : 0;
  const decPct = prevDec > 0 && biggestDecrease ? Math.round(((prevDec - biggestDecrease.total) / prevDec) * 100) : null;
  const decContext = decPct != null ? `↓ ${decPct}% vs last month` : `vs ${formatMoney(prevDec, overview.currency)}`;

  const monthParamFrom = `${date.year}-${String(date.month).padStart(2, "0")}-01`;
  const monthParamTo = `${date.year}-${String(date.month).padStart(2, "0")}-${String(daysInMonth).padStart(2, "0")}`;

  return (
    <div className="overview-page" style={{ animation: "rise 0.4s ease both", maxWidth: 1060, margin: "0 auto" }}>
      {/* ───────────────────────────────────────────────────────────── */}
      {/* ZONE 1: MONTH SUMMARY & FLOW                                  */}
      {/* ───────────────────────────────────────────────────────────── */}

      {/* Month Strip Controls */}
      <header
        className="overview-header"
        style={{
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
          marginBottom: "16px",
        }}
      >
        <MonthStrip
          year={date.year}
          month={date.month}
          onChange={(y, m) => setDate({ year: y, month: m })}
          disabled={loading}
        />
      </header>

      {/* Human Deterministic Summary Sentence */}
      <div
        style={{
          fontSize: "0.93rem",
          color: "var(--ink-muted)",
          lineHeight: 1.5,
          marginBottom: "18px",
          padding: "10px 14px",
          background: "var(--surface)",
          border: "1px solid var(--line)",
          borderRadius: "var(--radius)",
        }}
      >
        <span style={{ color: "var(--ink)", fontWeight: 500 }}>
          {getHumanSummary(overview, date)}
        </span>
      </div>

      {/* Needs Review / Data Quality Banner (if any) */}
      {overview.review.needs_review_count > 0 && (
        <div className="attention-banner" role="alert" style={{ marginBottom: "16px" }}>
          <div className="attention-banner-content">
            <span className="attention-banner-icon" aria-hidden="true">⚠</span>
            <span>
              <strong>{overview.review.needs_review_count} transactions</strong> (
              {formatMoney(overview.review.needs_review_amount, overview.currency)}) need classification
            </span>
          </div>
          <Link to={`/review?date_from=${monthParamFrom}&date_to=${monthParamTo}`} className="attention-banner-link">
            Review →
          </Link>
        </div>
      )}

      {/* Ledger Intelligence & Anomaly Signals Panel */}
      <LedgerIntelligencePanel
        onTransactionClick={(txId) => {
          navigate(`/transactions?search=${encodeURIComponent(txId)}`);
        }}
      />

      {/* Primary Financial Flow KPI Strip (Clean, Clickable for 6M trend, No TREND ↗ label) */}
      <section className="metrics" aria-label="Monthly financial flow" style={{ marginBottom: "12px" }}>
        <button
          type="button"
          className="metric-button"
          onClick={() => openTrend("income")}
          title="Click to view 6-month income trend"
          aria-label="Income, click to view 6-month trend"
        >
          <div className="metric-label">Income</div>
          <div className="metric-value" style={{ color: "var(--credit)" }}>
            {formatMoney(overview.summary.income, overview.currency)}
          </div>
          <div className="metric-hint">
            {overview.month_comparison.income_change_pct != null ? (
              <span className={overview.month_comparison.income_change_pct >= 0 ? "metric-delta up" : "metric-delta down"}>
                {overview.month_comparison.income_change_pct >= 0 ? "↑" : "↓"}{" "}
                {Math.abs(overview.month_comparison.income_change_pct).toFixed(1)}% vs last month
              </span>
            ) : (
              "vs last month —"
            )}
          </div>
        </button>

        <button
          type="button"
          className="metric-button"
          onClick={() => openTrend("cash_flow")}
          title="Click to view 6-month net cash flow trend"
          aria-label="Net Cash Flow, click to view 6-month trend"
        >
          <div className="metric-label">Net Cash Flow</div>
          <div
            className="metric-value"
            style={{
              color: overview.summary.net_cash_flow >= 0 ? "var(--credit)" : "var(--debit)",
            }}
          >
            {overview.summary.net_cash_flow >= 0 ? "+" : ""}
            {formatMoney(overview.summary.net_cash_flow, overview.currency)}
          </div>
          <div className="metric-hint">Income − spending</div>
        </button>

        <button
          type="button"
          className="metric-button"
          onClick={() => openTrend("spent")}
          title="Click to view 6-month spending trend"
          aria-label="Total Spent, click to view 6-month trend"
        >
          <div className="metric-label">Total Spent</div>
          <div className="metric-value">{formatMoney(overview.summary.spent, overview.currency)}</div>
          <div className="metric-hint">
            {overview.month_comparison.spent_change_pct != null ? (
              <span className={overview.month_comparison.spent_change_pct > 0 ? "metric-delta down" : "metric-delta up"}>
                {overview.month_comparison.spent_change_pct > 0 ? "↑" : "↓"}{" "}
                {Math.abs(overview.month_comparison.spent_change_pct).toFixed(1)}% vs last month
              </span>
            ) : (
              "vs last month —"
            )}
          </div>
        </button>
      </section>

      {/* Inline Reconciled Transactions Volume Sub-line */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "8px",
          fontSize: "0.84rem",
          color: "var(--ink-muted)",
          padding: "8px 12px",
          background: "var(--surface-muted, rgba(0,0,0,0.02))",
          borderRadius: "var(--radius-sm)",
          marginBottom: "28px",
          border: "1px solid var(--line)",
        }}
      >
        <div>
          <strong style={{ color: "var(--ink)" }}>{overview.summary.transaction_count} expenses recorded</strong>
          {" · "}
          <span>{formatMoney(overview.summary.spent, overview.currency)} out</span>
          {overview.summary.excluded_count ? (
            <span style={{ opacity: 0.85 }}>
              {" · "}
              {overview.summary.excluded_count} transfers & alerts filtered
            </span>
          ) : null}
        </div>
        <Link
          to={`/transactions?date_from=${monthParamFrom}&date_to=${monthParamTo}`}
          style={{ color: "var(--accent)", textDecoration: "none", fontWeight: 600, fontSize: "0.82rem" }}
        >
          View all transactions →
        </Link>
      </div>

      {/* ───────────────────────────────────────────────────────────── */}
      {/* ZONE 2: SPENDING ANALYSIS (Breakdown & Daily Pattern)         */}
      {/* ───────────────────────────────────────────────────────────── */}
      <div className="grid-2" style={{ marginBottom: "28px", alignItems: "start" }}>
        {/* Left: Spending Breakdown (Living Expenses vs Financial Commitments) */}
        <section className="section" style={{ height: "100%" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "12px" }}>
            <h2 style={{ margin: 0 }}>Spending Breakdown</h2>
            <span style={{ fontSize: "0.82rem", color: "var(--ink-muted)" }}>
              {formatMoney(overview.summary.spent, overview.currency)} total
            </span>
          </div>

          {overview.category_breakdown.length === 0 ? (
            <p className="empty">No spending recorded for this month.</p>
          ) : (
            <div>
              {/* Group 1: Living / Consumer Expenses */}
              <div style={{ marginBottom: "20px" }}>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    fontSize: "0.72rem",
                    fontWeight: 700,
                    letterSpacing: "0.08em",
                    textTransform: "uppercase",
                    color: "var(--ink-muted)",
                    marginBottom: "10px",
                    paddingBottom: "4px",
                    borderBottom: "1px solid var(--line)",
                  }}
                >
                  <span>Consumer & Living Spending</span>
                  <span>{formatMoney(livingTotal, overview.currency)}</span>
                </div>
                {renderCategoryList(livingCategories, livingTotal, true)}
                {livingCategories.length > 5 && (
                  <div style={{ marginTop: "8px" }}>
                    <button
                      type="button"
                      className="btn quiet"
                      onClick={() => setShowAllLiving((prev) => !prev)}
                      style={{ fontSize: "0.8rem", padding: "2px 6px" }}
                    >
                      {showAllLiving ? "Show top living categories ↑" : `View all ${livingCategories.length} categories →`}
                    </button>
                  </div>
                )}
              </div>

              {/* Group 2: Financial Commitments & Loan Obligations */}
              {commitmentCategories.length > 0 && (
                <div>
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      fontSize: "0.72rem",
                      fontWeight: 700,
                      letterSpacing: "0.08em",
                      textTransform: "uppercase",
                      color: "var(--ink-muted)",
                      marginBottom: "10px",
                      paddingBottom: "4px",
                      borderBottom: "1px solid var(--line)",
                    }}
                  >
                    <span>Financial Commitments & Loans</span>
                    <span>{formatMoney(commitmentTotal, overview.currency)}</span>
                  </div>
                  {renderCategoryList(commitmentCategories, commitmentTotal, false)}
                </div>
              )}
            </div>
          )}
        </section>

        {/* Right: Daily Spending Chart with Interactive Tooltip & Click-through */}
        <section className="section" style={{ display: "flex", flexDirection: "column", height: "100%" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "12px" }}>
            <h2 style={{ margin: 0 }}>Daily Spending</h2>
            <div style={{ fontSize: "0.82rem", color: "var(--ink-muted)", textAlign: "right" }}>
              Avg {formatCompactMoney(avgDaily, overview.currency)} / day · Peak {formatCompactMoney(maxDaily, overview.currency)}
            </div>
          </div>

          <div style={{ display: "flex", gap: "8px", height: "200px", marginTop: "8px" }}>
            {/* Y-Axis Scale Column */}
            <div
              style={{
                width: "44px",
                display: "flex",
                flexDirection: "column",
                justifyContent: "space-between",
                alignItems: "flex-end",
                paddingRight: "6px",
                fontSize: "0.72rem",
                color: "var(--ink-muted)",
                userSelect: "none",
                paddingTop: "2px",
                paddingBottom: "2px",
                borderRight: "1px solid var(--line)",
              }}
            >
              <span>{formatCompactMoney(maxDaily, overview.currency)}</span>
              <span>{formatCompactMoney(maxDaily / 2, overview.currency)}</span>
              <span>{formatCompactMoney(0, overview.currency)}</span>
            </div>

            {/* Bars Canvas Container */}
            <div style={{ flex: 1, position: "relative", display: "flex", alignItems: "flex-end", gap: "2px", paddingTop: "8px", paddingBottom: "2px" }}>
              {/* Horizontal Reference Lines */}
              <div style={{ position: "absolute", left: 0, right: 0, top: "2px", borderTop: "1px dashed var(--line)", opacity: 0.6, pointerEvents: "none" }} />
              <div style={{ position: "absolute", left: 0, right: 0, top: "50%", borderTop: "1px dashed var(--line)", opacity: 0.6, pointerEvents: "none" }} />
              <div style={{ position: "absolute", left: 0, right: 0, bottom: "2px", borderTop: "1px solid var(--line)", pointerEvents: "none" }} />

              {/* Subtle Average Reference Line */}
              {avgDaily > 0 && maxDaily > 0 && (
                <div
                  style={{
                    position: "absolute",
                    left: 0,
                    right: 0,
                    bottom: `${Math.min(100, (avgDaily / maxDaily) * 100)}%`,
                    borderTop: "1px dashed var(--accent)",
                    opacity: 0.65,
                    pointerEvents: "none",
                    zIndex: 0,
                  }}
                  title={`Daily average: ${formatMoney(avgDaily, overview.currency)}`}
                />
              )}

              {/* Day Bars */}
              {fullDailyData.map((d) => {
                const heightPct = maxDaily > 0 ? (d.spent / maxDaily) * 100 : 0;
                const hasSpend = d.spent > 0;
                const isHovered = hoveredDay?.day === d.day;
                return (
                  <div
                    key={d.day}
                    onMouseEnter={() => setHoveredDay(d)}
                    onMouseLeave={() => setHoveredDay(null)}
                    onClick={() => {
                      if (hasSpend) {
                        navigate(`/transactions?date_from=${d.dateStr}&date_to=${d.dateStr}`);
                      }
                    }}
                    style={{
                      flex: 1,
                      display: "flex",
                      flexDirection: "column",
                      alignItems: "center",
                      justifyContent: "flex-end",
                      height: "100%",
                      position: "relative",
                      zIndex: isHovered ? 40 : 1,
                      cursor: hasSpend ? "pointer" : "default",
                    }}
                  >
                    {/* Rich Hover Tooltip (Date, Amount, Count) */}
                    {isHovered && hasSpend && (
                      <div
                        style={{
                          position: "absolute",
                          bottom: `calc(${Math.max(6, heightPct)}% + 8px)`,
                          background: "var(--surface)",
                          backgroundColor: "var(--surface)",
                          color: "var(--ink)",
                          border: "1px solid var(--line)",
                          padding: "6px 12px",
                          borderRadius: "var(--radius-md)",
                          fontSize: "0.74rem",
                          fontVariantNumeric: "tabular-nums",
                          whiteSpace: "nowrap",
                          pointerEvents: "none",
                          zIndex: 50,
                          opacity: 1,
                          boxShadow: "0 8px 24px rgba(0, 0, 0, 0.28)",
                          textAlign: "center",
                        }}
                      >
                        <div style={{ fontWeight: 600, color: "var(--ink)" }}>{formatDate(d.dateStr)}</div>
                        <div style={{ fontSize: "0.88rem", fontWeight: 700, color: "var(--accent)", marginTop: 2 }}>
                          {formatMoney(d.spent, overview.currency)}
                        </div>
                        {d.count > 0 && (
                          <div style={{ fontSize: "0.72rem", color: "var(--ink-muted)", marginTop: 2 }}>
                            {d.count} {d.count === 1 ? "transaction" : "transactions"} · click to view
                          </div>
                        )}
                      </div>
                    )}

                    <div
                      style={{
                        width: "100%",
                        height: hasSpend ? `${Math.max(4, heightPct)}%` : "0%",
                        background: isHovered ? "var(--ink)" : "var(--accent)",
                        borderRadius: "2px 2px 0 0",
                        opacity: hasSpend ? (isHovered ? 1 : 0.8) : 0.15,
                        transition: "height 0.2s ease, opacity 0.15s ease, background 0.15s ease",
                      }}
                    />
                  </div>
                );
              })}
            </div>
          </div>

          {/* X Axis Timeline Labels */}
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.72rem", color: "var(--ink-muted)", paddingTop: "6px", marginLeft: "52px" }}>
            <span>Day 1</span>
            <span>Day 7</span>
            <span>Day 14</span>
            <span>Day 21</span>
            <span>Day 28</span>
            <span>Day {daysInMonth}</span>
          </div>
        </section>
      </div>

      {/* Month-over-Month Comparison Strip ("VS LAST MONTH") with Deep Context */}
      <section className="section" style={{ marginBottom: "28px" }}>
        <h2 style={{ marginBottom: "14px" }}>VS LAST MONTH</h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))", gap: "16px" }}>
          <div>
            <div style={{ color: "var(--ink-muted)", fontSize: "0.76rem", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "4px" }}>
              Spending Change
            </div>
            <div style={{ fontSize: "1.08rem", fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>
              <span className={spendingDiff > 0 ? "metric-delta down" : "metric-delta up"}>
                {spendingDiff > 0 ? "+" : ""}
                {formatMoney(spendingDiff, overview.currency)}
              </span>{" "}
              <span style={{ fontSize: "0.82rem", color: "var(--ink-muted)", fontWeight: 400 }}>
                ({overview.month_comparison.spent_change_pct != null ? `${overview.month_comparison.spent_change_pct > 0 ? "↑" : "↓"} ${Math.abs(overview.month_comparison.spent_change_pct).toFixed(1)}%` : "—"})
              </span>
            </div>
          </div>

          <div>
            <div style={{ color: "var(--ink-muted)", fontSize: "0.76rem", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "4px" }}>
              Income Change
            </div>
            <div style={{ fontSize: "1.08rem", fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>
              <span className={incomeDiff >= 0 ? "metric-delta up" : "metric-delta down"}>
                {incomeDiff > 0 ? "+" : ""}
                {formatMoney(incomeDiff, overview.currency)}
              </span>{" "}
              <span style={{ fontSize: "0.82rem", color: "var(--ink-muted)", fontWeight: 400 }}>
                ({overview.month_comparison.income_change_pct != null ? `${overview.month_comparison.income_change_pct >= 0 ? "↑" : "↓"} ${Math.abs(overview.month_comparison.income_change_pct).toFixed(1)}%` : "—"})
              </span>
            </div>
          </div>

          <div>
            <div style={{ color: "var(--ink-muted)", fontSize: "0.76rem", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "4px" }}>
              Largest Increase
            </div>
            <div style={{ fontSize: "0.92rem" }}>
              {biggestIncrease ? (
                <div>
                  <strong style={{ color: "var(--ink)" }}>{biggestIncrease.category}</strong>:{" "}
                  <span className="metric-delta down" style={{ fontVariantNumeric: "tabular-nums" }}>
                    +{formatMoney(maxInc, overview.currency)}
                  </span>
                  <div style={{ fontSize: "0.78rem", color: "var(--ink-muted)", marginTop: 2 }}>{incContext}</div>
                </div>
              ) : (
                <span style={{ color: "var(--ink-muted)" }}>None</span>
              )}
            </div>
          </div>

          <div>
            <div style={{ color: "var(--ink-muted)", fontSize: "0.76rem", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "4px" }}>
              Largest Decrease
            </div>
            <div style={{ fontSize: "0.92rem" }}>
              {biggestDecrease ? (
                <div>
                  <strong style={{ color: "var(--ink)" }}>{biggestDecrease.category}</strong>:{" "}
                  <span className="metric-delta up" style={{ fontVariantNumeric: "tabular-nums" }}>
                    {formatMoney(maxDec, overview.currency)}
                  </span>
                  <div style={{ fontSize: "0.78rem", color: "var(--ink-muted)", marginTop: 2 }}>{decContext}</div>
                </div>
              ) : (
                <span style={{ color: "var(--ink-muted)" }}>None</span>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* ───────────────────────────────────────────────────────────── */}
      {/* ZONE 3: OUTFLOW DETAILS (Merchants, Accounts, Largest TXs)     */}
      {/* ───────────────────────────────────────────────────────────── */}
      <div className="grid-2" style={{ marginBottom: "28px" }}>
        {/* Top Outflows / Payees */}
        <section className="section">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "12px" }}>
            <h2 style={{ margin: 0 }}>Top Outflows</h2>
            <span style={{ fontSize: "0.8rem", color: "var(--ink-muted)" }}>Top payees by volume</span>
          </div>
          {overview.top_merchants.length === 0 ? (
            <p className="empty">No merchants recorded this month.</p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column" }}>
              {overview.top_merchants.slice(0, 5).map((m, i) => (
                <div
                  key={m.merchant || i}
                  className="panel-hover"
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    padding: "9px 6px",
                    borderBottom: "1px solid var(--line)",
                    cursor: "pointer",
                    borderRadius: "var(--radius-sm)",
                  }}
                  title={`View transactions for ${m.merchant || "payee"}`}
                  onClick={() => {
                    navigate(`/transactions?date_from=${monthParamFrom}&date_to=${monthParamTo}&q=${encodeURIComponent(m.merchant || "")}`);
                  }}
                >
                  <div style={{ overflow: "hidden", textOverflow: "ellipsis", paddingRight: "16px" }}>
                    <div style={{ fontWeight: 600, fontSize: "0.92rem" }}>
                      {m.merchant || "Unidentified payee"}
                    </div>
                    <div style={{ fontSize: "0.78rem", color: "var(--ink-muted)", marginTop: 1 }}>
                      {m.count} {m.count === 1 ? "transaction" : "transactions"}
                    </div>
                  </div>
                  <div style={{ fontWeight: 600, textAlign: "right", fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}>
                    {formatMoney(m.total, overview.currency)}
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Payment Methods (Quiet Percentages & Clickable Accounts) */}
        <section className="section">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "12px" }}>
            <h2 style={{ margin: 0 }}>Payment Methods</h2>
            <span style={{ fontSize: "0.8rem", color: "var(--ink-muted)" }}>Distribution of spend</span>
          </div>
          {overview.account_breakdown.length === 0 ? (
            <p className="empty">No account breakdown data available.</p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column" }}>
              {overview.account_breakdown.slice(0, 5).map((a, i) => {
                const isUnknown = !a.account || a.account === "Unknown";
                return (
                  <div
                    key={a.account || i}
                    className="panel-hover"
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      padding: "9px 6px",
                      borderBottom: "1px solid var(--line)",
                      cursor: "pointer",
                      borderRadius: "var(--radius-sm)",
                    }}
                    title={`View transactions for ${a.account || "this account"}`}
                    onClick={() => {
                      navigate(`/transactions?date_from=${monthParamFrom}&date_to=${monthParamTo}&q=${encodeURIComponent(a.account || "")}`);
                    }}
                  >
                    <div>
                      <div style={{ fontWeight: 600, fontSize: "0.92rem", display: "flex", alignItems: "center", gap: "6px" }}>
                        {isUnknown ? (
                          <span style={{ color: "var(--warn)", fontSize: "0.82rem", fontWeight: 600 }}>
                            ⚠ Unknown / Unlinked
                          </span>
                        ) : (
                          <AccountBadge accountName={a.account} logoSize={20} />
                        )}
                      </div>
                      <div style={{ fontSize: "0.78rem", color: "var(--ink-muted)", marginTop: 1 }}>
                        {a.percentage.toFixed(1)}% of spending
                      </div>
                    </div>
                    <div style={{ fontWeight: 600, textAlign: "right", fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}>
                      {formatMoney(a.total, overview.currency)}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>
      </div>

      {/* Largest Transactions (5 Table Rows + Link to Full List) */}
      <section className="section" style={{ marginBottom: "28px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "12px" }}>
          <h2 style={{ margin: 0 }}>Largest Transactions</h2>
          <span style={{ fontSize: "0.8rem", color: "var(--ink-muted)" }}>Top individual outflows</span>
        </div>
        {overview.largest_transactions.length > 0 ? (
          <>
            {/* Desktop Table */}
            <div className="table-wrap tx-table-desktop">
              <table>
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Merchant / Description</th>
                    <th>Category</th>
                    <th>Account</th>
                    <th className="num">Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {overview.largest_transactions.slice(0, 5).map((t) => (
                    <tr
                      key={t.id}
                      style={{ cursor: "pointer" }}
                      onClick={() => {
                        navigate(`/transactions?q=${encodeURIComponent(t.merchant || t.id)}`);
                      }}
                    >
                      <td className="tx-date">{formatDate(t.date)}</td>
                      <td style={{ fontWeight: 600 }}>{t.merchant || "Unidentified merchant"}</td>
                      <td>
                        <span className="badge">{t.category || "Uncategorized"}</span>
                      </td>
                      <td style={{ color: "var(--ink-muted)" }}>{t.account || "—"}</td>
                      <td className="tx-amount num debit">
                        −{formatMoney(t.amount, overview.currency)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Mobile Cards */}
            <div className="tx-cards-mobile">
              {overview.largest_transactions.slice(0, 5).map((t) => (
                <article
                  key={t.id}
                  className="tx-card"
                  style={{ cursor: "pointer" }}
                  onClick={() => {
                    navigate(`/transactions?q=${encodeURIComponent(t.merchant || t.id)}`);
                  }}
                >
                  <div className="tx-card-header">
                    <div>
                      <div className="tx-card-merchant">{t.merchant || "Unidentified merchant"}</div>
                      <div className="tx-card-date">{formatDate(t.date)}</div>
                    </div>
                    <div className="tx-card-amount debit">−{formatMoney(t.amount, overview.currency)}</div>
                  </div>
                  <div className="tx-card-footer" style={{ borderTop: "1px solid var(--line)", paddingTop: 8 }}>
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                      <span className="badge">{t.category || "Uncategorized"}</span>
                      {t.account && <span className="tx-card-tag">{t.account}</span>}
                    </div>
                    <span style={{ fontSize: "0.78rem", color: "var(--accent)", fontWeight: 600 }}>View tx →</span>
                  </div>
                </article>
              ))}
            </div>

            {/* Bottom View All Link */}
            <div style={{ marginTop: "14px", textAlign: "right" }}>
              <Link
                to={`/transactions?date_from=${monthParamFrom}&date_to=${monthParamTo}`}
                style={{ color: "var(--accent)", textDecoration: "none", fontSize: "0.85rem", fontWeight: 600 }}
              >
                View all {overview.summary.transaction_count} transactions →
              </Link>
            </div>
          </>
        ) : (
          <p className="empty">No transactions recorded for this month.</p>
        )}
      </section>

      {/* Financial Trend Modal (Spent, Income, Net Cash Flow) */}
      <FinancialTrendModal
        open={trendModalOpen}
        loading={trendsLoading}
        error={trendsError}
        trends={financialTrends}
        overview={overview}
        initialMetric={trendMetric}
        onClose={() => setTrendModalOpen(false)}
      />
    </div>
  );
}
