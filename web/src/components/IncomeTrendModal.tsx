import { useId, useMemo, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import type { IncomeTrend, Overview } from "../api";
import { formatMoney, monthLabel } from "../format";
import { useBackdropClose, useModalChrome } from "../hooks/useModalChrome";

type Props = {
  open: boolean;
  loading: boolean;
  error: string | null;
  trend: IncomeTrend | null;
  overview: Overview;
  onClose: () => void;
};

function momDetail(overview: Overview): ReactNode {
  const { summary: { income }, month_comparison: { previous_income: previous, income_change_pct: changePct }, currency } = overview;

  if (income <= 0 && previous > 0) {
    return (
      <>
        No income posted yet · last month {formatMoney(previous, currency)}
      </>
    );
  }
  if (changePct == null || Number.isNaN(changePct)) {
    return <>vs last month —</>;
  }
  if (Math.abs(changePct) < 0.05) {
    return <>Flat vs last month ({formatMoney(previous, currency)})</>;
  }
  const up = changePct > 0;
  const abs = Math.abs(changePct).toLocaleString(undefined, { maximumFractionDigits: 1 });
  return (
    <span className={up ? "metric-delta up" : "metric-delta down"}>
      {up ? "Up" : "Down"} {abs}% from last month ({formatMoney(previous, currency)})
    </span>
  );
}

function IncomeLineChart({ trend }: { trend: IncomeTrend }) {
  const width = 640;
  const height = 280;
  const pad = { top: 24, right: 20, bottom: 40, left: 64 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const points = trend.points;
  const maxY = Math.max(1, ...points.map((p) => p.income));
  const niceMax = Math.ceil(maxY / 50000) * 50000 || maxY;

  const coords = useMemo(() => {
    if (points.length === 0) return [];
    return points.map((p, i) => {
      const x =
        points.length === 1
          ? pad.left + innerW / 2
          : pad.left + (i / (points.length - 1)) * innerW;
      const y = pad.top + innerH - (p.income / niceMax) * innerH;
      return { ...p, x, y };
    });
  }, [points, innerW, innerH, niceMax, pad.left, pad.top]);

  const linePath = coords.map((c, i) => `${i === 0 ? "M" : "L"} ${c.x} ${c.y}`).join(" ");
  const areaPath =
    coords.length > 0
      ? `${linePath} L ${coords[coords.length - 1].x} ${pad.top + innerH} L ${coords[0].x} ${pad.top + innerH} Z`
      : "";

  const ticks = [0, 0.5, 1].map((t) => niceMax * t);

  return (
    <svg className="income-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Income trend">
      {ticks.map((tick) => {
        const y = pad.top + innerH - (tick / niceMax) * innerH;
        return (
          <g key={tick}>
            <line
              x1={pad.left}
              x2={pad.left + innerW}
              y1={y}
              y2={y}
              className="income-chart-grid"
            />
            <text x={pad.left - 10} y={y + 4} textAnchor="end" className="income-chart-axis">
              {tick === 0 ? "0" : formatMoney(tick, trend.currency).replace(/\.00$/, "")}
            </text>
          </g>
        );
      })}

      {areaPath && <path d={areaPath} className="income-chart-area" />}
      {linePath && <path d={linePath} className="income-chart-line" />}

      {coords.map((c) => (
        <g key={`${c.year}-${c.month}`}>
          <circle cx={c.x} cy={c.y} r={5} className="income-chart-dot" />
          <title>
            {c.label}: {formatMoney(c.income, trend.currency)}
          </title>
          <text x={c.x} y={height - 14} textAnchor="middle" className="income-chart-axis">
            {c.label.split(" ")[0]}
          </text>
        </g>
      ))}
    </svg>
  );
}

export default function IncomeTrendModal({
  open,
  loading,
  error,
  trend,
  overview,
  onClose,
}: Props) {
  const titleId = useId();
  const closeRef = useRef<HTMLButtonElement>(null);

  useModalChrome(open, onClose, closeRef);
  const onBackdropClick = useBackdropClose(open, onClose);

  if (!open) return null;

  const hasData = Boolean(trend?.points.some((p) => p.income > 0));
  const month = monthLabel(overview.period.year, overview.period.month);

  return createPortal(
    <div className="modal-backdrop" role="presentation" onClick={onBackdropClick}>
      <div
        className="modal-panel income-trend-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onClick={(e) => e.stopPropagation()}
      >
        <header className="modal-header" style={{ padding: "24px 32px", borderBottom: "1px solid var(--line)", alignItems: "flex-start" }}>
          <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
            <div style={{ width: 44, height: 44, borderRadius: "50%", background: "var(--accent-soft)", color: "var(--accent)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
              <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 2v20"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>
            </div>
            <div>
              <h2 id={titleId} style={{ margin: 0, fontSize: "1.25rem", fontWeight: 700, color: "var(--ink)" }}>Income</h2>
              <div style={{ margin: "4px 0 0 0", color: "var(--ink-muted)", fontSize: "0.875rem", display: "flex", flexDirection: "column", gap: 2 }}>
                <span>This Month · {month} · {formatMoney(overview.summary.income, overview.currency)}</span>
                <span>{momDetail(overview)}</span>
                <span>Salary only · late-month credit counts for next month</span>
              </div>
            </div>
          </div>
          <div className="modal-actions" style={{ alignSelf: "flex-start", marginTop: 4 }}>
            <button ref={closeRef} type="button" className="btn icon-btn" onClick={onClose} aria-label="Close modal">
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
            </button>
          </div>
        </header>
        <div className="modal-body" style={{ display: "flex", flexDirection: "column", gap: 24, padding: "32px" }}>
          {loading && <p className="empty">Loading trend…</p>}
          {error && <p className="error">{error}</p>}
          {!loading && !error && trend && !hasData && (
            <p className="empty">No income classified in the last 6 months yet.</p>
          )}
          {!loading && !error && trend && hasData && (
            <>
              <h3 className="income-trend-subtitle">Last 6 months (pay period)</h3>
              <IncomeLineChart trend={trend} />
              <div className="income-trend-legend">
                {trend.points.map((p) => (
                  <div key={`${p.year}-${p.month}`} className="income-trend-legend-row">
                    <span>{p.label}</span>
                    <strong>{formatMoney(p.income, trend.currency)}</strong>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}
