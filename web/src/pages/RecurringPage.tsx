import { useEffect, useState } from "react";
import { api, type Subscription, type Bill } from "../api";
import { formatMoney } from "../format";

export default function RecurringPage() {
  const [subscriptions, setSubscriptions] = useState<Subscription[]>([]);
  const [bills, setBills] = useState<Bill[]>([]);
  const [detected, setDetected] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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

  const totalMonthlySub = subscriptions.reduce((acc, sub) => acc + (sub.annual_cost / 12), 0);
  const totalBillsExpected = bills.reduce((acc, bill) => acc + bill.expected_amount, 0);

  return (
    <>
      <header className="page-header">
        <div>
          <h1>Recurring & Subscriptions</h1>
          <p className="lead">Automatically detected fixed subscriptions and variable bills based on your transaction history.</p>
        </div>
      </header>
      
      <section className="metrics">
        <article className="panel metric" style={{ background: "var(--accent-soft)" }}>
          <div className="metric-label">Avg Monthly Subscriptions</div>
          <div className="metric-value" style={{ color: "var(--accent)" }}>
            {formatMoney(totalMonthlySub)}
          </div>
          <div className="metric-hint">Fixed, low variance recurring costs</div>
        </article>
        <article className="panel metric">
          <div className="metric-label">Expected Variable Bills</div>
          <div className="metric-value">
            {formatMoney(totalBillsExpected)}
          </div>
          <div className="metric-hint">Based on average past amounts</div>
        </article>
      </section>

      <div className="grid-2">
        <section className="panel section">
          <h2>Fixed Subscriptions</h2>
          <p className="lead">Services with exact recurring amounts.</p>
          {subscriptions.length === 0 ? (
            <div className="empty">No subscriptions detected.</div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Service</th>
                  <th>Freq</th>
                  <th>Amount</th>
                  <th>Next Date</th>
                </tr>
              </thead>
              <tbody>
                {subscriptions.map(s => (
                  <tr key={s.id}>
                    <td style={{ fontWeight: 600 }}>{s.name}</td>
                    <td style={{ textTransform: "capitalize", fontSize: "0.85rem", color: "var(--ink-muted)" }}>{s.billing_frequency}</td>
                    <td>{formatMoney(s.amount)}</td>
                    <td>{s.next_billing_date ? new Date(s.next_billing_date).toLocaleDateString() : "Unknown"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        <section className="panel section">
          <h2>Variable Bills</h2>
          <p className="lead">Recurring payments with varying amounts.</p>
          {bills.length === 0 ? (
            <div className="empty">No variable bills detected.</div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Biller</th>
                  <th>Freq</th>
                  <th>Avg Amount</th>
                  <th>Due Date</th>
                </tr>
              </thead>
              <tbody>
                {bills.map(b => (
                  <tr key={b.id}>
                    <td style={{ fontWeight: 600 }}>{b.name}</td>
                    <td style={{ textTransform: "capitalize", fontSize: "0.85rem", color: "var(--ink-muted)" }}>{b.frequency}</td>
                    <td>{formatMoney(b.expected_amount)}</td>
                    <td style={{ color: "var(--warn)" }}>
                        {b.due_date ? new Date(b.due_date).toLocaleDateString() : "Unknown"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        {detected.length > 0 && (
          <section className="panel section" style={{ gridColumn: "1 / -1" }}>
            <h2>Detected Recurring Candidates</h2>
            <p className="lead">These transactions look like recurring charges, but are not yet confirmed.</p>
            <table>
              <thead>
                <tr>
                  <th>Merchant / Name</th>
                  <th>Freq</th>
                  <th>Expected Amount</th>
                </tr>
              </thead>
              <tbody>
                {detected.map((d, i) => (
                  <tr key={d.id || i}>
                    <td style={{ fontWeight: 600 }}>{d.name}</td>
                    <td style={{ textTransform: "capitalize", fontSize: "0.85rem", color: "var(--ink-muted)" }}>{d.frequency}</td>
                    <td>{formatMoney(d.expected_amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        )}
      </div>
    </>
  );
}
