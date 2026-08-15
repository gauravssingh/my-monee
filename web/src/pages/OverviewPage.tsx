import { useEffect, useState } from "react";
import { api, type Overview, type AccountsResponse } from "../api";
import { formatMoney, monthLabel } from "../format";

function getPeriodLabel(year: number, month: number) {
  const now = new Date();
  if (year === now.getFullYear() && month === now.getMonth() + 1) {
    return "This Month";
  }
  const startDate = new Date(year, month - 1, 1);
  const endDate = new Date(year, month, 0);
  const startStr = startDate.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
  const endStr = endDate.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
  return `${startStr} – ${endStr}`;
}

export default function OverviewPage() {
  const [date, setDate] = useState(() => {
    const now = new Date();
    return { year: now.getFullYear(), month: now.getMonth() + 1 };
  });
  const [overview, setOverview] = useState<Overview | null>(null);
  const [accounts, setAccounts] = useState<AccountsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAllCategories, setShowAllCategories] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setShowAllCategories(false);
    
    api.overview(date.year, date.month)
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
      
    api.accounts()
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

  if (error) return <p className="error">Could not load overview: {error}</p>;
  if (!overview && loading) return <p className="empty">Loading overview…</p>;
  if (!overview) return null;

  const maxDaily = overview.daily_spending.length > 0 ? Math.max(1, ...overview.daily_spending.map((d) => d.spent)) : 1;
  const avgDaily = overview.daily_spending.length > 0 ? overview.summary.spent / overview.daily_spending.length : 0;

  let biggestIncrease: any = null;
  let biggestDecrease: any = null;
  let maxInc = 0;
  let maxDec = 0;
  
  overview.category_breakdown.forEach(c => {
    const diff = c.total - (c.previous_total || 0);
    if (diff > maxInc) { maxInc = diff; biggestIncrease = c; }
    if (diff < maxDec) { maxDec = diff; biggestDecrease = c; }
  });

  const spendingDiff = overview!.summary.spent - overview!.month_comparison.previous_spent;
  const incomeDiff = overview!.summary.income - overview!.month_comparison.previous_income;

  const consumerCategories = overview.category_breakdown.filter(c => ['essential', 'discretionary'].includes(c.expense_type || ''));
  const otherCategories = overview.category_breakdown.filter(c => ['transfer', 'financial', 'investment'].includes(c.expense_type || ''));
  const uncategorizedCategories = overview.category_breakdown.filter(c => !['essential', 'discretionary', 'transfer', 'financial', 'investment'].includes(c.expense_type || ''));

  function renderCategoryGroup(title: string, cats: Overview["category_breakdown"]) {
    if (cats.length === 0) return null;
    const maxCat = Math.max(1, ...cats.map(c => c.total));
    const displayCats = showAllCategories ? cats : cats.slice(0, 5);
    return (
      <div style={{ marginBottom: "24px" }}>
        <h4 style={{ margin: "0 0 12px", fontSize: "0.95rem", color: "var(--ink-muted)", borderBottom: "1px solid var(--line)", paddingBottom: "4px" }}>{title}</h4>
        <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
          {displayCats.map(c => (
            <div key={c.category_id}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: "0.9rem", marginBottom: "4px" }}>
                <span>{c.category}</span>
                <span>
                  <span style={{ color: 'var(--ink-muted)', marginRight: "8px" }}>{c.percentage.toFixed(1)}%</span>
                  <span style={{ fontWeight: 500 }}>{formatMoney(c.total, overview!.currency)}</span>
                </span>
              </div>
              <div style={{ width: "100%", height: "4px", background: "var(--line)", borderRadius: "2px", overflow: "hidden" }}>
                <div style={{ width: `${(c.total / maxCat) * 100}%`, height: "100%", background: "var(--accent)", borderRadius: "2px" }} />
              </div>
            </div>
          ))}
        </div>
        {!showAllCategories && cats.length > 5 && (
          <div style={{ marginTop: "12px", textAlign: "center" }}>
            <button className="btn quiet" onClick={() => setShowAllCategories(true)} style={{ fontSize: "0.85rem" }}>View all categories</button>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="overview-page" style={{ maxWidth: "1000px", margin: "0 auto", paddingBottom: "48px" }}>
      <header style={{ display: "flex", flexDirection: "column", alignItems: "center", marginBottom: 24 }}>
        <h1 style={{ margin: "0 0 16px", fontSize: "1.5rem" }}>Monthly Analysis</h1>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <button className="btn quiet" onClick={prevMonth} disabled={loading}>&larr; Previous</button>
          <div style={{ textAlign: "center", minWidth: "140px" }}>
            <strong style={{ display: "block", fontSize: "1.1rem" }}>{monthLabel(date.year, date.month)}</strong>
            <span style={{ fontSize: "0.85rem", color: "var(--ink-muted)" }}>{getPeriodLabel(date.year, date.month)}</span>
          </div>
          <button className="btn quiet" onClick={nextMonth} disabled={loading}>Next &rarr;</button>
        </div>
      </header>

      {overview.review.needs_review_count > 0 && (
        <div className="panel" style={{ marginBottom: 24, padding: "12px 16px", display: "flex", justifyContent: "space-between", alignItems: "center", border: "1px solid var(--warn)", background: "var(--bg)", borderRadius: "6px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <span style={{ color: "var(--warn)" }}>⚠️</span>
            <span style={{ fontSize: "0.95rem" }}>
              <strong>{overview.review.needs_review_count} transactions</strong> ({formatMoney(overview.review.needs_review_amount, overview.currency)}) need review
            </span>
          </div>
          <a href="/transactions?needs_review=true" style={{ fontSize: "0.9rem", color: "var(--ink)", fontWeight: 500, textDecoration: "none" }}>Review &rarr;</a>
        </div>
      )}

      <section className="metrics" style={{ marginBottom: 24, display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "16px" }}>
        <article className="panel metric" style={{ padding: "16px" }}>
          <div className="metric-label" style={{ fontSize: "0.85rem", color: "var(--ink-muted)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "8px" }}>Total Spent</div>
          <div className="metric-value" style={{ fontSize: "1.75rem", fontWeight: 600, marginBottom: "8px" }}>{formatMoney(overview.summary.spent, overview.currency)}</div>
          <div className="metric-hint" style={{ fontSize: "0.85rem" }}>
            {overview.month_comparison.spent_change_pct != null ? (
              <span style={{ color: overview.month_comparison.spent_change_pct > 0 ? 'var(--warn)' : 'var(--credit)' }}>
                {overview.month_comparison.spent_change_pct > 0 ? "↑" : "↓"} {Math.abs(overview.month_comparison.spent_change_pct).toFixed(1)}% vs prev month
              </span>
            ) : (
              <span style={{ color: "var(--ink-muted)" }}>vs previous month</span>
            )}
          </div>
        </article>
        <article className="panel metric" style={{ padding: "16px" }}>
          <div className="metric-label" style={{ fontSize: "0.85rem", color: "var(--ink-muted)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "8px" }}>Income</div>
          <div className="metric-value" style={{ fontSize: "1.75rem", fontWeight: 600, marginBottom: "8px" }}>{formatMoney(overview.summary.income, overview.currency)}</div>
          <div className="metric-hint" style={{ fontSize: "0.85rem" }}>
            {overview.month_comparison.income_change_pct != null ? (
              <span style={{ color: overview.month_comparison.income_change_pct > 0 ? 'var(--credit)' : 'var(--warn)' }}>
                {overview.month_comparison.income_change_pct > 0 ? "↑" : "↓"} {Math.abs(overview.month_comparison.income_change_pct).toFixed(1)}% vs prev month
              </span>
            ) : (
              <span style={{ color: "var(--ink-muted)" }}>vs previous month</span>
            )}
          </div>
        </article>
        <article className="panel metric" style={{ padding: "16px" }}>
          <div className="metric-label" style={{ fontSize: "0.85rem", color: "var(--ink-muted)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "8px" }}>Net Cash Flow</div>
          <div className="metric-value" style={{ fontSize: "1.75rem", fontWeight: 600, marginBottom: "8px" }}>{formatMoney(overview.summary.net_cash_flow, overview.currency)}</div>
          <div className="metric-hint" style={{ fontSize: "0.85rem", color: "var(--ink-muted)" }}>Income − spent</div>
        </article>
      </section>
      
      <section style={{ marginBottom: "24px", display: "grid", gridTemplateColumns: accounts ? "1fr 1fr" : "1fr", gap: "16px" }}>
        <article className="panel metric" style={{ padding: "12px 16px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span style={{ fontSize: "0.9rem", color: "var(--ink-muted)" }}>Transactions</span>
          <span style={{ fontWeight: 500 }}>{overview.summary.transaction_count} ({overview.summary.debit_count} out, {overview.summary.credit_count} in)</span>
        </article>
        {accounts && (
          <article className="panel metric" style={{ padding: "12px 16px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: "0.9rem", color: "var(--ink-muted)" }}>Net Worth</span>
            <span style={{ fontWeight: 500 }}>{formatMoney(accounts.net_worth, overview.currency)}</span>
          </article>
        )}
      </section>

      {/* Month over Month vs Previous Month insight */}
      <section className="panel" style={{ marginBottom: 24, padding: "20px" }}>
        <h3 style={{ margin: "0 0 16px", fontSize: "1.1rem" }}>Monthly Insights vs Previous</h3>
        
        <div style={{ marginBottom: "16px", display: "flex", gap: "32px" }}>
          <div>
            <span style={{ color: "var(--ink-muted)", fontSize: "0.9rem", display: "block", marginBottom: "4px" }}>Spending difference</span>
            <span style={{ fontWeight: 500, color: spendingDiff > 0 ? 'var(--warn)' : 'var(--credit)' }}>
              {spendingDiff > 0 ? "+" : ""}{formatMoney(spendingDiff, overview.currency)}
            </span>
          </div>
          <div>
            <span style={{ color: "var(--ink-muted)", fontSize: "0.9rem", display: "block", marginBottom: "4px" }}>Income difference</span>
            <span style={{ fontWeight: 500, color: incomeDiff > 0 ? 'var(--credit)' : 'var(--warn)' }}>
              {incomeDiff > 0 ? "+" : ""}{formatMoney(incomeDiff, overview.currency)}
            </span>
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px", fontSize: "0.95rem", paddingTop: "16px", borderTop: "1px solid var(--line)" }}>
          <div>
            <span style={{ color: "var(--ink-muted)", display: "block", marginBottom: "4px", fontSize: "0.85rem" }}>Biggest Increase</span>
            {biggestIncrease ? (
              <div>
                <strong>{biggestIncrease.category}</strong>: <span style={{ color: "var(--warn)" }}>+{formatMoney(maxInc, overview.currency)}</span>
              </div>
            ) : <div style={{ color: "var(--ink-muted)" }}>No significant increases</div>}
          </div>
          <div>
            <span style={{ color: "var(--ink-muted)", display: "block", marginBottom: "4px", fontSize: "0.85rem" }}>Biggest Decrease</span>
            {biggestDecrease ? (
              <div>
                <strong>{biggestDecrease.category}</strong>: <span style={{ color: "var(--credit)" }}>{formatMoney(maxDec, overview.currency)}</span>
              </div>
            ) : <div style={{ color: "var(--ink-muted)" }}>No significant decreases</div>}
          </div>
        </div>
      </section>

      <div className="grid-2" style={{ marginBottom: 24, display: "grid", gridTemplateColumns: "1fr 1fr", gap: "24px" }}>
        <section className="panel section" style={{ padding: "20px" }}>
          <h3 style={{ margin: "0 0 20px", fontSize: "1.2rem" }}>Spending Breakdown</h3>
          {overview.category_breakdown.length === 0 ? (
            <p className="empty">No spending this month.</p>
          ) : (
            <div className="category-list">
              {renderCategoryGroup("Consumer Spending", consumerCategories)}
              {renderCategoryGroup("Other Cash Movements", otherCategories)}
              {renderCategoryGroup("Other / Uncategorized", uncategorizedCategories)}
            </div>
          )}
        </section>

        <section className="panel section" style={{ padding: "20px", display: "flex", flexDirection: "column" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "20px" }}>
            <h3 style={{ margin: "0", fontSize: "1.2rem" }}>Daily Spending</h3>
            <span style={{ fontSize: "0.9rem", color: "var(--ink-muted)" }}>Daily avg: {formatMoney(avgDaily, overview.currency)}</span>
          </div>
          <div style={{ flex: 1, minHeight: "200px", display: "flex", alignItems: "flex-end", gap: "2px", paddingTop: "16px", paddingBottom: "8px", position: "relative" }}>
            {overview.daily_spending.length > 0 ? (
              overview.daily_spending.map((d) => {
                const heightPct = Math.max(0, (d.spent / maxDaily) * 100);
                return (
                  <div key={d.date} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "flex-end", height: "100%" }} title={`${d.date}: ${formatMoney(d.spent, overview.currency)}`}>
                    <div style={{
                      width: "100%",
                      height: `${heightPct}%`,
                      background: "var(--accent)",
                      opacity: 0.8,
                      borderTopLeftRadius: "2px",
                      borderTopRightRadius: "2px",
                      minHeight: d.spent > 0 ? "2px" : "0"
                    }} />
                  </div>
                );
              })
            ) : (
              <p className="empty" style={{ width: "100%", textAlign: "center" }}>No daily data.</p>
            )}
          </div>
          {overview.daily_spending.length > 0 && (
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.8rem", color: "var(--ink-muted)", borderTop: "1px solid var(--line)", paddingTop: "8px" }}>
              <span>{overview.daily_spending[0].date.split('-').slice(1).join('/')}</span>
              <span>{overview.daily_spending[overview.daily_spending.length - 1].date.split('-').slice(1).join('/')}</span>
            </div>
          )}
        </section>
      </div>

      <div className="grid-2" style={{ marginBottom: 24, display: "grid", gridTemplateColumns: "1fr 1fr", gap: "24px" }}>
        <section className="panel section" style={{ padding: "20px" }}>
          <h3 style={{ margin: "0 0 20px", fontSize: "1.2rem" }}>Top Merchants</h3>
          <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
            {overview.top_merchants.slice(0, 5).map((m, i) => (
              <div key={m.merchant || i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", paddingRight: "16px" }} title={m.merchant || "Unidentified merchant"}>
                  <div style={{ fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis" }}>{m.merchant || "Unidentified merchant"}</div>
                  <div style={{ fontSize: "0.85rem", color: "var(--ink-muted)" }}>{m.count} transactions</div>
                </div>
                <div style={{ fontWeight: 600, textAlign: "right", whiteSpace: "nowrap" }}>{formatMoney(m.total, overview.currency)}</div>
              </div>
            ))}
            {overview.top_merchants.length === 0 && <p className="empty">No merchants this month.</p>}
          </div>
        </section>

        <section className="panel section" style={{ padding: "20px" }}>
          <h3 style={{ margin: "0 0 20px", fontSize: "1.2rem" }}>Payment Methods</h3>
          <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
            {overview.account_breakdown.slice(0, 5).map((a, i) => (
              <div key={a.account || i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div>
                  <div style={{ fontWeight: 500, display: "flex", alignItems: "center", gap: "6px" }}>
                    {!a.account && <span style={{ color: "var(--warn)", fontSize: "0.9rem" }}>⚠️</span>}
                    {a.account || "Unknown account"}
                  </div>
                  <div style={{ fontSize: "0.85rem", color: "var(--ink-muted)" }}>{a.percentage.toFixed(1)}% of spend</div>
                </div>
                <div style={{ fontWeight: 600, textAlign: "right" }}>{formatMoney(a.total, overview.currency)}</div>
              </div>
            ))}
            {overview.account_breakdown.length === 0 && <p className="empty">No account data.</p>}
          </div>
        </section>
      </div>

      <section className="panel section" style={{ padding: "20px" }}>
        <h3 style={{ margin: "0 0 20px", fontSize: "1.2rem" }}>Largest Transactions</h3>
        {overview.largest_transactions.length > 0 ? (
          <table className="table" style={{ width: "100%", textAlign: "left", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--line)", color: "var(--ink-muted)", fontSize: "0.85rem", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                <th style={{ padding: "12px 8px", fontWeight: 500 }}>Date</th>
                <th style={{ padding: "12px 8px", fontWeight: 500 }}>Merchant</th>
                <th style={{ padding: "12px 8px", fontWeight: 500 }}>Category</th>
                <th style={{ padding: "12px 8px", fontWeight: 500 }}>Account</th>
                <th style={{ padding: "12px 8px", fontWeight: 500, textAlign: "right" }}>Amount</th>
              </tr>
            </thead>
            <tbody>
              {overview.largest_transactions.slice(0, 5).map(t => (
                <tr key={t.id} 
                    style={{ borderBottom: "1px solid var(--line)", cursor: "pointer" }} 
                    onClick={() => window.location.href = `/transactions?id=${t.id}`}
                    className="hover-row">
                  <td style={{ padding: "12px 8px", fontSize: "0.9rem" }}>{t.date}</td>
                  <td style={{ padding: "12px 8px", fontWeight: 500 }}>{t.merchant || "Unidentified merchant"}</td>
                  <td style={{ padding: "12px 8px", fontSize: "0.9rem" }}>{t.category || "Uncategorized"}</td>
                  <td style={{ padding: "12px 8px", fontSize: "0.9rem", color: "var(--ink-muted)" }}>{t.account || "Unknown account"}</td>
                  <td style={{ padding: "12px 8px", fontWeight: 600, textAlign: "right" }}>{formatMoney(t.amount, overview.currency)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="empty">No transactions this month.</p>
        )}
      </section>
    </div>
  );
}
