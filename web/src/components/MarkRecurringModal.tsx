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
      <div
        className="modal-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onClick={(e) => e.stopPropagation()}
        style={{ display: "flex", flexDirection: "column", height: "min(640px, 86dvh)", maxHeight: "86dvh" }}
      >
        <div className="sheet-handle" onClick={onClose} aria-label="Dismiss sheet" />

        <header className="modal-header" style={{ flexShrink: 0 }}>
          <div>
            <h2 id={titleId}>Mark as recurring</h2>
            <p className="lead">
              Classify {transaction.merchant_normalized || "this transaction"} as a recurring bill or subscription.
            </p>
          </div>
          <div className="modal-actions">
            <button type="button" className="btn icon-btn" onClick={onClose} aria-label="Close modal">
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
            </button>
          </div>
        </header>
        
        <div className="modal-body" style={{ display: "flex", flexDirection: "column", gap: 20, flex: "1 1 0%", minHeight: 0, overflowY: "auto" }}>
          {error && <div className="error">{error}</div>}
          
          <div className="field">
            <label className="label" style={{ display: "block", marginBottom: 6, fontSize: "0.75rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--ink-muted)" }}>Type</label>
            <div className="segmented">
              <button type="button" className={`segmented-btn ${type === "subscription" ? "active" : ""}`} onClick={() => setType("subscription")}>Subscription (Fixed)</button>
              <button type="button" className={`segmented-btn ${type === "bill" ? "active" : ""}`} onClick={() => setType("bill")}>Bill (Variable)</button>
            </div>
          </div>
          
          <div className="field">
            <label className="label" style={{ display: "block", marginBottom: 6, fontSize: "0.75rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--ink-muted)" }}>Name</label>
            <input 
              className="input" 
              value={name} 
              onChange={e => setName(e.target.value)} 
              placeholder={transaction?.merchant_normalized || transaction?.merchant_raw || "e.g. Netflix"} 
              style={{ width: "100%" }}
            />
          </div>
          
          <div className="field">
            <label className="label" style={{ display: "block", marginBottom: 6, fontSize: "0.75rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--ink-muted)" }}>Frequency</label>
            <select className="input" value={frequency} onChange={e => setFrequency(e.target.value)} style={{ width: "100%" }}>
              <option value="monthly">Monthly</option>
              <option value="yearly">Yearly</option>
              <option value="weekly">Weekly</option>
            </select>
          </div>
        </div>

        <footer className="modal-footer" style={{ flexShrink: 0, padding: "12px 18px max(16px, env(safe-area-inset-bottom, 16px))" }}>
          <button type="button" className="btn quiet" onClick={onClose} disabled={saving}>Cancel</button>
          <button type="button" className="btn primary" disabled={saving} onClick={handleSubmit}>
            {saving ? "Saving..." : "Save Recurring"}
          </button>
        </footer>
      </div>
    </div>,
    document.body
  );
}
