import SurfaceCard from "./SurfaceCard";
import { formatMoney } from "../../format";

export interface SpendingCompositionCardProps {
  totalSpent: number;
  currency: string;
  consumerSpent?: number | null;
  commitmentsSpent?: number | null;
  spentChangePct: number | null;
  prevMonthName?: string;
  periodLabel?: string;
  onViewTrend?: () => void;
  className?: string;
}

export interface SpendingCompositionBreakdown {
  safeTotal: number;
  safeConsumer: number;
  safeCommitments: number;
  allocatedSum: number;
  effectiveTotal: number;
  unallocatedAmount: number;
  consumerPct: number;
  commitmentsPct: number;
  unallocatedPct: number;
  consumerBarWidth: number;
  commitmentsBarWidth: number;
  unallocatedBarWidth: number;
  accessibleCompositionLabel: string;
}

export function computeSpendingComposition(
  totalSpent: number | null | undefined,
  consumerSpent: number | null | undefined,
  commitmentsSpent: number | null | undefined,
): SpendingCompositionBreakdown {
  // Preserve explicit zero values using nullish coalescing
  const safeTotal = Math.max(0, totalSpent ?? 0);
  const safeConsumer = Math.max(0, consumerSpent ?? 0);
  const safeCommitments = Math.max(0, commitmentsSpent ?? 0);

  // Validate composition totals against total spending
  const allocatedSum = safeConsumer + safeCommitments;
  const effectiveTotal = Math.max(safeTotal, allocatedSum);
  const unallocatedAmount = safeTotal > allocatedSum ? safeTotal - allocatedSum : 0;

  // Proportions
  const consumerPct = effectiveTotal > 0 ? (safeConsumer / effectiveTotal) * 100 : 0;
  const commitmentsPct = effectiveTotal > 0 ? (safeCommitments / effectiveTotal) * 100 : 0;
  const unallocatedPct =
    effectiveTotal > 0 && unallocatedAmount > 0.01 ? (unallocatedAmount / effectiveTotal) * 100 : 0;

  // Clamped percentages for visual bar
  const consumerBarWidth = Math.min(100, Math.max(0, consumerPct));
  const commitmentsBarWidth = Math.min(100, Math.max(0, commitmentsPct));
  const unallocatedBarWidth = Math.min(100, Math.max(0, unallocatedPct));

  const accessibleCompositionLabel = `Spending composition: ${consumerPct.toFixed(1)}% consumer and living spending, ${commitmentsPct.toFixed(1)}% financial commitments and loans${unallocatedPct > 0.01 ? `, ${unallocatedPct.toFixed(1)}% other outflows` : ""}`;

  return {
    safeTotal,
    safeConsumer,
    safeCommitments,
    allocatedSum,
    effectiveTotal,
    unallocatedAmount,
    consumerPct,
    commitmentsPct,
    unallocatedPct,
    consumerBarWidth,
    commitmentsBarWidth,
    unallocatedBarWidth,
    accessibleCompositionLabel,
  };
}

