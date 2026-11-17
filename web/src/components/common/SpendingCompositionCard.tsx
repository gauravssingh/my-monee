import SurfaceCard from "./SurfaceCard";
import { formatMoney } from "../../format";

export interface SpendingCompositionCardProps {
  totalSpent: number;
  currency: string;
  consumerSpent: number;
  commitmentsSpent: number;
  spentChangePct: number | null;
  prevMonthName?: string;
  periodLabel?: string;
  onViewTrend?: () => void;
  className?: string;
}

export default function SpendingCompositionCard({
  totalSpent,
  currency,
  consumerSpent,
  commitmentsSpent,
  spentChangePct,
  prevMonthName,
  periodLabel = "this month",
  onViewTrend,
  className = "",
}: SpendingCompositionCardProps) {
  // Ensure non-negative numbers and avoid division by zero
  const safeTotal = Math.max(0, totalSpent);
  const safeConsumer = Math.max(0, consumerSpent);
  const safeCommitments = Math.max(0, commitmentsSpent);

  // Proportions
  const consumerPct = safeTotal > 0 ? (safeConsumer / safeTotal) * 100 : 0;
  const commitmentsPct = safeTotal > 0 ? (safeCommitments / safeTotal) * 100 : 0;

  // Clamped percentages for visual bar
  const consumerBarWidth = Math.min(100, Math.max(0, consumerPct));
  const commitmentsBarWidth = Math.min(100, Math.max(0, commitmentsPct));

  // Change indicator
  const hasChange = spentChangePct != null && !Number.isNaN(spentChangePct);
  const isLess = hasChange && spentChangePct < 0;
  const isMore = hasChange && spentChangePct > 0;
  const absPct = hasChange ? Math.abs(spentChangePct).toFixed(1) : null;

  return (
    <SurfaceCard
      variant="hero"
      padding="lg"
      className={`spending-composition-card ${className}`.trim()}
    >
      <div className="spending-card-header">
        <div className="spending-card-title-group">
          <span className="spending-card-eyebrow">Spending {periodLabel}</span>
          <div className="spending-card-amount-wrap">
            <span className="spending-card-amount">
              {formatMoney(safeTotal, currency)}
            </span>
            {onViewTrend && (
              <button
                type="button"
                className="spending-card-trend-btn"
                onClick={onViewTrend}
                title="View spending trend analysis"
                aria-label="View spending trend analysis"
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <line x1="7" y1="17" x2="17" y2="7" />
                  <polyline points="7 7 17 7 17 17" />
                </svg>
              </button>
            )}
          </div>
        </div>

        {hasChange && (
          <div className={`spending-card-pill ${isLess ? "favorable" : isMore ? "unfavorable" : "neutral"}`}>
            <span className="spending-card-pill-arrow">{isLess ? "↓" : isMore ? "↑" : "•"}</span>
            <span>
              {absPct}% {isLess ? "less" : isMore ? "more" : "change"}
              {prevMonthName ? ` vs ${prevMonthName}` : " vs last month"}
            </span>
          </div>
        )}
      </div>

      {/* Proportional Segmented Track */}
      {safeTotal > 0 && (
        <div
          className="spending-track-composite"
          role="progressbar"
          aria-label={`Spending breakdown: ${consumerPct.toFixed(0)}% living expenses, ${commitmentsPct.toFixed(0)}% loan commitments`}
          aria-valuenow={100}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          {consumerBarWidth > 0 && (
            <div
              className="spending-track-segment teal"
              style={{ width: `${consumerBarWidth}%` }}
              title={`Living Spending: ${formatMoney(safeConsumer, currency)} (${consumerPct.toFixed(1)}%)`}
            />
          )}
          {commitmentsBarWidth > 0 && (
            <div
              className="spending-track-segment orange"
              style={{ width: `${commitmentsBarWidth}%` }}
              title={`Commitments & Loans: ${formatMoney(safeCommitments, currency)} (${commitmentsPct.toFixed(1)}%)`}
            />
          )}
        </div>
      )}

      {/* Breakdown Rows */}
      <div className="spending-breakdown-rows">
        {/* Living / Consumer Expenses */}
        <div className="spending-breakdown-row">
          <div className="spending-row-label-group">
            <span className="spending-row-dot teal" />
            <div className="spending-row-text">
              <span className="spending-row-name">Consumer & Living Spending</span>
              <span className="spending-row-sub">Everyday expenses & lifestyle</span>
            </div>
          </div>
          <div className="spending-row-bar-wrap">
            <div className="spending-row-bar-track">
              <div
                className="spending-row-bar-fill teal"
                style={{ width: `${consumerBarWidth}%` }}
              />
            </div>
          </div>
          <div className="spending-row-value-group">
            <span className="spending-row-amount">
              {formatMoney(safeConsumer, currency)}
            </span>
            <span className="spending-row-pct">
              {consumerPct.toFixed(1)}%
            </span>
          </div>
        </div>

        {/* Financial Commitments & Loans */}
        <div className="spending-breakdown-row">
          <div className="spending-row-label-group">
            <span className="spending-row-dot orange" />
            <div className="spending-row-text">
              <span className="spending-row-name">Financial Commitments & Loans</span>
              <span className="spending-row-sub">EMI, loan payments, fixed obligations</span>
            </div>
          </div>
          <div className="spending-row-bar-wrap">
            <div className="spending-row-bar-track">
              <div
                className="spending-row-bar-fill orange"
                style={{ width: `${commitmentsBarWidth}%` }}
              />
            </div>
          </div>
          <div className="spending-row-value-group">
            <span className="spending-row-amount">
              {formatMoney(safeCommitments, currency)}
            </span>
            <span className="spending-row-pct">
              {commitmentsPct.toFixed(1)}%
            </span>
          </div>
        </div>
      </div>
    </SurfaceCard>
  );
}
