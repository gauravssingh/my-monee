import { useId, useMemo, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import type { FinancialTrends, Overview } from "../api";
import { formatMoney } from "../format";
import { useBackdropClose, useModalChrome } from "../hooks/useModalChrome";

export type TrendMetricType = "spent" | "income" | "cash_flow";

type Props = {
  open: boolean;
  loading: boolean;
  error: string | null;
  trends: FinancialTrends | null;
  overview: Overview;
  initialMetric?: TrendMetricType;
  onClose: () => void;
};

function momSummary(overview: Overview, metric: TrendMetricType): ReactNode {
  const { summary, month_comparison, currency } = overview;

  if (metric === "spent") {
    const change = month_comparison.spent_change_pct;
    const prev = month_comparison.previous_spent;
    if (change == null || Number.isNaN(change)) return <span>vs last month —</span>;
    const up = change > 0;
    const abs = Math.abs(change).toFixed(1);
    return (
      <span className={up ? "metric-delta down" : "metric-delta up"}>
        {up ? "Up" : "Down"} {abs}% from last month ({formatMoney(prev, currency)})
      </span>
    );
  }

  if (metric === "income") {
    const change = month_comparison.income_change_pct;
    const prev = month_comparison.previous_income;
    if (summary.income <= 0 && prev > 0) {
      return <span>No income posted yet · last month {formatMoney(prev, currency)}</span>;
    }
    if (change == null || Number.isNaN(change)) return <span>vs last month —</span>;
    const up = change >= 0;
    const abs = Math.abs(change).toFixed(1);
    return (
      <span className={up ? "metric-delta up" : "metric-delta down"}>
        {up ? "Up" : "Down"} {abs}% from last month ({formatMoney(prev, currency)})
      </span>
    );
  }

  // cash_flow
  const current = summary.net_cash_flow;
  const prev = month_comparison.previous_income - month_comparison.previous_spent;
  const diff = current - prev;
  const up = diff >= 0;
  return (
    <span className={up ? "metric-delta up" : "metric-delta down"}>
      {up ? "+" : "−"}{formatMoney(Math.abs(diff), currency)} vs last month ({prev >= 0 ? "+" : ""}{formatMoney(prev, currency)})
    </span>
  );
}

function TrendChart({
  trends,
  metric,
}: {
  trends: FinancialTrends;
  metric: TrendMetricType;
}) {
  const width = 600;
  const height = 240;
  const pad = { top: 24, right: 24, bottom: 36, left: 64 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const points = trends.points;

  const values = points.map((p) => {
    if (metric === "spent") return p.spent;
    if (metric === "income") return p.income;
    return p.net_cash_flow;
  });

  const minVal = Math.min(0, ...values);
  const maxVal = Math.max(1000, ...values);
  const range = maxVal - minVal || 1;

  const coords = useMemo(() => {
    if (points.length === 0) return [];
    return points.map((p, i) => {
      const val =
        metric === "spent"
          ? p.spent
          : metric === "income"
          ? p.income
          : p.net_cash_flow;
      const x =
        points.length === 1
          ? pad.left + innerW / 2
          : pad.left + (i / (points.length - 1)) * innerW;
      const y = pad.top + innerH - ((val - minVal) / range) * innerH;
      return { ...p, val, x, y };
    });
  }, [points, metric, innerW, innerH, minVal, range, pad.left, pad.top]);

  const linePath = coords.map((c, i) => `${i === 0 ? "M" : "L"} ${c.x.toFixed(1)} ${c.y.toFixed(1)}`).join(" ");
  
  const zeroY = pad.top + innerH - ((0 - minVal) / range) * innerH;
  const areaPath =
    coords.length > 0
      ? `${linePath} L ${coords[coords.length - 1].x.toFixed(1)} ${zeroY.toFixed(1)} L ${coords[0].x.toFixed(1)} ${zeroY.toFixed(1)} Z`
      : "";

  const strokeColor =
    metric === "spent"
      ? "var(--debit)"
      : metric === "income"
      ? "var(--credit)"
      : "var(--accent)";

  const fillColor =
    metric === "spent"
      ? "var(--debit-soft)"
      : metric === "income"
      ? "var(--credit-soft)"
      : "var(--accent-soft)";

  return (
    <svg
      style={{ width: "100%", height: "auto", overflow: "visible" }}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={`${metric} trend chart`}
    >
      {/* Zero baseline */}
      {minVal < 0 && (
        <line
          x1={pad.left}
          x2={pad.left + innerW}
          y1={zeroY}
          y2={zeroY}
          stroke="var(--line)"
          strokeDasharray="4 4"
        />
      )}

      {/* Grid Lines */}
      {[0, 0.5, 1].map((ratio) => {
        const val = minVal + ratio * range;
        const y = pad.top + innerH - ratio * innerH;
        return (
          <g key={ratio}>
            <line
              x1={pad.left}
              x2={pad.left + innerW}
              y1={y}
              y2={y}
              stroke="var(--line)"
              strokeOpacity={0.6}
            />
            <text
              x={pad.left - 10}
              y={y + 4}
              textAnchor="end"
              style={{ fontSize: "0.75rem", fill: "var(--ink-muted)", fontVariantNumeric: "tabular-nums" }}
            >
              {formatMoney(val, trends.currency).replace(/\.00$/, "")}
            </text>
          </g>
        );
      })}

      {areaPath && <path d={areaPath} fill={fillColor} />}
      {linePath && (
        <path
          d={linePath}
          fill="none"
          stroke={strokeColor}
          strokeWidth={2.5}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      )}

      {coords.map((c) => (
        <g key={`${c.year}-${c.month}`}>
          <circle
            cx={c.x}
            cy={c.y}
            r={5}
            fill="var(--surface)"
            stroke={strokeColor}
            strokeWidth={2.5}
          />
          <title>
            {c.label}: {formatMoney(c.val, trends.currency)}
          </title>
          <text
            x={c.x}
            y={height - 12}
            textAnchor="middle"
            style={{ fontSize: "0.75rem", fill: "var(--ink-muted)" }}
          >
            {c.label.split(" ")[0]}
          </text>
        </g>
      ))}
    </svg>
  );
}

export default function FinancialTrendModal({
  open,
  loading,
  error,
  trends,
  overview,
  initialMetric = "spent",
  onClose,
}: Props) {
  const [activeMetric, setActiveMetric] = useState<TrendMetricType>(initialMetric);
  const panelRef = useRef<HTMLDivElement>(null);
  const titleId = useId();

  useModalChrome(open, onClose);
  const handleBackdropClick = useBackdropClose(open, onClose);

  // Sync initialMetric when modal opens
  useMemo(() => {
    if (open) setActiveMetric(initialMetric);
  }, [open, initialMetric]);

  if (!open) return null;

  const metricTitles: Record<TrendMetricType, { title: string; subtitle: string }> = {
    spent: {
      title: "Monthly Spending Trend",
      subtitle: "6-month total expense trajectory across all debit activity",
    },
    income: {
      title: "Monthly Income Trend",
      subtitle: "6-month net pay and cash inflow attribution",
    },
    cash_flow: {
      title: "Net Cash Flow Trend",
      subtitle: "6-month cash surplus or deficit (Income − Spending)",
    },
  };

  const currentVal =
    activeMetric === "spent"
      ? overview.summary.spent
      : activeMetric === "income"
      ? overview.summary.income
      : overview.summary.net_cash_flow;

  return createPortal(
    <div className="modal-backdrop" onClick={handleBackdropClick} role="presentation">
      <div
        ref={panelRef}
        className="modal-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        style={{ width: "min(680px, 100%)", display: "flex", flexDirection: "column" }}
      >
        <div className="sheet-handle" onClick={onClose} aria-label="Dismiss sheet" />

        <header
          className="modal-header"
          style={{
            padding: "16px 20px 14px",
            borderBottom: "1px solid var(--line)",
            position: "sticky",
            top: 0,
            zIndex: 10,
            background: "var(--surface)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <div style={{ display: "flex", gap: 12, alignItems: "center", minWidth: 0 }}>
            <div
              style={{
                width: 36,
                height: 36,
                borderRadius: "50%",
                background:
                  activeMetric === "spent"
                    ? "var(--debit-soft)"
                    : activeMetric === "income"
                    ? "var(--credit-soft)"
                    : "var(--accent-soft)",
                color:
                  activeMetric === "spent"
                    ? "var(--debit)"
                    : activeMetric === "income"
                    ? "var(--credit)"
                    : "var(--accent)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
              }}
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="22 7 13.5 15.5 8.5 10.5 2 17" />
                <polyline points="16 7 22 7 22 13" />
              </svg>
            </div>
            <div style={{ minWidth: 0 }}>
              <h2 id={titleId} style={{ margin: 0, fontSize: "1.1rem", fontWeight: 700, color: "var(--ink)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                {metricTitles[activeMetric].title}
              </h2>
              <p style={{ margin: "2px 0 0", color: "var(--ink-muted)", fontSize: "0.8rem", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                {metricTitles[activeMetric].subtitle}
              </p>
            </div>
          </div>
          <button
            type="button"
            className="btn icon-btn"
            onClick={onClose}
            aria-label="Close modal"
            style={{ width: 36, height: 36, display: "inline-flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
          </button>
        </header>

        <div
          className="modal-body"
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 16,
            padding: "16px 20px",
            overflowY: "auto",
            flex: 1,
            WebkitOverflowScrolling: "touch",
          }}
        >
          {/* Metric Selector Tabs */}
          <div className="segmented" style={{ width: "100%" }}>
            <button
              type="button"
              className={`segmented-btn${activeMetric === "spent" ? " active" : ""}`}
              onClick={() => setActiveMetric("spent")}
            >
              Total Spent
            </button>
            <button
              type="button"
              className={`segmented-btn${activeMetric === "income" ? " active" : ""}`}
              onClick={() => setActiveMetric("income")}
            >
              Income
            </button>
            <button
              type="button"
              className={`segmented-btn${activeMetric === "cash_flow" ? " active" : ""}`}
              onClick={() => setActiveMetric("cash_flow")}
            >
              Net Cash Flow
            </button>
          </div>

          {/* Current Month Highlights */}
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "baseline",
              padding: "12px 14px",
              background: "var(--bg)",
              borderRadius: "var(--radius-sm)",
              border: "1px solid var(--line)",
            }}
          >
            <div>
              <div style={{ fontSize: "0.72rem", textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--ink-muted)", fontWeight: 600 }}>
                Selected Month
              </div>
              <div
                style={{
                  fontSize: "1.35rem",
                  fontWeight: 700,
                  color:
                    activeMetric === "spent"
                      ? "var(--ink)"
                      : activeMetric === "income"
                      ? "var(--credit)"
                      : currentVal >= 0
                      ? "var(--credit)"
                      : "var(--debit)",
                }}
              >
                {activeMetric === "cash_flow" && currentVal >= 0 ? "+" : ""}
                {formatMoney(currentVal, overview.currency)}
              </div>
            </div>
            <div style={{ fontSize: "0.82rem", textAlign: "right" }}>
              {momSummary(overview, activeMetric)}
            </div>
          </div>

          {loading && <p className="empty">Loading 6-month historical trend…</p>}
          {error && <p className="error">{error}</p>}

          {!loading && !error && trends && (
            <>
              {/* Chart */}
              <div
                style={{
                  background: "var(--surface)",
                  border: "1px solid var(--line)",
                  borderRadius: "var(--radius)",
                  padding: "12px 10px 6px",
                }}
              >
                <TrendChart trends={trends} metric={activeMetric} />
              </div>

              {/* Breakdown History Table */}
              <div>
                <h3 style={{ margin: "0 0 8px", fontSize: "0.78rem", textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--ink-muted)" }}>
                  6-Month History
                </h3>
                <div style={{ border: "1px solid var(--line)", borderRadius: "var(--radius)", overflow: "hidden" }}>
                  <table style={{ minWidth: "100%", margin: 0 }}>
                    <thead>
                      <tr>
                        <th>Month</th>
                        <th style={{ textAlign: "right" }}>
                          {activeMetric === "spent" ? "Spent" : activeMetric === "income" ? "Income" : "Cash Flow"}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {trends.points.slice().reverse().map((p) => {
                        const val =
                          activeMetric === "spent"
                            ? p.spent
                            : activeMetric === "income"
                            ? p.income
                            : p.net_cash_flow;
                        return (
                          <tr key={`${p.year}-${p.month}`}>
                            <td style={{ fontWeight: 500 }}>{p.label}</td>
                            <td
                              style={{
                                textAlign: "right",
                                fontWeight: 600,
                                fontVariantNumeric: "tabular-nums",
                                color:
                                  activeMetric === "spent"
                                    ? "var(--ink)"
                                    : activeMetric === "income"
                                    ? "var(--credit)"
                                    : val >= 0
                                    ? "var(--credit)"
                                    : "var(--debit)",
                              }}
                            >
                              {activeMetric === "cash_flow" && val >= 0 ? "+" : ""}
                              {formatMoney(val, trends.currency)}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}
        </div>

        {/* Dedicated Close Footer */}
        <footer
          style={{
            padding: "10px 20px calc(10px + var(--sab))",
            borderTop: "1px solid var(--line)",
            background: "var(--surface)",
            display: "flex",
            justifyContent: "flex-end",
            alignItems: "center",
          }}
        >
          <button
            type="button"
            className="btn primary"
            onClick={onClose}
            style={{ width: "100%", padding: "10px 16px", fontSize: "0.92rem", fontWeight: 600 }}
          >
            Done
          </button>
        </footer>
      </div>
    </div>,
    document.body
  );
}