export default function SpendingCompositionCard({
  totalSpent,
  currency,
  consumerSpent,
  commitmentsSpent,
  spentChangePct,
  prevMonthName = "last month",
  periodLabel = "This Month",
  onViewTrend,
  className = "",
}: SpendingCompositionCardProps) {
  const {
    safeTotal,
    safeConsumer,
    safeCommitments,
    effectiveTotal,
    unallocatedAmount,
    consumerPct,
    commitmentsPct,
    unallocatedPct,
    consumerBarWidth,
    commitmentsBarWidth,
    unallocatedBarWidth,
    accessibleCompositionLabel,
  } = computeSpendingComposition(totalSpent, consumerSpent, commitmentsSpent);

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
      {/* Card Header & Primary Total */}
      <div className="spending-card-header">
        <div className="spending-card-title-group">
          <div className="spending-card-eyebrow">
            <span>Total Outflows · {periodLabel}</span>
            {onViewTrend && (
              <button
                type="button"
                className="spending-card-trend-btn"
                onClick={onViewTrend}
                title="View 6-month spending trend"
                aria-label="View 6-month spending trend"
              >
                Trend
                <svg
                  width="13"
                  height="13"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  <line x1="7" y1="17" x2="17" y2="7" />
                  <polyline points="7 7 17 7 17 17" />
                </svg>
              </button>
            )}
          </div>
          <div className="spending-card-hero-amount">
            {formatMoney(safeTotal, currency)}
          </div>
        </div>

        {hasChange && (
          <div className={`spending-card-pill ${isLess ? "favorable" : isMore ? "unfavorable" : "neutral"}`}>
            <span className="pill-arrow" aria-hidden="true">
              {isLess ? "↓" : isMore ? "↑" : "→"}
            </span>
            <span className="pill-text">
              {absPct}% vs {prevMonthName}
            </span>
          </div>
        )}
      </div>

      {/* Proportional Segmented Track with Accessible Semantics */}
      {effectiveTotal > 0 && (
        <div
          className="spending-track-composite"
          role="group"
          aria-label={accessibleCompositionLabel}
        >
          {consumerBarWidth > 0 && (
            <div
              className="spending-track-segment teal"
              style={{ width: `${consumerBarWidth}%` }}
              role="meter"
              aria-label="Consumer & Living Spending"
              aria-valuenow={Math.round(consumerPct)}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuetext={`${formatMoney(safeConsumer, currency)} (${consumerPct.toFixed(1)}%)`}
              title={`Living Spending: ${formatMoney(safeConsumer, currency)} (${consumerPct.toFixed(1)}%)`}
            />
          )}
          {commitmentsBarWidth > 0 && (
            <div
              className="spending-track-segment orange"
              style={{ width: `${commitmentsBarWidth}%` }}
              role="meter"
              aria-label="Financial Commitments & Loans"
              aria-valuenow={Math.round(commitmentsPct)}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuetext={`${formatMoney(safeCommitments, currency)} (${commitmentsPct.toFixed(1)}%)`}
              title={`Commitments & Loans: ${formatMoney(safeCommitments, currency)} (${commitmentsPct.toFixed(1)}%)`}
            />
          )}
          {unallocatedBarWidth > 0 && (
            <div
              className="spending-track-segment neutral"
              style={{ width: `${unallocatedBarWidth}%` }}
              role="meter"
              aria-label="Other Outflows"
              aria-valuenow={Math.round(unallocatedPct)}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuetext={`${formatMoney(unallocatedAmount, currency)} (${unallocatedPct.toFixed(1)}%)`}
              title={`Other Outflows: ${formatMoney(unallocatedAmount, currency)} (${unallocatedPct.toFixed(1)}%)`}
            />
          )}
        </div>
      )}

      {/* Breakdown Detail Rows */}
      <div className="spending-breakdown-rows">
        {/* Living / Consumer Expenses */}
        <div className="spending-breakdown-row">
          <div className="spending-row-label-group">
            <span className="spending-row-dot teal" />
            <div className="spending-row-text">
              <span className="spending-row-name">Living &amp; Consumer Spend</span>
              <span className="spending-row-sub">Food, lifestyle, travel, personal</span>
            </div>
          </div>
          <div className="spending-row-bar-wrap">
            <div
              className="spending-row-bar-track"
              role="meter"
              aria-label="Consumer & Living Spending proportion"
              aria-valuenow={Math.round(consumerPct)}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuetext={`${formatMoney(safeConsumer, currency)}, ${consumerPct.toFixed(1)}% of spending`}
            >
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

        {/* Commitments & Loans */}
        <div className="spending-breakdown-row">
          <div className="spending-row-label-group">
            <span className="spending-row-dot orange" />
            <div className="spending-row-text">
              <span className="spending-row-name">Commitments &amp; Loans</span>
              <span className="spending-row-sub">EMIs, interest, family support, dues</span>
            </div>
          </div>
          <div className="spending-row-bar-wrap">
            <div
              className="spending-row-bar-track"
              role="meter"
              aria-label="Financial Commitments & Loans proportion"
              aria-valuenow={Math.round(commitmentsPct)}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuetext={`${formatMoney(safeCommitments, currency)}, ${commitmentsPct.toFixed(1)}% of spending`}
            >
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

        {/* Unallocated / Other Outflows */}
        {unallocatedAmount > 0.01 && (
          <div className="spending-breakdown-row">
            <div className="spending-row-label-group">
              <span className="spending-row-dot neutral" />
              <div className="spending-row-text">
                <span className="spending-row-name">Other Outflows</span>
                <span className="spending-row-sub">Uncategorized expenses & adjustments</span>
              </div>
            </div>
            <div className="spending-row-bar-wrap">
              <div
                className="spending-row-bar-track"
                role="meter"
                aria-label="Other Outflows proportion"
                aria-valuenow={Math.round(unallocatedPct)}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuetext={`${formatMoney(unallocatedAmount, currency)}, ${unallocatedPct.toFixed(1)}% of spending`}
              >
                <div
                  className="spending-row-bar-fill neutral"
                  style={{ width: `${unallocatedBarWidth}%` }}
                />
              </div>
            </div>
            <div className="spending-row-value-group">
              <span className="spending-row-amount">
                {formatMoney(unallocatedAmount, currency)}
              </span>
              <span className="spending-row-pct">
                {unallocatedPct.toFixed(1)}%
              </span>
            </div>
          </div>
        )}
      </div>
    </SurfaceCard>
  );
}
