import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  api,
  type CategoryAnalytics,
  type CategoryTree,
} from "../api";
import { formatMoney, formatCompactMoney, formatDate } from "../format";
import { getCategoryIcon } from "../utils/categoryIcons";

const SUBCAT_PALETTE = [
  "#10b981", // Emerald
  "#6366f1", // Indigo
  "#f59e0b", // Amber
  "#ec4899", // Pink
  "#06b6d4", // Cyan
  "#8b5cf6", // Purple
  "#f97316", // Orange
  "#3b82f6", // Blue
  "#14b8a6", // Teal
  "#e11d48", // Rose
  "#64748b", // Slate
];

// Helper to format short month label e.g. "Aug '26" or "Mar '26"
function formatMonthLabelShort(monthStr: string): string {
  if (!monthStr || !monthStr.includes("-")) return monthStr;
  const [yearStr, monthNumStr] = monthStr.split("-");
  const year = parseInt(yearStr, 10);
  const monthNum = parseInt(monthNumStr, 10);
  if (isNaN(year) || isNaN(monthNum)) return monthStr;
  const date = new Date(year, monthNum - 1, 1);
  const monthName = date.toLocaleString("en-IN", { month: "short" });
  return `${monthName} '${yearStr.slice(2)}`;
}

// Helper to format full month label e.g. "Aug 2026"
function formatMonthLabelLong(monthStr: string): string {
  if (!monthStr || !monthStr.includes("-")) return monthStr;
  const [yearStr, monthNumStr] = monthStr.split("-");
  const year = parseInt(yearStr, 10);
  const monthNum = parseInt(monthNumStr, 10);
  if (isNaN(year) || isNaN(monthNum)) return monthStr;
  const date = new Date(year, monthNum - 1, 1);
  const monthName = date.toLocaleString("en-IN", { month: "short" });
  return `${monthName} ${yearStr}`;
}

// Helper to compute smooth cubic bezier path for SVG line charts
function getSmoothCurvedPath(points: Array<{ x: number; y: number }>): string {
  if (points.length === 0) return "";
  if (points.length === 1) return `M ${points[0].x} ${points[0].y}`;
  if (points.length === 2) return `M ${points[0].x} ${points[0].y} L ${points[1].x} ${points[1].y}`;

  let path = `M ${points[0].x.toFixed(1)} ${points[0].y.toFixed(1)}`;
  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[i === 0 ? 0 : i - 1];
    const p1 = points[i];
    const p2 = points[i + 1];
    const p3 = points[i + 2 < points.length ? i + 2 : i + 1];

    const cp1x = p1.x + (p2.x - p0.x) / 6;
    const cp1y = p1.y + (p2.y - p0.y) / 6;
    const cp2x = p2.x - (p3.x - p1.x) / 6;
    const cp2y = p2.y - (p3.y - p1.y) / 6;

    path += ` C ${cp1x.toFixed(1)} ${cp1y.toFixed(1)}, ${cp2x.toFixed(1)} ${cp2y.toFixed(1)}, ${p2.x.toFixed(1)} ${p2.y.toFixed(1)}`;
  }
  return path;
}

