import { useEffect, useId, useState } from "react";
import { createPortal } from "react-dom";
import { api, type Transaction } from "../api";
import { useBackdropClose, useModalChrome } from "../hooks/useModalChrome";

type Props = {
  open: boolean;
  transaction: Transaction | null;
  onClose: () => void;
  onSuccess: () => void;
};

export default function MarkRecurringModal({ open, transaction, onClose, onSuccess }: Props) {
  const titleId = useId();
  const [type, setType] = useState<"subscription" | "bill">("subscription");
  const [name, setName] = useState("");
  const [frequency, setFrequency] = useState("monthly");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useModalChrome(open, onClose);
  const onBackdropClick = useBackdropClose(open, onClose);

  useEffect(() => {
    if (open && transaction) {
      setName(transaction.merchant_normalized || transaction.merchant_raw || "");
      setFrequency("monthly");
      setType("subscription");
      setError(null);
    }
  }, [open, transaction]);

  if (!open || !transaction) return null;

  async function handleSubmit() {
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

  return createPortal(
    <div className="modal-backdrop" role="presentation" onClick={onBackdropClick}>
      <div className="modal-panel" role="dialog" aria-modal="true" aria-labelledby={titleId} onClick={(e) => e.stopPropagation()}>
        <header className="modal-header" style={{ padding: "24px 32px", borderBottom: "1px solid var(--line)", alignItems: "flex-start" }}>
          <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
            <div style={{ width: 44, height: 44, borderRadius: "50%", background: "var(--accent-soft)", color: "var(--accent)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
              <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" focusable="false"><path fill="currentColor" d="M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6 0 1.01-.25 1.97-.7 2.8l1.46 1.46C19.54 15.03 20 13.57 20 12c0-4.42-3.58-8-8-8zm0 14c-3.31 0-6-2.69-6-6 0-1.01.25-1.97.7-2.8L5.24 7.74C4.46 8.97 4 10.43 4 12c0 4.42 3.58 8 8 8v3l4-4-4-4v3z"/></svg>
            </div>
            <div>
              <h2 id={titleId} style={{ margin: 0, fontSize: "1.25rem", fontWeight: 700, color: "var(--ink)" }}>Mark as recurring</h2>
              <p style={{ margin: "4px 0 0 0", color: "var(--ink-muted)", fontSize: "0.875rem" }}>
                Classify {transaction.merchant_normalized || "this transaction"} as a recurring bill or subscription.
              </p>
            </div>
          </div>
          <div className="modal-actions" style={{ alignSelf: "flex-start", marginTop: 4 }}>
            <button type="button" className="btn icon-btn" onClick={onClose} aria-label="Close modal">
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
            </button>
          </div>
        </header>
        
        <div className="modal-body" style={{ display: "flex", flexDirection: "column", gap: 24, padding: "32px" }}>
          {error && <div className="error">{error}</div>}
          
          <div className="form-group full-width">
            <label style={{ display: "block", marginBottom: 8, fontWeight: 500 }}>Type</label>
            <div className="segmented">
              <button type="button" className={`segmented-btn ${type === "subscription" ? "active" : ""}`} onClick={() => setType("subscription")}>Subscription (Fixed)</button>
              <button type="button" className={`segmented-btn ${type === "bill" ? "active" : ""}`} onClick={() => setType("bill")}>Bill (Variable)</button>
            </div>
          </div>
          
          <div className="form-group full-width">
            <label style={{ display: "block", marginBottom: 8, fontWeight: 500 }}>Name</label>
            <input 
              className="input" 
              value={name} 
              onChange={e => setName(e.target.value)} 
              placeholder={transaction?.merchant_normalized || transaction?.merchant_raw || "e.g. Netflix"} 
              style={{ width: "100%" }}
            />
          </div>
          
          <div className="form-group full-width">
            <label style={{ display: "block", marginBottom: 8, fontWeight: 500 }}>Frequency</label>
            <select className="input" value={frequency} onChange={e => setFrequency(e.target.value)} style={{ width: "100%" }}>
              <option value="monthly">Monthly</option>
              <option value="yearly">Yearly</option>
              <option value="weekly">Weekly</option>
            </select>
          </div>
        </div>

        <footer style={{ padding: "20px 32px", borderTop: "1px solid var(--line)", background: "var(--surface)", display: "flex", justifyContent: "flex-end", alignItems: "center", borderRadius: "0 0 8px 8px" }}>
          <div style={{ display: "flex", gap: 12 }}>
            <button type="button" className="btn quiet" onClick={onClose} style={{ padding: "10px 20px" }} disabled={saving}>Cancel</button>
            <button type="button" className="btn primary" style={{ padding: "10px 24px" }} disabled={saving} onClick={handleSubmit}>
              {saving ? "Saving..." : "Save Recurring"}
            </button>
          </div>
        </footer>
      </div>
    </div>,
    document.body
  );
}
