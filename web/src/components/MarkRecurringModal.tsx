import { useState } from "react";
import { api, type Transaction } from "../api";

type Props = {
  open: boolean;
  transaction: Transaction | null;
  onClose: () => void;
  onSuccess: () => void;
};

export default function MarkRecurringModal({ open, transaction, onClose, onSuccess }: Props) {
  const [type, setType] = useState<"subscription" | "bill">("subscription");
  const [name, setName] = useState("");
  const [frequency, setFrequency] = useState("monthly");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open || !transaction) return null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      if (type === "subscription") {
        await api.createSubscription({
          name: name || transaction?.merchant_normalized || transaction?.merchant_raw || "Unknown",
          amount: Math.abs(transaction?.amount ?? 0),
          billing_frequency: frequency,
          transaction_id: transaction?.id,
        });
      } else {
        await api.createBill({
          name: name || transaction?.merchant_normalized || transaction?.merchant_raw || "Unknown",
          expected_amount: Math.abs(transaction?.amount ?? 0),
          frequency,
          transaction_id: transaction?.id,
        });
      }
      onSuccess();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create recurring item");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="modal-overlay" onMouseDown={onClose}>
      <div className="modal-content" onMouseDown={e => e.stopPropagation()}>
        <header className="modal-header">
          <h2>Mark as Recurring</h2>
          <button className="icon-action" onClick={onClose}>×</button>
        </header>
        <form onSubmit={handleSubmit} className="modal-body form-grid">
          {error && <div className="error">{error}</div>}
          
          <div className="form-group full-width">
            <label>Type</label>
            <div className="segmented">
              <button type="button" className={`segmented-btn ${type === "subscription" ? "active" : ""}`} onClick={() => setType("subscription")}>Subscription (Fixed)</button>
              <button type="button" className={`segmented-btn ${type === "bill" ? "active" : ""}`} onClick={() => setType("bill")}>Bill (Variable)</button>
            </div>
          </div>
          
          <div className="form-group full-width">
            <label>Name</label>
            <input 
              className="input" 
              value={name} 
              onChange={e => setName(e.target.value)} 
              placeholder={transaction?.merchant_normalized || transaction?.merchant_raw || "e.g. Netflix"} 
            />
          </div>
          
          <div className="form-group full-width">
            <label>Frequency</label>
            <select className="input" value={frequency} onChange={e => setFrequency(e.target.value)}>
              <option value="monthly">Monthly</option>
              <option value="yearly">Yearly</option>
              <option value="weekly">Weekly</option>
            </select>
          </div>
          
          <div className="modal-footer full-width">
            <button type="button" className="btn" onClick={onClose} disabled={saving}>Cancel</button>
            <button type="submit" className="btn primary" disabled={saving}>
              {saving ? "Saving..." : "Save Recurring"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
