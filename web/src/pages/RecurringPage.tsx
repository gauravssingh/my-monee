import { useEffect, useState } from "react";
import { api, type Subscription, type Bill } from "../api";
import { formatDate, formatMoney } from "../format";
import PageHeader from "../components/common/PageHeader";
import SegmentedControl from "../components/common/SegmentedControl";

export default function RecurringPage() {
  const [subscriptions, setSubscriptions] = useState<Subscription[]>([]);
  const [bills, setBills] = useState<Bill[]>([]);
  const [detected, setDetected] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [mobileTab, setMobileTab] = useState<"all" | "subscriptions" | "bills" | "detected">("all");

  useEffect(() => {
    setLoading(true);
    api.getRecurring()
      .then((data) => {
        setSubscriptions(data.subscriptions);
        setBills(data.bills);
        setDetected(data.detected || []);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="empty">Loading recurring items...</div>;
  if (error) return <div className="error">{error}</div>;

  const totalMonthlySub = subscriptions.reduce((acc, sub) => {
    const monthly = sub.annual_cost > 0 ? sub.annual_cost / 12 : (sub.billing_frequency === "yearly" ? sub.amount / 12 : sub.amount);
    return acc + monthly;
  }, 0);
  const totalBillsExpected = bills.reduce((acc, bill) => acc + bill.expected_amount, 0);

  const showSubs = mobileTab === "all" || mobileTab === "subscriptions";
  const showBills = mobileTab === "all" || mobileTab === "bills";
  const showDetected = mobileTab === "all" || mobileTab === "detected";

  return (
    <>
      <PageHeader
        title="Recurring & Subscriptions"
        subtitle="Automatically detected fixed subscriptions and variable bills based on transaction history."
      />
      
      <section className="metrics" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}>
        <article className="metric">
          <div className="metric-label">Avg Monthly Subscriptions</div>
          <div className="metric-value">
            {formatMoney(totalMonthlySub)}
          </div>
          <div className="metric-hint">Fixed, low variance recurring commitments</div>
        </article>
        <article className="metric">
          <div className="metric-label">Expected Variable Bills</div>
          <div className="metric-value">
            {formatMoney(totalBillsExpected)}
          </div>
          <div className="metric-hint">Based on average past utility & card statements</div>
        </article>
      </section>

      {/* Mobile Tab Filter */}
      <div className="mobile-recurring-tabs" style={{ display: "none", marginBottom: 16 }}>
        <SegmentedControl<"all" | "subscriptions" | "bills" | "detected">
          value={mobileTab}
          onChange={setMobileTab}
          size="sm"
          style={{ width: "100%" }}
          options={[
            { value: "all", label: "All" },
            { value: "subscriptions", label: "Subscriptions", count: subscriptions.length },
            { value: "bills", label: "Bills", count: bills.length },
            ...(detected.length > 0 ? [{ value: "detected" as const, label: "Detected", count: detected.length }] : []),
          ]}
        />
      </div>

      <div className="grid-2">
        {showSubs && (
          <section className="section">
            <h2>Fixed Subscriptions</h2>
            <p className="lead">Services with exact recurring amounts.</p>
            {subscriptions.length === 0 ? (
              <div className="empty">No subscriptions detected.</div>
            ) : (
              <div className="table-wrap">
                <table style={{ minWidth: "100%" }}>
                  <thead>
                    <tr>
                      <th>Service</th>
                      <th>Freq</th>
                      <th className="num">Amount</th>
                      <th>Next Date</th>
                    </tr>
                  </thead>
                  <tbody>
                    {subscriptions.map(s => (
                      <tr key={s.id}>
                        <td style={{ fontWeight: 600 }}>{s.name}</td>
                        <td style={{ textTransform: "capitalize", fontSize: "0.85rem", color: "var(--ink-muted)" }}>{s.billing_frequency}</td>
                        <td className="num tx-amount debit">−{formatMoney(s.amount)}</td>
                        <td className="tx-date">{s.next_billing_date ? formatDate(s.next_billing_date) : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        )}

        {showBills && (
          <section className="section">
            <h2>Variable Bills</h2>
            <p className="lead">Recurring payments with varying monthly amounts.</p>
            {bills.length === 0 ? (
              <div className="empty">No variable bills detected.</div>
            ) : (
              <div className="table-wrap">
                <table style={{ minWidth: "100%" }}>
                  <thead>
                    <tr>
                      <th>Biller</th>
                      <th>Freq</th>
                      <th className="num">Avg Amount</th>
                      <th>Due Date</th>
                    </tr>
                  </thead>
                  <tbody>
                    {bills.map(b => (
                      <tr key={b.id}>
                        <td style={{ fontWeight: 600 }}>{b.name}</td>
                        <td style={{ textTransform: "capitalize", fontSize: "0.85rem", color: "var(--ink-muted)" }}>{b.frequency}</td>
                        <td className="num tx-amount debit">−{formatMoney(b.expected_amount)}</td>
                        <td className="tx-date" style={{ color: b.due_date ? "var(--warn)" : "var(--ink-muted)" }}>
                          {b.due_date ? formatDate(b.due_date) : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        )}

        {showDetected && detected.length > 0 && (
          <section className="section" style={{ gridColumn: "1 / -1", marginTop: 12 }}>
            <h2>Detected Recurring Candidates</h2>
            <p className="lead">Transactions identified as candidate recurring commitments.</p>
            <div className="table-wrap">
              <table style={{ minWidth: "100%" }}>
                <thead>
                  <tr>
                    <th>Merchant / Name</th>
                    <th>Freq</th>
                    <th className="num">Expected Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {detected.map((d, i) => (
                    <tr key={d.id || i}>
                      <td style={{ fontWeight: 600 }}>{d.name}</td>
                      <td style={{ textTransform: "capitalize", fontSize: "0.85rem", color: "var(--ink-muted)" }}>{d.frequency}</td>
                      <td className="num tx-amount debit">−{formatMoney(d.expected_amount)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </div>
    </>
  );
}
