import { useEffect, useId, useState } from "react";
import { createPortal } from "react-dom";
import type { DataIssueType, Transaction } from "../api";
import { formatDate, formatMoney, issueFieldForType } from "../format";
import { useBackdropClose, useModalChrome } from "../hooks/useModalChrome";

type Props = {
  open: boolean;
  transactions: Transaction[];
  saving: boolean;
  error: string | null;
  onClose: () => void;
  onSubmit: (body: {
    issue_type: DataIssueType;
    field_name?: string | null;
    suggested_value?: string | null;
    note?: string | null;
  }) => void;
};

const ISSUE_TYPES: Array<{ value: DataIssueType; label: string }> = [
  { value: "not_a_transaction", label: "Not a transaction" },
  { value: "wrong_amount", label: "Wrong amount" },
  { value: "wrong_date", label: "Wrong date" },
  { value: "wrong_merchant", label: "Wrong merchant" },
  { value: "wrong_direction", label: "Wrong debit/credit" },
  { value: "duplicate", label: "Duplicate" },
  { value: "other", label: "Other" },
];

function currentFieldValue(tx: Transaction, field: string): string {
  switch (field) {
    case "amount":
      return formatMoney(tx.amount ?? 0, tx.currency);
    case "transaction_date":
      return formatDate(tx.transaction_date);
    case "merchant_normalized":
      return tx.merchant_normalized || tx.merchant_raw || "—";
    case "direction":
      return tx.direction;
    default:
      return "—";
  }
}

function previewLabel(tx: Transaction): string {
  return (
    tx.merchant_normalized ||
    tx.merchant_raw ||
    (tx.description
      ? tx.description.length > 60
        ? `${tx.description.slice(0, 60)}…`
        : tx.description
      : "Uncategorized transaction")
  );
}

export default function FlagIssueModal({ open, transactions, saving, error, onClose, onSubmit }: Props) {
  const titleId = useId();
  const [issueType, setIssueType] = useState<DataIssueType>("not_a_transaction");
  const [suggestedValue, setSuggestedValue] = useState("");
  const [note, setNote] = useState("");

  useModalChrome(open, onClose);
  const onBackdropClick = useBackdropClose(open, onClose);

  useEffect(() => {
    if (!open) return;
    setIssueType("not_a_transaction");
    setSuggestedValue("");
    setNote("");
  }, [open, transactions]);

  if (!open || transactions.length === 0) return null;

  const count = transactions.length;
  const single = count === 1 ? transactions[0] : null;
  const preview = transactions.slice(0, 5);
  const remaining = Math.max(0, count - preview.length);
  const field = issueFieldForType(issueType);

  return createPortal(
    <div className="modal-backdrop" role="presentation" onClick={onBackdropClick}>
      <div
        className="modal-panel flag-issue-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onClick={(e) => e.stopPropagation()}
        style={{ display: "flex", flexDirection: "column", maxHeight: "86dvh", width: "min(500px, 100%)" }}
      >
        <div className="sheet-handle" onClick={onClose} aria-label="Dismiss sheet" />

        <header className="modal-header" style={{ flexShrink: 0, padding: "16px 20px 12px" }}>
          <div>
            <h2 id={titleId} style={{ fontSize: "1.05rem", margin: 0 }}>{count === 1 ? "Flag data issue" : `Flag ${count} transactions`}</h2>
            <p className="lead" style={{ margin: "4px 0 0", fontSize: "0.8rem", color: "var(--ink-muted)", lineHeight: 1.35 }}>
              Groups transactions for review under Data Issues without modifying raw data.
            </p>
          </div>
          <div className="modal-actions">
            <button type="button" className="btn icon-btn" onClick={onClose} aria-label="Close modal" disabled={saving}>
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
            </button>
          </div>
        </header>

        <div className="modal-body flag-issue-body" style={{ flex: "1 1 auto", minHeight: 0, overflowY: "auto", padding: "14px 20px", gap: "14px" }}>
          <section className="classify-preview">
            <h3 className="classify-section-title">{count === 1 ? "Transaction" : "Selected"}</h3>
            <ul className="classify-preview-list">
              {preview.map((tx) => (
                <li key={tx.id}>
                  <span className="classify-preview-merchant">{previewLabel(tx)}</span>
                  <span className="classify-preview-meta">
                    {formatDate(tx.transaction_date)} ·{" "}
                    <span className={tx.direction === "credit" ? "tx-amount credit" : "tx-amount debit"}>
                      {tx.direction === "credit" ? "+" : "−"}
                      {formatMoney(tx.amount ?? 0, tx.currency)}
                    </span>
                  </span>
                </li>
              ))}
            </ul>
            {remaining > 0 && <p className="metric-hint">and {remaining} more…</p>}
          </section>

          <section>
            <h3 className="classify-section-title">What's wrong</h3>
            <div className="classify-chip-grid" role="listbox" aria-label="Issue type">
              {ISSUE_TYPES.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  role="option"
                  aria-selected={issueType === opt.value}
                  className={`classify-chip${issueType === opt.value ? " active" : ""}`}
                  onClick={() => setIssueType(opt.value)}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </section>

          {field && (
            <section>
              <h3 className="classify-section-title">
                {single ? "Currently extracted as" : "Correct value, if the same for all"}
              </h3>
              {single && <p className="flag-current-value">{currentFieldValue(single, field)}</p>}
              <label className="flag-field-label" htmlFor="flag-suggested-value">
                {single ? "What should it be? (optional)" : "Optional — leave blank if it varies per row"}
              </label>
              <input
                id="flag-suggested-value"
                className="input"
                value={suggestedValue}
                onChange={(e) => setSuggestedValue(e.target.value)}
                placeholder="Leave blank if you're not sure"
              />
            </section>
          )}

          <section>
            <label className="flag-field-label" htmlFor="flag-note">
              Note (optional)
            </label>
            <textarea
              id="flag-note"
              className="input"
              rows={2}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Anything else worth knowing about this one"
            />
          </section>

          {error && <p className="error">{error}</p>}

        </div>
        <footer className="modal-footer" style={{ flexShrink: 0, padding: "12px 20px max(14px, env(safe-area-inset-bottom, 14px))", borderTop: "1px solid var(--line)" }}>
          <button type="button" className="btn quiet" onClick={onClose} disabled={saving}>Cancel</button>
          <button 
            type="button" 
            className="btn primary" 
            disabled={saving}
            onClick={() =>
              onSubmit({
                issue_type: issueType,
                field_name: field,
                suggested_value: suggestedValue.trim() || null,
                note: note.trim() || null,
              })
            }
          >
            {saving ? "Flagging…" : count === 1 ? "Flag issue" : `Flag ${count} transactions`}
          </button>
        </footer>
      </div>
    </div>,
    document.body,
  );
}
