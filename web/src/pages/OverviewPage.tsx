import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, type Overview, type AccountsResponse, type IncomeTrend } from "../api";
import IncomeTrendModal from "../components/IncomeTrendModal";
import { formatMoney, formatCompactMoney, monthLabel, formatDate } from "../format";

function getPeriodLabel(year: number, month: number) {
  const startDate = new Date(year, month - 1, 1);
  const endDate = new Date(year, month, 0);
  const startStr = startDate.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
  const endStr = endDate.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
  return `${startStr} – ${endStr}`;
}

export default function OverviewPage() {
  const navigate = useNavigate();
  const [date, setDate] = useState(() => {
    const now = new Date();
    return { year: now.getFullYear(), month: now.getMonth() + 1 };
  });
  const [overview, setOverview] = useState<Overview | null>(null);
  const [accounts, setAccounts] = useState<AccountsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAllCategories, setShowAllCategories] = useState(false);
  const [hoveredDay, setHoveredDay] = useState<{ day: number; dateStr: string; spent: number } | null>(null);

  // Income trend modal state
  const [incomeTrendOpen, setIncomeTrendOpen] = useState(false);
  const [incomeTrend, setIncomeTrend] = useState<IncomeTrend | null>(null);
  const [incomeTrendLoading, setIncomeTrendLoading] = useState(false);
  const [incomeTrendError, setIncomeTrendError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setShowAllCategories(false);

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

    api
      .accounts()
      .then((a) => {
        if (!cancelled) setAccounts(a);
      })
      .catch(console.error);

    return () => {
      cancelled = true;
    };
  }, [date.year, date.month]);

  function prevMonth() {
    setDate((prev) => {
      if (prev.month === 1) return { year: prev.year - 1, month: 12 };
      return { ...prev, month: prev.month - 1 };
    });
  }

  function nextMonth() {
    setDate((prev) => {
      if (prev.month === 12) return { year: prev.year + 1, month: 1 };
      return { ...prev, month: prev.month + 1 };
    });
  }

  function goToCurrentMonth() {
    const now = new Date();
    setDate({ year: now.getFullYear(), month: now.getMonth() + 1 });
  }

  function openIncomeTrend() {
    setIncomeTrendOpen(true);
    setIncomeTrendLoading(true);
    setIncomeTrendError(null);
    api
      .incomeTrend(6)
      .then((trend) => {
        setIncomeTrend(trend);
      })
      .catch((err: Error) => {
        setIncomeTrendError(err.message);
      })
      .finally(() => {
        setIncomeTrendLoading(false);
      });
  }

  const isCurrentMonth = useMemo(() => {
    const now = new Date();
    return date.year === now.getFullYear() && date.month === now.getMonth() + 1;
  }, [date.year, date.month]);

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

  const fullDailyData = useMemo(() => {
    const data: Array<{ day: number; dateStr: string; spent: number }> = [];
    for (let day = 1; day <= daysInMonth; day++) {
      const padM = String(date.month).padStart(2, "0");
      const padD = String(day).padStart(2, "0");
      const dateStr = `${date.year}-${padM}-${padD}`;
      data.push({
        day,
        dateStr,
        spent: dailyMap.get(dateStr) || 0,
      });
    }
    return data;
  }, [daysInMonth, date.year, date.month, dailyMap]);

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

  const consumerCategories = overview.category_breakdown.filter((c) =>
    ["essential", "discretionary"].includes(c.expense_type || "")
  );
  const otherCategories = overview.category_breakdown.filter((c) =>
    ["transfer", "financial", "investment"].includes(c.expense_type || "")
  );
  const uncategorizedCategories = overview.category_breakdown.filter(
    (c) => !["essential", "discretionary", "transfer", "financial", "investment"].includes(c.expense_type || "")
  );

  function renderCategoryGroup(title: string, cats: Overview["category_breakdown"]) {
    if (cats.length === 0) return null;
    const maxCat = Math.max(1, ...cats.map((c) => c.total));
    const displayCats = showAllCategories ? cats : cats.slice(0, 5);

    return (
      <div style={{ marginBottom: "20px" }}>
        <div
          style={{
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
          {title}
        </div>
        <div className="category-list">
          {displayCats.map((c) => (
            <div
              key={c.category_id}
              className="category-row"
              style={{ cursor: "pointer" }}
              title={`View ${c.category} transactions`}
              onClick={() => {
                const padM = String(date.month).padStart(2, "0");
                const from = `${date.year}-${padM}-01`;
                const to = `${date.year}-${padM}-${String(daysInMonth).padStart(2, "0")}`;
                navigate(`/transactions?date_from=${from}&date_to=${to}&category=${encodeURIComponent(c.category)}`);
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
                  {c.percentage.toFixed(1)}%
                </span>
                <span>{formatMoney(c.total, overview!.currency)}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="overview-page" style={{ animation: "rise 0.4s ease both" }}>
      {/* Page Header with Month Selector */}
      <header
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-end",
          flexWrap: "wrap",
          gap: "16px",
          marginBottom: "20px",
        }}
      >
        <div>
          <h1 className="page-title" style={{ margin: 0 }}>Monthly Analysis</h1>
          <p className="lead" style={{ margin: "2px 0 0", color: "var(--ink-muted)", fontSize: "0.9rem" }}>
            {getPeriodLabel(date.year, date.month)}
          </p>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          {!isCurrentMonth && (
            <button className="btn quiet" onClick={goToCurrentMonth} disabled={loading}>
              This Month
            </button>
          )}
          <button className="btn quiet" onClick={prevMonth} disabled={loading} aria-label="Previous month">
            ← Previous
          </button>
          <strong style={{ fontFamily: "var(--font-display)", fontSize: "1.1rem", padding: "0 6px" }}>
            {monthLabel(date.year, date.month)}
          </strong>
          <button className="btn quiet" onClick={nextMonth} disabled={loading} aria-label="Next month">
            Next →
          </button>
        </div>
      </header>

      {/* Needs Review / Data Quality Banner */}
      {overview.review.needs_review_count > 0 && (() => {
        const padM = String(date.month).padStart(2, "0");
        const from = `${date.year}-${padM}-01`;
        const to = `${date.year}-${padM}-${String(daysInMonth).padStart(2, "0")}`;
        return (
          <div className="attention-banner" role="alert">
            <div className="attention-banner-content">
              <span className="attention-banner-icon" aria-hidden="true">⚠</span>
              <span>
                <strong>{overview.review.needs_review_count} transactions</strong> (
                {formatMoney(overview.review.needs_review_amount, overview.currency)}) need classification
              </span>
            </div>
            <Link to={`/review?date_from=${from}&date_to=${to}`} className="attention-banner-link">
              Review →
            </Link>
          </div>
        );
      })()}

      {/* Primary Financial Flow KPI Strip */}
      <section className="metrics" aria-label="Monthly financial flow">
        <article className="metric">
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
        </article>

        <button
          type="button"
          className="metric-button"
          onClick={openIncomeTrend}
          title="Click to view 6-month income trend"
          aria-label="Income, click to view 6-month trend"
        >
          <div className="metric-label" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span>Income</span>
            <span style={{ fontSize: "0.68rem", color: "var(--accent)", fontWeight: 600 }}>Trend ↗</span>
          </div>
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

        <article className="metric">
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
        </article>
      </section>

      {/* Supporting Metrics: Flow Volume & Financial Position */}
      <section
        style={{
          display: "grid",
          gridTemplateColumns: accounts ? "1fr 1fr" : "1fr",
          gap: "16px",
          marginBottom: "28px",
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            padding: "10px 16px",
            border: "1px solid var(--line)",
            borderRadius: "var(--radius)",
            background: "var(--surface)",
          }}
        >
          <span style={{ fontSize: "0.85rem", color: "var(--ink-muted)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em" }}>
            Transactions
          </span>
          <span style={{ fontSize: "0.92rem", fontWeight: 600 }}>
            {overview.summary.transaction_count} total{" "}
            <span style={{ color: "var(--ink-muted)", fontWeight: 400 }}>
              ({overview.summary.debit_count} out · {overview.summary.credit_count} in)
            </span>
          </span>
        </div>

        {accounts && (
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              padding: "10px 16px",
              border: "1px solid var(--line)",
              borderRadius: "var(--radius)",
              background: "var(--surface)",
            }}
          >
            <span style={{ fontSize: "0.85rem", color: "var(--ink-muted)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em" }}>
              Net Worth Position
            </span>
            <span style={{ fontSize: "0.92rem", fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>
              {formatMoney(accounts.net_worth, overview.currency)}{" "}
              <span style={{ color: "var(--ink-muted)", fontWeight: 400 }}>
                ({accounts.accounts.length} accounts)
              </span>
            </span>
          </div>
        )}
      </section>

      {/* Spending Breakdown & Daily Spending Chart (60/40 grid) */}
      <div className="grid-2" style={{ marginBottom: "28px" }}>
        {/* Left: Spending Breakdown */}
        <section className="section">
          <h2>Spending Breakdown</h2>
          {overview.category_breakdown.length === 0 ? (
            <p className="empty">No spending recorded for this month.</p>
          ) : (
            <div>
              {renderCategoryGroup("Consumer Spending", consumerCategories)}
              {renderCategoryGroup("Other Cash Movements", otherCategories)}
              {renderCategoryGroup("Other / Uncategorized", uncategorizedCategories)}

              {overview.category_breakdown.length > 5 && (
                <div style={{ marginTop: "12px", textAlign: "left" }}>
                  <button
                    type="button"
                    className="btn quiet"
                    onClick={() => setShowAllCategories((prev) => !prev)}
                    style={{ fontSize: "0.85rem", padding: "4px 8px" }}
                  >
                    {showAllCategories ? "Show top categories ↑" : "View all categories →"}
                  </button>
                </div>
              )}
            </div>
          )}
        </section>

        {/* Right: Daily Spending Chart */}
        <section className="section" style={{ display: "flex", flexDirection: "column" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "12px" }}>
            <h2>Daily Spending</h2>
            <div style={{ fontSize: "0.82rem", color: "var(--ink-muted)", textAlign: "right" }}>
              Avg {formatCompactMoney(avgDaily, overview.currency)} / day · Peak {formatCompactMoney(maxDaily, overview.currency)}
            </div>
          </div>

          <div style={{ display: "flex", gap: "8px", height: "190px", marginTop: "8px" }}>
            {/* Y-Axis Column */}
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
              {/* Horizontal Grid lines */}
              <div
                style={{
                  position: "absolute",
                  left: 0,
                  right: 0,
                  top: "2px",
                  borderTop: "1px dashed var(--line)",
                  opacity: 0.6,
                  pointerEvents: "none",
                }}
              />
              <div
                style={{
                  position: "absolute",
                  left: 0,
                  right: 0,
                  top: "50%",
                  borderTop: "1px dashed var(--line)",
                  opacity: 0.6,
                  pointerEvents: "none",
                }}
              />
              <div
                style={{
                  position: "absolute",
                  left: 0,
                  right: 0,
                  bottom: "2px",
                  borderTop: "1px solid var(--line)",
                  pointerEvents: "none",
                }}
              />

              {/* Average Reference Line */}
              {avgDaily > 0 && maxDaily > 0 && (
                <div
                  style={{
                    position: "absolute",
                    left: 0,
                    right: 0,
                    bottom: `${Math.min(100, (avgDaily / maxDaily) * 100)}%`,
                    borderTop: "1px dashed var(--accent)",
                    opacity: 0.7,
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
                    style={{
                      flex: 1,
                      display: "flex",
                      flexDirection: "column",
                      alignItems: "center",
                      justifyContent: "flex-end",
                      height: "100%",
                      position: "relative",
                      zIndex: 1,
                      cursor: hasSpend ? "pointer" : "default",
                    }}
                  >
                    {/* Floating Value Pill on hover */}
                    {isHovered && hasSpend && (
                      <div
                        style={{
                          position: "absolute",
                          bottom: `calc(${Math.max(4, heightPct)}% + 6px)`,
                          background: "var(--ink)",
                          color: "#fff",
                          padding: "2px 6px",
                          borderRadius: "var(--radius-sm)",
                          fontSize: "0.7rem",
                          fontVariantNumeric: "tabular-nums",
                          whiteSpace: "nowrap",
                          pointerEvents: "none",
                          zIndex: 10,
                          boxShadow: "0 2px 6px rgba(0,0,0,0.15)",
                        }}
                      >
                        {formatMoney(d.spent, overview.currency)}
                      </div>
                    )}

                    <div
                      style={{
                        width: "100%",
                        height: hasSpend ? `${Math.max(4, heightPct)}%` : "0%",
                        background: isHovered ? "var(--ink)" : "var(--accent)",
                        borderRadius: "2px 2px 0 0",
                        opacity: hasSpend ? (isHovered ? 1 : 0.85) : 0.15,
                        transition: "height 0.2s ease, opacity 0.15s ease, background 0.15s ease",
                      }}
                    />
                  </div>
                );
              })}
            </div>
          </div>

          {/* X Axis Labels */}
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

      {/* Month-over-Month Comparison */}
      <section className="section" style={{ marginBottom: "28px" }}>
        <h2>VS LAST MONTH</h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "16px", padding: "12px 0" }}>
          <div>
            <div style={{ color: "var(--ink-muted)", fontSize: "0.78rem", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "4px" }}>
              Spending Change
            </div>
            <div style={{ fontSize: "1.1rem", fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>
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
            <div style={{ color: "var(--ink-muted)", fontSize: "0.78rem", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "4px" }}>
              Income Change
            </div>
            <div style={{ fontSize: "1.1rem", fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>
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
            <div style={{ color: "var(--ink-muted)", fontSize: "0.78rem", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "4px" }}>
              Largest Increase
            </div>
            <div style={{ fontSize: "0.95rem" }}>
              {biggestIncrease ? (
                <span>
                  <strong>{biggestIncrease.category}</strong>:{" "}
                  <span className="metric-delta down" style={{ fontVariantNumeric: "tabular-nums" }}>
                    +{formatMoney(maxInc, overview.currency)}
                  </span>
                </span>
              ) : (
                <span style={{ color: "var(--ink-muted)" }}>None</span>
              )}
            </div>
          </div>

          <div>
            <div style={{ color: "var(--ink-muted)", fontSize: "0.78rem", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "4px" }}>
              Largest Decrease
            </div>
            <div style={{ fontSize: "0.95rem" }}>
              {biggestDecrease ? (
                <span>
                  <strong>{biggestDecrease.category}</strong>:{" "}
                  <span className="metric-delta up" style={{ fontVariantNumeric: "tabular-nums" }}>
                    {formatMoney(maxDec, overview.currency)}
                  </span>
                </span>
              ) : (
                <span style={{ color: "var(--ink-muted)" }}>None</span>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* Top Merchants & Payment Methods (50/50 grid) */}
      <div className="grid-2" style={{ marginBottom: "28px" }}>
        {/* Top Merchants */}
        <section className="section">
          <h2>Top Merchants</h2>
          {overview.top_merchants.length === 0 ? (
            <p className="empty">No merchants recorded this month.</p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column" }}>
              {overview.top_merchants.slice(0, 5).map((m, i) => (
                <div
                  key={m.merchant || i}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    padding: "8px 0",
                    borderBottom: "1px solid var(--line)",
                    cursor: "pointer",
                  }}
                  title={`View transactions for ${m.merchant || "merchant"}`}
                  onClick={() => {
                    const padM = String(date.month).padStart(2, "0");
                    const from = `${date.year}-${padM}-01`;
                    const to = `${date.year}-${padM}-${String(daysInMonth).padStart(2, "0")}`;
                    navigate(`/transactions?date_from=${from}&date_to=${to}&q=${encodeURIComponent(m.merchant || "")}`);
                  }}
                >
                  <div style={{ overflow: "hidden", textOverflow: "ellipsis", paddingRight: "16px" }}>
                    <div style={{ fontWeight: 600, fontSize: "0.92rem" }}>
                      {m.merchant || "Unidentified merchant"}
                    </div>
                    <div style={{ fontSize: "0.8rem", color: "var(--ink-muted)" }}>
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

        {/* Payment Methods */}
        <section className="section">
          <h2>Payment Methods</h2>
          {overview.account_breakdown.length === 0 ? (
            <p className="empty">No account breakdown data available.</p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column" }}>
              {overview.account_breakdown.slice(0, 5).map((a, i) => (
                <div
                  key={a.account || i}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    padding: "8px 0",
                    borderBottom: "1px solid var(--line)",
                  }}
                >
                  <div>
                    <div style={{ fontWeight: 600, fontSize: "0.92rem", display: "flex", alignItems: "center", gap: "6px" }}>
                      {!a.account && (
                        <span style={{ color: "var(--warn)", fontSize: "0.85rem" }} title="Data issue: transactions not linked to an account">
                          ⚠
                        </span>
                      )}
                      <span>{a.account || "Unknown account"}</span>
                    </div>
                    <div style={{ fontSize: "0.8rem", color: "var(--ink-muted)" }}>
                      {a.percentage.toFixed(1)}% of spend
                    </div>
                  </div>
                  <div style={{ fontWeight: 600, textAlign: "right", fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}>
                    {formatMoney(a.total, overview.currency)}
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>

      {/* Largest Transactions */}
      <section className="section" style={{ marginBottom: "28px" }}>
        <h2>Largest Transactions</h2>
        {overview.largest_transactions.length > 0 ? (
          <div className="table-wrap">
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
                    <td>{t.category || "Uncategorized"}</td>
                    <td style={{ color: "var(--ink-muted)" }}>{t.account || "—"}</td>
                    <td className="tx-amount num debit">
                      −{formatMoney(t.amount, overview.currency)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="empty">No transactions recorded for this month.</p>
        )}
      </section>

      {/* Income Trend Modal */}
      <IncomeTrendModal
        open={incomeTrendOpen}
        loading={incomeTrendLoading}
        error={incomeTrendError}
        trend={incomeTrend}
        overview={overview}
        onClose={() => setIncomeTrendOpen(false)}
      />
    </div>
  );
}