export default function CategoryAnalyticsPage() {
  const navigate = useNavigate();
  const { categoryId: paramCatId } = useParams<{ categoryId?: string }>();
  const [searchParams, setSearchParams] = useSearchParams();

  const [categories, setCategories] = useState<CategoryTree[]>([]);
  const [catsLoading, setCatsLoading] = useState(true);

  const range = searchParams.get("range") || "6m";
  const yearParam = searchParams.get("year") ? parseInt(searchParams.get("year")!, 10) : undefined;
  const monthParam = searchParams.get("month") ? parseInt(searchParams.get("month")!, 10) : undefined;

  const [data, setData] = useState<CategoryAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [viewMode, setViewMode] = useState<"stacked" | "line">("stacked");
  const [selectedMonth, setSelectedMonth] = useState<CategoryAnalytics["trend"][number] | null>(null);
  const [hoveredSubcat, setHoveredSubcat] = useState<string | null>(null);
  const [showAllMerchants, setShowAllMerchants] = useState(false);

  // Category Picker Modal State
  const [isPickerOpen, setIsPickerOpen] = useState(false);

  // Responsive chart width tracking
  const chartScrollRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState<number>(() => {
    return typeof window !== "undefined"
      ? Math.min(960, Math.max(300, window.innerWidth - 48))
      : 960;
  });

  useEffect(() => {
    if (!chartScrollRef.current) return;
    const updateWidth = () => {
      if (chartScrollRef.current) {
        const w = chartScrollRef.current.clientWidth;
        if (w > 0) setContainerWidth(w);
      }
    };
    updateWidth();
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const w = Math.round(entry.contentRect.width);
        if (w > 0) setContainerWidth(w);
      }
    });
    ro.observe(chartScrollRef.current);
    window.addEventListener("resize", updateWidth);
    return () => {
      ro.disconnect();
      window.removeEventListener("resize", updateWidth);
    };
  }, [viewMode]);

  // 1. Fetch categories taxonomy
  useEffect(() => {
    let cancelled = false;
    setCatsLoading(true);
    api.categories()
      .then((res) => {
        if (cancelled) return;
        const validCats = res.items.filter((c) => c.slug !== "transfers");
        setCategories(validCats);
        // If no paramCatId in URL, default to first category (e.g. Food)
        if (!paramCatId && validCats.length > 0) {
          navigate(`/analytics/category/${validCats[0].id}?${searchParams.toString()}`, { replace: true });
        }
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setCatsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [paramCatId, navigate, searchParams]);

  // 2. Fetch Category Analytics
  useEffect(() => {
    if (!paramCatId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setSelectedMonth(null);

    api.categoryAnalytics(paramCatId, {
      range,
      year: yearParam,
      month: monthParam,
    })
      .then((res) => {
        if (cancelled) return;
        setData(res);
        // Default selected month to latest month in trend
        if (res.trend.length > 0) {
          setSelectedMonth(res.trend[res.trend.length - 1]);
        }
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
  }, [paramCatId, range, yearParam, monthParam]);

  const activeCategory = useMemo(() => {
    return categories.find((c) => c.id === paramCatId) || (data ? {
      id: data.category.id,
      name: data.category.name,
      slug: data.category.slug,
      expense_type: data.category.expense_type || undefined,
      subcategories: [],
    } : null);
  }, [categories, paramCatId, data]);

  // Subcategory color map
  const subcatColors = useMemo(() => {
    const map = new Map<string, string>();
    if (!data) return map;
    data.subcategories.forEach((sub, idx) => {
      map.set(sub.id, SUBCAT_PALETTE[idx % SUBCAT_PALETTE.length]);
    });
    map.set("unassigned", "#94a3b8");
    return map;
  }, [data]);

  // Max month total in trend for chart scaling
  const maxTrendTotal = data?.trend.length ? Math.max(1, ...data.trend.map((t) => t.total)) : 1;

  // Comparison period label
  const comparisonLabel = useMemo(() => {
    if (!data) return "vs previous period";
    if (range === "1m" || data.period.months === 1) return "vs previous month";
    if (range === "3m") return "vs previous 3 months";
    if (range === "6m") return "vs previous 6 months";
    if (range === "12m") return "vs previous 12 months";
    if (range === "ytd") return "vs previous period";
    return `vs previous ${data.period.months} months`;
  }, [data, range]);

  // SVG Line Chart coordinates for line view mode with smooth curves matching bar scale
  const linePoints = useMemo(() => {
    if (!data || data.trend.length === 0) {
      return { path: "", areaPath: "", dots: [], gridTicks: [], width: 960, height: 250, paddingBottom: 38, isCompact: false };
    }
    const count = data.trend.length;
    const baseW = containerWidth > 0 ? containerWidth : (typeof window !== "undefined" ? Math.min(960, window.innerWidth - 48) : 960);
    const isCompact = baseW < 520;
    const minPointSpacing = isCompact ? 50 : 70;
    const width = Math.max(baseW, count * minPointSpacing);
    const height = 250;
    const paddingLeft = isCompact ? 36 : 54;
    const paddingRight = isCompact ? 24 : 44;
    const paddingTop = 36;
    const paddingBottom = 38;
    const usableW = width - paddingLeft - paddingRight;
    const usableH = height - paddingTop - paddingBottom;

    const countClamped = Math.max(1, count);
    const step = countClamped > 1 ? usableW / (countClamped - 1) : usableW / 2;

    const dots = data.trend.map((item, idx) => {
      const x = paddingLeft + idx * step;
      const y = height - paddingBottom - (maxTrendTotal > 0 ? (item.total / maxTrendTotal) * usableH : 0);
      return { x, y, month: item.month, total: item.total };
    });

    const path = getSmoothCurvedPath(dots);
    const lastDot = dots[dots.length - 1];
    const firstDot = dots[0];
    const areaPath = `${path} L ${lastDot.x.toFixed(1)} ${(height - paddingBottom).toFixed(1)} L ${firstDot.x.toFixed(1)} ${(height - paddingBottom).toFixed(1)} Z`;

    const gridTicks = [0, 0.33, 0.66, 1.0].map((ratio) => ({
      y: height - paddingBottom - ratio * usableH,
      amount: ratio * maxTrendTotal,
    }));

    return { path, areaPath, dots, gridTicks, width, height, paddingBottom, isCompact };
  }, [data, maxTrendTotal, containerWidth]);

  const handleRangeChange = (newRange: string) => {
    const next = new URLSearchParams(searchParams);
    next.set("range", newRange);
    setSearchParams(next);
  };

  const handleCategoryChange = (catId: string) => {
    setIsPickerOpen(false);
    navigate(`/analytics/category/${catId}?${searchParams.toString()}`);
  };

  // Group categories by expense type for the modal picker
  const groupedCategories = useMemo(() => {
    const groups: { [key: string]: CategoryTree[] } = {
      living: [],
      discretionary: [],
      investment: [],
      other: [],
    };
    categories.forEach((c) => {
      const type = c.expense_type || "other";
      if (groups[type]) {
        groups[type].push(c);
      } else {
        groups.other.push(c);
      }
    });
    return groups;
  }, [categories]);

  if (catsLoading && !activeCategory) {
    return <div className="empty" style={{ padding: "48px 0" }}>Loading category taxonomy…</div>;
  }

  if (error && !data) {
    return (
      <div style={{ maxWidth: 1060, margin: "0 auto", padding: "24px 0" }}>
        <p className="error">Failed to load category analytics: {error}</p>
        <Link to="/" className="btn quiet" style={{ marginTop: 12 }}>
          ← Back to Overview
        </Link>
      </div>
    );
  }

  // Drilldown date filters for Ledger
  const drilldownFrom = data?.period.start ? data.period.start.slice(0, 10) : "";
  const drilldownTo = data?.period.end ? data.period.end.slice(0, 10) : "";

  const displayedMerchants = data?.merchants
    ? (showAllMerchants ? data.merchants : data.merchants.slice(0, 5))
    : [];

  const subcategoriesCount = activeCategory?.subcategories.length || data?.subcategories.length || 0;
  const expenseTypeLabel = activeCategory?.expense_type || data?.category.expense_type || "Expense";

  return (
    <div className="category-analytics-page" style={{ maxWidth: 1060, margin: "0 auto" }}>
      {/* ───────────────────────────────────────────────────────────── */}
      {/* 1. BREADCRUMB & CATEGORY HEADER                               */}
      {/* ───────────────────────────────────────────────────────────── */}
      <nav className="category-breadcrumb" aria-label="Breadcrumb">
        <Link to="/" className="category-breadcrumb-link">Overview</Link>
        <span className="category-breadcrumb-sep">/</span>
        <span className="category-breadcrumb-current">Category Deep Dive</span>
      </nav>

      <header className="category-analytics-header">
        {/* Compact Category Selector Header Card */}
        <button
          type="button"
          className="category-selector-btn"
          onClick={() => setIsPickerOpen(true)}
          aria-label={`Change Category, current: ${activeCategory?.name || "Category"}`}
        >
          <div className="category-selector-main">
            <div className="category-selector-icon-badge" aria-hidden="true">
              {getCategoryIcon(activeCategory?.name || "", activeCategory?.expense_type)}
            </div>
            <div className="category-selector-info">
              <div className="category-selector-title">
                {activeCategory?.name || "Select Category"}
              </div>
              <div className="category-selector-meta">
                <span className="category-type-tag">{expenseTypeLabel}</span>
                <span className="category-meta-dot">·</span>
                <span>{subcategoriesCount} {subcategoriesCount === 1 ? "subcategory" : "subcategories"}</span>
              </div>
            </div>
          </div>
          <div className="category-selector-chevron" aria-hidden="true">
            ▾
          </div>
        </button>

        {/* 2. Compact Period Selector */}
        <div className="category-period-controls">
          <div
            className="segmented-control category-range-segmented"
            role="group"
            aria-label="Select Period"
          >
            {(["1m", "3m", "6m", "12m", "ytd"] as const).map((r) => (
              <button
                key={r}
                type="button"
                className={`btn quiet ${range === r ? "active" : ""}`}
                onClick={() => handleRangeChange(r)}
              >
                {r.toUpperCase()}
              </button>
            ))}
          </div>

          {data && (
            <div className="category-period-dates">
              {formatDate(data.period.start)} – {formatDate(data.period.end)}
            </div>
          )}
        </div>
      </header>

      {loading && !data ? (
        <div className="empty" style={{ padding: "48px 0" }}>
          Aggregating ledger insights for {activeCategory?.name}…
        </div>
      ) : data ? (
        <>
          {/* ───────────────────────────────────────────────────────────── */}
          {/* 3. SUMMARY METRICS (3 COMPACT CARDS)                          */}
          {/* ───────────────────────────────────────────────────────────── */}
          <section className="category-metrics-grid" aria-label="Category Key Metrics">
            {/* Metric 1: Total Spend */}
            <article className="category-metric-card">
              <div className="category-metric-label">Total Spend</div>
              <div className="category-metric-value category-spend-value">
                {formatMoney(data.summary.period_total_spend)}
              </div>
              <div className="category-metric-hint">
                {data.summary.period_change_pct != null ? (
                  <span className={data.summary.period_change_pct > 0 ? "metric-delta down" : "metric-delta up"}>
                    {data.summary.period_change_pct > 0 ? "↑" : "↓"} {Math.abs(data.summary.period_change_pct)}% {comparisonLabel}
                  </span>
                ) : (
                  <span>{comparisonLabel} —</span>
                )}
              </div>
            </article>

            {/* Metric 2: Ticket Size (Avg / Median) */}
            <article className="category-metric-card">
              <div className="category-metric-label">Average / Median Ticket</div>
              <div className="category-metric-value">
                {formatMoney(data.summary.avg_ticket)}{" "}
                <span className="category-metric-secondary">/ {formatMoney(data.summary.median_ticket)}</span>
              </div>
              <div className="category-metric-hint">
                {data.summary.transaction_count} qualifying transactions
              </div>
            </article>

            {/* Metric 3: Share of Living Spend */}
            <article className="category-metric-card">
              <div className="category-metric-label">Share of Living Spend</div>
              <div className="category-metric-value category-share-value">
                {(data.summary.share_of_living_spend * 100).toFixed(1)}%
              </div>
              <div className="category-metric-hint">
                of total living expenses
              </div>
            </article>
          </section>

          {/* ───────────────────────────────────────────────────────────── */}
          {/* 4. CATEGORY INTELLIGENCE                                      */}
          {/* ───────────────────────────────────────────────────────────── */}
          <section className="category-intelligence-section" aria-label="Category Intelligence">
            <div className="category-section-title">
              <span className="category-section-icon" aria-hidden="true">✨</span>
              <span>Category Intelligence</span>
            </div>

            {data.insights.length > 0 ? (
              <div className="category-insights-grid">
                {data.insights.map((ins, idx) => {
                  const isPositive = ins.severity === "positive";
                  const isWarning = ins.severity === "warning";
                  return (
                    <div
                      key={idx}
                      className={`category-insight-card ${isPositive ? "positive" : isWarning ? "warning" : "info"}`}
                    >
                      <div className="category-insight-header">
                        <span className="category-insight-dot" aria-hidden="true" />
                        <span className="category-insight-title">{ins.title}</span>
                      </div>
                      <div className="category-insight-body">{ins.message}</div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="category-insight-card neutral">
                <div className="category-insight-header">
                  <span className="category-insight-dot" aria-hidden="true" />
                  <span className="category-insight-title">No significant spending patterns detected.</span>
                </div>
                <div className="category-insight-body">
                  Spending in {data.category.name} is distributed evenly within expected historical ranges.
                </div>
              </div>
            )}
          </section>

          {/* ───────────────────────────────────────────────────────────── */}
          {/* 5. MONTHLY SPEND TREND & SELECTED MONTH DETAIL                 */}
          {/* ───────────────────────────────────────────────────────────── */}
          <section className="panel category-trend-panel">
            <div className="category-trend-header">
              <div>
                <h2 className="category-trend-title">Monthly Spend Trend</h2>
                <p className="category-trend-subtitle">
                  Monthly spend distribution across subcategories.
                </p>
              </div>

              {/* View Toggle */}
              <div className="segmented-control category-view-toggle" role="group" aria-label="Chart view mode">
                <button
                  type="button"
                  className={`btn quiet ${viewMode === "stacked" ? "active" : ""}`}
                  onClick={() => setViewMode("stacked")}
                >
                  Stacked
                </button>
                <button
                  type="button"
                  className={`btn quiet ${viewMode === "line" ? "active" : ""}`}
                  onClick={() => setViewMode("line")}
                >
                  Trajectory
                </button>
              </div>
            </div>

            {/* Subcategory Color Legend */}
            <div className="category-legend-strip">
              {data.subcategories.map((sub) => {
                const color = subcatColors.get(sub.id) || "#64748b";
                const isHovered = hoveredSubcat === sub.id;
                return (
                  <div
                    key={sub.id}
                    className={`category-legend-item ${hoveredSubcat && !isHovered ? "dimmed" : ""} ${isHovered ? "active" : ""}`}
                    onMouseEnter={() => setHoveredSubcat(sub.id)}
                    onMouseLeave={() => setHoveredSubcat(null)}
                    onClick={() => setHoveredSubcat(hoveredSubcat === sub.id ? null : sub.id)}
                  >
                    <span className="category-legend-dot" style={{ background: color }} />
                    <span className="category-legend-name">{sub.name}</span>
                  </div>
                );
              })}
            </div>

            {/* Scrollable Chart Canvas Container */}
            <div className="category-chart-scroll-wrap" ref={chartScrollRef}>
              {viewMode === "stacked" ? (
                <div
                  className="category-stacked-chart"
                  style={{
                    maxWidth: Math.min(960, Math.max(340, data.trend.length * 130)),
                    minWidth: Math.max(340, data.trend.length * 56),
                  }}
                >
                  {data.trend.map((month) => {
                    const monthTotal = month.total;
                    const heightPct = maxTrendTotal > 0 ? (monthTotal / maxTrendTotal) * 100 : 0;
                    const isSelected = selectedMonth?.month === month.month;

                    return (
                      <div
                        key={month.month}
                        className={`category-bar-col ${isSelected ? "selected" : ""}`}
                        onClick={() => setSelectedMonth(month)}
                        role="button"
                        tabIndex={0}
                        aria-label={`Month ${formatMonthLabelLong(month.month)}: ${formatMoney(month.total)}`}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            setSelectedMonth(month);
                          }
                        }}
                      >
                        {/* High contrast pill badge on top of bar */}
                        <div className={`category-bar-badge ${isSelected ? "active" : ""}`}>
                          {formatMoney(month.total, "INR").replace(".00", "")}
                        </div>

                        {/* Stacked Bar Pillar */}
                        <div
                          className={`category-bar-pillar ${isSelected ? "active" : ""}`}
                          style={{ height: `${Math.max(6, heightPct)}%` }}
                        >
                          {month.subcategories.map((sub) => {
                            const subPct = monthTotal > 0 ? (sub.spend / monthTotal) * 100 : 0;
                            if (subPct <= 0) return null;
                            const color = subcatColors.get(sub.id) || "#94a3b8";
                            const isSubDimmed = hoveredSubcat && hoveredSubcat !== sub.id;

                            return (
                              <div
                                key={sub.id}
                                style={{
                                  height: `${subPct}%`,
                                  background: color,
                                  opacity: isSubDimmed ? 0.20 : 1,
                                  transition: "opacity 0.2s ease",
                                }}
                                title={`${sub.name}: ${formatMoney(sub.spend)}`}
                              />
                            );
                          })}
                        </div>

                        {/* X-Axis Month Label */}
                        <div className={`category-bar-label ${isSelected ? "active" : ""}`}>
                          {formatMonthLabelShort(month.month)}
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                /* High-Readability Smooth Line Trajectory Mode matching bar scale */
                <div
                  className="category-line-chart-wrap"
                  style={{
                    width: linePoints.width,
                    minWidth: "100%",
                    height: 250,
                  }}
                >
                  <svg
                    viewBox={`0 0 ${linePoints.width} ${linePoints.height}`}
                    className="category-line-svg"
                    style={{
                      width: linePoints.width,
                      height: 250,
                      display: "block",
                    }}
                  >
                    <defs>
                      <linearGradient id="lineGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.35" />
                        <stop offset="100%" stopColor="var(--accent)" stopOpacity="0.0" />
                      </linearGradient>
                    </defs>

                    {/* Horizontal Reference Grid Lines */}
                    {linePoints.gridTicks.map((tick, idx) => (
                      <g key={idx}>
                        <line
                          x1="28"
                          y1={tick.y}
                          x2={linePoints.width - 28}
                          y2={tick.y}
                          stroke="var(--line)"
                          strokeWidth="1"
                          strokeDasharray="4 4"
                          opacity="0.6"
                        />
                        <text
                          x="24"
                          y={tick.y + 3}
                          textAnchor="end"
                          fontSize={linePoints.isCompact ? "8.5" : "9.5"}
                          fill="var(--ink-muted)"
                          opacity="0.8"
                        >
                          {formatCompactMoney(tick.amount)}
                        </text>
                      </g>
                    ))}

                    {/* Smooth Area Gradient Fill */}
                    {linePoints.dots.length > 1 && (
                      <path
                        d={linePoints.areaPath}
                        fill="url(#lineGrad)"
                      />
                    )}

                    {/* Smooth Spline Curve Stroke */}
                    <path
                      d={linePoints.path}
                      fill="none"
                      stroke="var(--accent)"
                      strokeWidth="3.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />

                    {/* Data Points with Badges */}
                    {linePoints.dots.map((dot, idx) => {
                      const isSelected = selectedMonth?.month === dot.month;
                      const badgeW = linePoints.isCompact ? 48 : 56;
                      const badgeH = 18;

                      return (
                        <g
                          key={idx}
                          onClick={() => setSelectedMonth(data.trend[idx])}
                          style={{ cursor: "pointer" }}
                          tabIndex={0}
                          role="button"
                          aria-label={`Month ${formatMonthLabelLong(dot.month)}: ${formatMoney(dot.total)}`}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" || e.key === " ") {
                              e.preventDefault();
                              setSelectedMonth(data.trend[idx]);
                            }
                          }}
                        >
                          {/* Active Glowing Aura */}
                          {isSelected && (
                            <circle
                              cx={dot.x}
                              cy={dot.y}
                              r="13"
                              fill="var(--accent-soft)"
                            />
                          )}

                          {/* Center Dot */}
                          <circle
                            cx={dot.x}
                            cy={dot.y}
                            r={isSelected ? 6.5 : 4.5}
                            fill="var(--surface)"
                            stroke="var(--accent)"
                            strokeWidth={isSelected ? 3 : 2}
                          />

                          {/* Value Tag Badge */}
                          <rect
                            x={dot.x - badgeW / 2}
                            y={dot.y - 25}
                            width={badgeW}
                            height={badgeH}
                            rx="4"
                            fill="var(--surface)"
                            stroke={isSelected ? "var(--accent)" : "var(--line)"}
                            strokeWidth={isSelected ? 1.5 : 1}
                          />
                          <text
                            x={dot.x}
                            y={dot.y - 12}
                            textAnchor="middle"
                            fontSize={linePoints.isCompact ? "9" : "10"}
                            fontWeight={isSelected ? "700" : "600"}
                            fill={isSelected ? "var(--accent)" : "var(--ink)"}
                          >
                            {formatMoney(dot.total, "INR").replace(".00", "")}
                          </text>

                          {/* X-Axis Month Label */}
                          <text
                            x={dot.x}
                            y={linePoints.height - 12}
                            textAnchor="middle"
                            fontSize={linePoints.isCompact ? "10" : "11"}
                            fontWeight={isSelected ? "700" : "500"}
                            fill={isSelected ? "var(--accent)" : "var(--ink-muted)"}
                          >
                            {formatMonthLabelShort(dot.month)}
                          </text>
                        </g>
                      );
                    })}
                  </svg>
                </div>
              )}
            </div>

            {/* 6. Selected Month Detail (Visually Connected Below Chart) */}
            {selectedMonth && (
              <div className="category-selected-month-card">
                <div className="category-selected-month-header">
                  <div className="category-selected-month-title">
                    {formatMonthLabelLong(selectedMonth.month)} Total
                  </div>
                  <div className="category-selected-month-total">
                    {formatMoney(selectedMonth.total)}
                  </div>
                </div>

                <div className="category-selected-month-grid">
                  {/* Sort by spend descending */}
                  {[...selectedMonth.subcategories]
                    .sort((a, b) => b.spend - a.spend)
                    .map((s) => {
                      const color = subcatColors.get(s.id) || "var(--accent)";
                      const pct = selectedMonth.total > 0 ? (s.spend / selectedMonth.total) * 100 : 0;
                      const isZero = s.spend === 0;

                      return (
                        <div
                          key={s.id}
                          className={`category-selected-sub-chip ${isZero ? "zero-spend" : ""}`}
                        >
                          <div className="category-selected-sub-left">
                            <span
                              className="category-selected-sub-dot"
                              style={{ background: isZero ? "var(--ink-muted)" : color }}
                            />
                            <span className="category-selected-sub-name">
                              {s.name}
                            </span>
                          </div>
                          <div className="category-selected-sub-right">
                            <span className="category-selected-sub-amt">{formatMoney(s.spend)}</span>
                            <span className="category-selected-sub-pct">({pct.toFixed(0)}%)</span>
                          </div>
                        </div>
                      );
                    })}
                </div>
              </div>
            )}
          </section>

          {/* ───────────────────────────────────────────────────────────── */}
          {/* 7 & 8. TWO-COLUMN EXPLORATION: SUBCATEGORIES + TOP MERCHANTS */}
          {/* ───────────────────────────────────────────────────────────── */}
          <div className="category-exploration-grid">
            {/* Left: Subcategory Breakdown */}
            <section className="panel category-subcats-panel">
              <div className="category-panel-header">
                <h3 className="category-panel-title">
                  Subcategory Breakdown
                </h3>
                <span className="category-panel-meta">
                  {data.subcategories.length} {data.subcategories.length === 1 ? "subcategory" : "subcategories"}
                </span>
              </div>

              {data.subcategories.length === 0 ? (
                <p className="empty">No subcategory spend recorded.</p>
              ) : (
                <div className="category-subcats-list">
                  {data.subcategories.map((sub) => {
                    const maxSub = Math.max(1, ...data.subcategories.map((s) => s.spend));
                    const color = subcatColors.get(sub.id) || "var(--accent)";
                    const drilldownSubId = sub.id === "unassigned" ? "" : sub.id;
                    const isZero = sub.spend === 0;

                    return (
                      <div
                        key={sub.id}
                        className={`category-subcat-row ${isZero ? "zero-spend" : ""}`}
                      >
                        <div className="category-subcat-top">
                          <div className="category-subcat-left">
                            <span
                              className="category-subcat-dot"
                              style={{ background: isZero ? "var(--ink-muted)" : color }}
                            />
                            <span className="category-subcat-name">
                              {sub.name}
                            </span>
                            <span className="category-subcat-share">
                              ({(sub.share_of_category * 100).toFixed(1)}%)
                            </span>
                          </div>

                          <div className="category-subcat-amt">
                            {formatMoney(sub.spend)}
                          </div>
                        </div>

                        {/* Progress bar */}
                        <div className="bar-track category-subcat-bar">
                          <div
                            className="bar-fill"
                            style={{
                              width: `${Math.min(100, (sub.spend / maxSub) * 100)}%`,
                              background: color,
                            }}
                          />
                        </div>

                        {/* Subcategory metadata row */}
                        <div className="category-subcat-bottom">
                          <div className="category-subcat-stats">
                            {sub.transaction_count} txs · avg {formatMoney(sub.avg_ticket)}
                          </div>
                          <div className="category-subcat-actions">
                            {sub.mom_change_pct != null && (
                              <span className={sub.mom_change_pct >= 0 ? "metric-delta down" : "metric-delta up"}>
                                {sub.mom_change_pct >= 0 ? "↑" : "↓"} {Math.abs(sub.mom_change_pct)}% MoM
                              </span>
                            )}
                            <Link
                              to={`/transactions?category_id=${encodeURIComponent(data.category.id)}${drilldownSubId ? `&subcategory_id=${encodeURIComponent(drilldownSubId)}` : ""}&date_from=${drilldownFrom}&date_to=${drilldownTo}`}
                              className="category-subtle-link"
                            >
                              Ledger →
                            </Link>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              {/* View all in ledger subtle link */}
              <div className="category-panel-footer">
                <Link
                  to={`/transactions?category_id=${encodeURIComponent(data.category.id)}&date_from=${drilldownFrom}&date_to=${drilldownTo}`}
                  className="category-subtle-link"
                >
                  View all subcategories in Ledger →
                </Link>
              </div>
            </section>

            {/* Right: Top Counterparties */}
            <section className="panel category-merchants-panel">
              <div className="category-panel-header">
                <h3 className="category-panel-title">
                  Top Counterparties
                </h3>
                <span className="category-panel-meta">
                  Top 5: {(data.concentration.top_5_share * 100).toFixed(1)}% of spend
                </span>
              </div>

              {/* Concentration summary pills */}
              <div className="category-concentration-strip">
                <div className="category-concentration-item">
                  Top 1: <strong>{(data.concentration.top_1_share * 100).toFixed(1)}%</strong>
                </div>
                <div className="category-concentration-item">
                  Top 3: <strong>{(data.concentration.top_3_share * 100).toFixed(1)}%</strong>
                </div>
                <div className="category-concentration-item">
                  Top 5: <strong>{(data.concentration.top_5_share * 100).toFixed(1)}%</strong>
                </div>
              </div>

              {data.merchants.length === 0 ? (
                <p className="empty">No merchant counterparties recorded.</p>
              ) : (
                <>
                  {/* Desktop Table View */}
                  <div className="category-merchants-desktop">
                    <table className="table category-merchants-table">
                      <thead>
                        <tr>
                          <th style={{ textAlign: "left" }}>Merchant</th>
                          <th style={{ textAlign: "right" }}>Spend</th>
                          <th style={{ textAlign: "right" }}>Share</th>
                          <th style={{ textAlign: "right" }}>Txs</th>
                          <th style={{ textAlign: "right" }}>Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {displayedMerchants.map((m, idx) => (
                          <tr key={idx}>
                            <td className="category-merchant-name">
                              {m.name}
                            </td>
                            <td style={{ textAlign: "right", fontWeight: 600 }}>
                              {formatMoney(m.spend)}
                            </td>
                            <td style={{ textAlign: "right", color: "var(--ink-muted)" }}>
                              {(m.share_of_category * 100).toFixed(1)}%
                            </td>
                            <td style={{ textAlign: "right", color: "var(--ink-muted)" }}>
                              {m.transaction_count}
                            </td>
                            <td style={{ textAlign: "right" }}>
                              <Link
                                to={`/transactions?category_id=${encodeURIComponent(data.category.id)}&q=${encodeURIComponent(m.name)}&date_from=${drilldownFrom}&date_to=${drilldownTo}`}
                                className="category-subtle-link"
                              >
                                View →
                              </Link>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  {/* Mobile Cards View */}
                  <div className="category-merchants-mobile">
                    {displayedMerchants.map((m, idx) => (
                      <div key={idx} className="category-merchant-card">
                        <div className="category-merchant-card-top">
                          <div className="category-merchant-name">
                            {idx + 1}. {m.name}
                          </div>
                          <div className="category-merchant-spend">
                            {formatMoney(m.spend)}
                          </div>
                        </div>

                        <div className="category-merchant-card-bottom">
                          <div>
                            {(m.share_of_category * 100).toFixed(1)}% share · {m.transaction_count} txs (avg {formatMoney(m.avg_ticket)})
                          </div>
                          <Link
                            to={`/transactions?category_id=${encodeURIComponent(data.category.id)}&q=${encodeURIComponent(m.name)}&date_from=${drilldownFrom}&date_to=${drilldownTo}`}
                            className="category-subtle-link"
                          >
                            View →
                          </Link>
                        </div>
                      </div>
                    ))}
                  </div>

                  {/* Toggle All Merchants */}
                  {data.merchants.length > 5 && (
                    <div className="category-merchants-toggle-wrap">
                      <button
                        type="button"
                        className="btn quiet category-merchants-toggle"
                        onClick={() => setShowAllMerchants((prev) => !prev)}
                      >
                        {showAllMerchants ? "Show Top 5 Counterparties ↑" : `Show All ${data.merchants.length} Counterparties ↓`}
                      </button>
                    </div>
                  )}
                </>
              )}
            </section>
          </div>

          {/* ───────────────────────────────────────────────────────────── */}
          {/* 9. VERIFIED LEDGER AUDIT TRAIL BANNER                         */}
          {/* ───────────────────────────────────────────────────────────── */}
          <div className="category-ledger-banner">
            <div className="category-ledger-banner-left">
              <div className="category-ledger-icon-wrap" aria-hidden="true">
                📋
              </div>
              <div>
                <div className="category-ledger-title">
                  Verified Ledger Audit Trail
                </div>
                <div className="category-ledger-desc">
                  All {data.summary.transaction_count} transactions supporting {formatMoney(data.summary.period_total_spend)} total spend for {data.category.name} are preserved in your local SQLite ledger.
                </div>
              </div>
            </div>

            <Link
              to={`/transactions?category_id=${encodeURIComponent(data.category.id)}&category=${encodeURIComponent(data.category.name)}&date_from=${drilldownFrom}&date_to=${drilldownTo}`}
              className="btn primary category-ledger-btn"
            >
              Open in Transactions Ledger →
            </Link>
          </div>
        </>
      ) : null}

      {/* ───────────────────────────────────────────────────────────── */}
      {/* 10. CATEGORY PICKER MODAL (Portaled to document.body)          */}
      {/* ───────────────────────────────────────────────────────────── */}
      {isPickerOpen &&
        createPortal(
          <div className="modal-backdrop" onClick={() => setIsPickerOpen(false)}>
            <div
              className="modal-panel category-picker-modal"
              onClick={(e) => e.stopPropagation()}
              role="dialog"
              aria-modal="true"
              aria-label="Select Category"
            >
              <div className="modal-header">
                <div>
                  <h3 style={{ margin: 0, fontSize: "1.1rem", fontWeight: 700 }}>Select Category</h3>
                  <p className="metric-hint" style={{ margin: 0, marginTop: 2 }}>
                    Choose a category to explore subcategory trends &amp; merchants
                  </p>
                </div>
                <button
                  type="button"
                  className="btn quiet"
                  onClick={() => setIsPickerOpen(false)}
                  style={{ padding: "4px 8px", fontSize: "1.1rem", lineHeight: 1 }}
                >
                  ✕
                </button>
              </div>

              <div className="modal-body" style={{ padding: "12px 16px 20px", overflowY: "auto", maxHeight: 440 }}>
                {Object.entries(groupedCategories).map(([groupKey, groupCats]) => {
                  if (groupCats.length === 0) return null;
                  const groupTitle =
                    groupKey === "living"
                      ? "Living Expenses"
                      : groupKey === "discretionary"
                      ? "Discretionary & Lifestyle"
                      : groupKey === "investment"
                      ? "Investments & Savings"
                      : "Commitments & Other";

                  return (
                    <div key={groupKey} style={{ marginBottom: 16 }}>
                      <div
                        style={{
                          fontSize: "0.72rem",
                          fontWeight: 700,
                          textTransform: "uppercase",
                          letterSpacing: "0.06em",
                          color: "var(--ink-muted)",
                          padding: "6px 8px",
                        }}
                      >
                        {groupTitle}
                      </div>

                      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                        {groupCats.map((cat) => {
                          const isSelected = cat.id === paramCatId;
                          return (
                            <div
                              key={cat.id}
                              className={`category-picker-item ${isSelected ? "active" : ""}`}
                              onClick={() => handleCategoryChange(cat.id)}
                            >
                              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                                <span style={{ fontSize: "1.3rem", lineHeight: 1 }}>
                                  {getCategoryIcon(cat.name, cat.expense_type)}
                                </span>
                                <div>
                                  <div style={{ fontWeight: isSelected ? 700 : 600, color: "var(--ink)", fontSize: "0.92rem" }}>
                                    {cat.name}
                                  </div>
                                  <div style={{ fontSize: "0.74rem", color: "var(--ink-muted)" }}>
                                    {cat.subcategories.length} subcategories
                                  </div>
                                </div>
                              </div>

                              {isSelected && (
                                <span style={{ color: "var(--accent)", fontWeight: 700, fontSize: "1rem" }}>
                                  ✓
                                </span>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>,
          document.body
        )}
    </div>
  );
}
