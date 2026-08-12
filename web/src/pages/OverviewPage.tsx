import { useEffect, useState } from "react";
import { api, type CategorySpend, type IncomeTrend, type Overview } from "../api";
import IncomeTrendModal from "../components/IncomeTrendModal";
import { formatMoney, monthLabel } from "../format";

export default function OverviewPage() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [categories, setCategories] = useState<CategorySpend[]>([]);
  const [catYear, setCatYear] = useState<number | null>(null);
  const [catMonth, setCatMonth] = useState<number | null>(null);
  const [catLoading, setCatLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [trendOpen, setTrendOpen] = useState(false);
  const [trendLoading, setTrendLoading] = useState(false);
  const [trendError, setTrendError] = useState<string | null>(null);
  const [trend, setTrend] = useState<IncomeTrend | null>(null);

  useEffect(() => {
    let cancelled = false;
    api.overview()
      .then((o) => {
        if (cancelled) return;
        setOverview(o);
        setCatYear(o.period.year);
        setCatMonth(o.period.month);
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!catYear || !catMonth) return;
    let cancelled = false;
    setCatLoading(true);
    api.byCategory(catYear, catMonth)
      .then((c) => {
        if (cancelled) return;
        setCategories(c.items);
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setCatLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [catYear, catMonth]);

  function prevMonth() {
    if (!catYear || !catMonth) return;
    if (catMonth === 1) {
      setCatMonth(12);
      setCatYear(catYear - 1);
    } else {
      setCatMonth(catMonth - 1);
    }
  }

  function nextMonth() {
    if (!catYear || !catMonth) return;
    if (catMonth === 12) {
      setCatMonth(1);
      setCatYear(catYear + 1);
    } else {
      setCatMonth(catMonth + 1);
    }
  }

  const openIncomeTrend = () => {
    setTrendOpen(true);
    setTrendLoading(true);
    setTrendError(null);
    api
      .incomeTrend(6)
      .then((data) => setTrend(data))
      .catch((err: Error) => setTrendError(err.message))
      .finally(() => setTrendLoading(false));
  };

  if (error) return <p className="error">Could not load overview: {error}</p>;
  if (!overview) return <p className="empty">Loading overview…</p>;

  const regularCategories = categories.filter((c) => c.total > 0 && c.category !== "Loans");
  const loansCategory = categories.find((c) => c.category === "Loans" && c.total > 0);
  const maxCategory = Math.max(1, ...regularCategories.map((c) => c.total), 1);

  return (
    <>
      <section className="metrics">
        <article className="panel metric">
          <div className="metric-label">This month</div>
          <div className="metric-value">
            {formatMoney(overview.current_month_spending, overview.currency)}
          </div>
          <div className="metric-hint">{monthLabel(overview.period.year, overview.period.month)}</div>
        </article>
        <article className="panel metric">
          <div className="metric-label">Previous month</div>
          <div className="metric-value">
            {formatMoney(overview.previous_month_spending, overview.currency)}
          </div>
          <div className="metric-hint">Spending</div>
        </article>
        <button
          type="button"
          className="panel metric metric-button"
          onClick={openIncomeTrend}
          aria-label="Open income details"
        >
          <div className="metric-label">Income</div>
          <div className="metric-value">{formatMoney(overview.income, overview.currency)}</div>
          <div className="metric-hint">
            This Month · {monthLabel(overview.period.year, overview.period.month)}
          </div>
        </button>
        <article className="panel metric">
          <div className="metric-label">Net cash flow</div>
          <div className="metric-value">{formatMoney(overview.net_cash_flow, overview.currency)}</div>
          <div className="metric-hint">Income − spending</div>
        </article>
        <article className="panel metric">
          <div className="metric-label">Transactions</div>
          <div className="metric-value">{overview.transaction_count}</div>
          <div className="metric-hint">
            {monthLabel(overview.period.year, overview.period.month)} ·{" "}
            {overview.needs_review_count} need review (all time)
          </div>
        </article>
        <article className="panel metric">
          <div className="metric-label">Largest</div>
          <div className="metric-value">
            {overview.largest_transaction
              ? formatMoney(overview.largest_transaction.amount, overview.currency)
              : "—"}
          </div>
          <div className="metric-hint">
            {overview.largest_transaction?.merchant ?? "No transactions yet"}
          </div>
        </article>
      </section>

      <div className="grid-2">
        <section className="panel section" style={{ display: "flex", flexDirection: "column" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
            <h2 style={{ margin: 0 }}>Spending by category</h2>
            {catYear && catMonth && (
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <button className="btn quiet" onClick={prevMonth} disabled={catLoading}>&larr; Prev</button>
                <strong style={{ minWidth: 100, textAlign: "center" }}>{monthLabel(catYear, catMonth)}</strong>
                <button className="btn quiet" onClick={nextMonth} disabled={catLoading}>Next &rarr;</button>
              </div>
            )}
          </div>
          <p className="lead">Category totals for the selected month.</p>
          {regularCategories.length === 0 && !loansCategory ? (
            <div className="empty">No categorized spending yet. Connect Gmail in Phase 2.</div>
          ) : (
            <>
              {regularCategories.length > 0 && (
                <div className="category-list">
                  {regularCategories.map((c) => (
                    <div className="category-row" key={c.category_id}>
                      <div className="category-name">{c.category}</div>
                      <div className="bar-track">
                        <div
                          className="bar-fill"
                          style={{ width: `${(c.total / maxCategory) * 100}%` }}
                        />
                      </div>
                      <div className="category-total">{formatMoney(c.total)}</div>
                    </div>
                  ))}
                </div>
              )}
              {loansCategory && (
                <div style={{ marginTop: 24, paddingTop: 16, borderTop: "1px solid var(--border)" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <div style={{ fontWeight: 600, color: "var(--text-secondary)" }}>{loansCategory.category} (Recurring)</div>
                    <div style={{ fontWeight: 600 }}>{formatMoney(loansCategory.total)}</div>
                  </div>
                </div>
              )}
            </>
          )}
        </section>

        <section className="panel section">
          <h2>What comes next</h2>
          <p className="lead">Gmail ingestion is live. Connect under Settings, or run demo emails.</p>
          <div className="status-grid">
            <div className="status-row">
              <div className="status-key">Phase 2</div>
              <div>OAuth, discovery, parsers — available now</div>
            </div>
            <div className="status-row">
              <div className="status-key">Phase 3</div>
              <div>Dedupe hardening, refunds, transfers</div>
            </div>
            <div className="status-row">
              <div className="status-key">Phase 4</div>
              <div>Personal classification + learning loop</div>
            </div>
          </div>
        </section>
      </div>

      <IncomeTrendModal
        open={trendOpen}
        loading={trendLoading}
        error={trendError}
        trend={trend}
        overview={overview}
        onClose={() => setTrendOpen(false)}
      />
    </>
  );
}
