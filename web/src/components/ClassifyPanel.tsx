import { useEffect, useId, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api, type AISuggestion, type CategoryTree, type Transaction } from "../api";
import { formatDate, formatMoney } from "../format";
import { useBackdropClose, useModalChrome } from "../hooks/useModalChrome";
import { useConfirm } from "../hooks/useConfirm";

type Props = {
  open: boolean;
  transactions: Transaction[];
  categories: CategoryTree[];
  saving: boolean;
  error: string | null;
  onClose: () => void;
  onSave: (categoryId: string, subcategoryId: string | null) => void;
  onExclude: () => void;
  onReimburse: () => void;
  onFlag: (tx: Transaction) => void;
};

export default function ClassifyPanel({
  open,
  transactions,
  categories,
  saving,
  error,
  onClose,
  onSave,
  onExclude,
  onReimburse,
  onFlag,
}: Props) {
  const titleId = useId();
  const closeRef = useRef<HTMLButtonElement>(null);
  const [categoryId, setCategoryId] = useState("");
  const [subcategoryId, setSubcategoryId] = useState("");

  const [aiSuggestion, setAiSuggestion] = useState<AISuggestion | null>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);

  useModalChrome(open, onClose, closeRef);
  const onBackdropClick = useBackdropClose(open, onClose);
  const { armed: excludeArmed, trigger: triggerExclude } = useConfirm(onExclude);
  const { armed: reimburseArmed, trigger: triggerReimburse } = useConfirm(onReimburse);

  useEffect(() => {
    if (!open) return;
    setCategoryId("");
    setSubcategoryId("");
    setAiSuggestion(null);
    setAiError(null);

    // If a single transaction is open, fetch AI suggestion if available
    if (transactions.length === 1) {
      const tx = transactions[0];
      setAiLoading(true);
      api.getAiSuggestion(tx.id)
        .then((sug) => {
          setAiSuggestion(sug);
        })
        .catch((err: Error) => {
          // If external AI is disabled or key missing, silently ignore or record
          if (err.message && !err.message.includes("External AI is disabled")) {
            setAiError(err.message);
          }
        })
        .finally(() => {
          setAiLoading(false);
        });
    }
  }, [open, transactions]);

  const selectedCategory = useMemo(
    () => categories.find((c) => c.id === categoryId) ?? null,
    [categories, categoryId],
  );

  if (!open) return null;

  const count = transactions.length;
  const preview = transactions.slice(0, 5);
  const remaining = Math.max(0, count - preview.length);

  return createPortal(
    <div className="modal-backdrop" role="presentation" onClick={onBackdropClick}>
      <div
        className="modal-panel classify-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onClick={(e) => e.stopPropagation()}
      >
        <header className="modal-header">
          <div>
            <h2 id={titleId}>
              {count === 1 ? "Classify transaction" : `Classify ${count} transactions`}
            </h2>
            <p className="metric-hint">
              Choose a category, then save to verify and clear Needs Review.
            </p>
          </div>
          <div className="modal-actions">
            <button ref={closeRef} className="btn" type="button" onClick={onClose} disabled={saving}>
              Cancel
            </button>
          </div>
        </header>

        <div className="modal-body classify-panel-body">
          <section className="classify-preview">
            <h3 className="classify-section-title">Selected</h3>
            <ul className="classify-preview-list">
              {preview.map((tx) => {
                const merchant =
                  tx.merchant_normalized ||
                  tx.merchant_raw ||
                  (tx.description
                    ? tx.description.length > 60
                      ? `${tx.description.slice(0, 60)}…`
                      : tx.description
                    : "Uncategorized transaction");
                return (
                  <li key={tx.id}>
                    <span className="classify-preview-merchant">{merchant}</span>
                    <span className="classify-preview-trailing">
                      <span className="classify-preview-meta">
                        {formatDate(tx.transaction_date)} ·{" "}
                        <span className={tx.direction === "credit" ? "tx-amount credit" : "tx-amount debit"}>
                          {tx.direction === "credit" ? "+" : "−"}
                          {formatMoney(tx.amount ?? 0, tx.currency)}
                        </span>
                      </span>
                      <button
                        className="icon-action"
                        type="button"
                        title="Flag a data issue"
                        aria-label={`Flag a data issue on ${merchant}`}
                        onClick={() => onFlag(tx)}
                      >
                        <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" focusable="false">
                          <path fill="currentColor" d="M14.4 6 14 4H5v17h2v-7h5.6l.4 2h7V6z" />
                        </svg>
                      </button>
                    </span>
                  </li>
                );
              })}
            </ul>
            {remaining > 0 && (
              <p className="metric-hint">and {remaining} more…</p>
            )}
          </section>

          {count === 1 && (
            <section className="classify-ai-section" style={{ marginBottom: 16 }}>
              {aiLoading && (
                <div style={{ padding: "12px 16px", borderRadius: 8, border: "1px dashed var(--line)", background: "var(--surface)", color: "var(--ink-muted)", fontSize: "0.8125rem" }}>
                  Consulting Gemini for category suggestion…
                </div>
              )}
              {aiError && (
                <div style={{ padding: "10px 14px", borderRadius: 8, border: "1px solid var(--line)", background: "var(--surface)", fontSize: "0.8125rem", color: "var(--ink-muted)" }}>
                  <span>AI Suggestion unavailable ({aiError})</span>
                </div>
              )}
              {aiSuggestion && (
                <div
                  style={{
                    padding: "14px 16px",
                    borderRadius: 8,
                    border: "1px solid var(--accent, #0c6e5c)",
                    background: "var(--accent-soft, #e8f5f1)",
                    display: "flex",
                    flexDirection: "column",
                    gap: 8,
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ fontSize: "0.75rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.04em", color: "var(--accent, #0c6e5c)" }}>
                        ✨ AI Suggestion ({aiSuggestion.provider === "gemini" ? "Gemini" : aiSuggestion.provider})
                      </span>
                      <span style={{ fontSize: "0.75rem", color: "var(--ink-muted)" }}>
                        {Math.round(aiSuggestion.confidence * 100)}% confidence
                      </span>
                      {aiSuggestion.cached && (
                        <span style={{ fontSize: "0.6875rem", background: "var(--surface)", padding: "1px 6px", borderRadius: 4, color: "var(--ink-muted)", border: "1px solid var(--line)" }}>
                          cached
                        </span>
                      )}
                    </div>
                    <button
                      type="button"
                      className="btn primary"
                      style={{ padding: "4px 12px", fontSize: "0.8125rem", height: "auto" }}
                      onClick={() => {
                        setCategoryId(aiSuggestion.category_id);
                        setSubcategoryId(aiSuggestion.subcategory_id || "");
                      }}
                    >
                      Accept Suggestion
                    </button>
                  </div>
                  <div style={{ fontSize: "0.9375rem", fontWeight: 600, color: "var(--ink)" }}>
                    {aiSuggestion.category_name}
                    {aiSuggestion.subcategory_name ? ` › ${aiSuggestion.subcategory_name}` : ""}
                  </div>
                  {aiSuggestion.signals && aiSuggestion.signals.length > 0 && (
                    <ul style={{ margin: 0, paddingLeft: 18, fontSize: "0.8125rem", color: "var(--ink-muted)", lineHeight: 1.4 }}>
                      {aiSuggestion.signals.map((sig, i) => (
                        <li key={i}>{sig}</li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </section>
          )}

          <section>
            <h3 className="classify-section-title">Category</h3>
            <div className="classify-chip-grid" role="listbox" aria-label="Categories">
              {categories.map((cat) => {
                const active = cat.id === categoryId;
                return (
                  <button
                    key={cat.id}
                    type="button"
                    role="option"
                    aria-selected={active}
                    className={`classify-chip${active ? " active" : ""}`}
                    onClick={() => {
                      setCategoryId(cat.id);
                      setSubcategoryId("");
                    }}
                  >
                    {cat.name}
                  </button>
                );
              })}
            </div>
          </section>

          {selectedCategory && selectedCategory.subcategories.length > 0 && (
            <section>
              <h3 className="classify-section-title">Subcategory</h3>
              <div className="classify-chip-grid" role="listbox" aria-label="Subcategories">
                <button
                  type="button"
                  role="option"
                  aria-selected={subcategoryId === ""}
                  className={`classify-chip${subcategoryId === "" ? " active" : ""}`}
                  onClick={() => setSubcategoryId("")}
                >
                  None
                </button>
                {selectedCategory.subcategories.map((sub) => {
                  const active = sub.id === subcategoryId;
                  return (
                    <button
                      key={sub.id}
                      type="button"
                      role="option"
                      aria-selected={active}
                      className={`classify-chip${active ? " active" : ""}`}
                      onClick={() => setSubcategoryId(sub.id)}
                    >
                      {sub.name}
                    </button>
                  );
                })}
              </div>
            </section>
          )}

          <section className="classify-exclude">
            <h3 className="classify-section-title">Not a transaction?</h3>
            <p className="metric-hint">
              Use this when the email is not a real bank/UPI transaction. Removes it from Needs
              Review, keeps it out of spending totals, and skips it on later syncs.
            </p>
            <button
              className={`btn classify-exclude-btn${excludeArmed ? " confirm-armed" : ""}`}
              type="button"
              disabled={saving}
              onClick={triggerExclude}
            >
              {saving
                ? "Saving…"
                : excludeArmed
                  ? "Click again to confirm"
                  : count === 1
                    ? "Exclude — not a valid transaction email"
                    : `Exclude ${count} — not valid transaction emails`}
            </button>
          </section>

          <section className="classify-exclude">
            <h3 className="classify-section-title">Reimbursement?</h3>
            <p className="metric-hint">
              Covers both sides: a purchase you fronted for someone else (debit), or the payment
              they sent back to repay you (credit). Either way it's real money movement, but it's
              not your spending or income — it stays on the ledger, excluded from both totals, and
              clears Needs Review.
            </p>
            <button
              className={`btn classify-exclude-btn${reimburseArmed ? " confirm-armed" : ""}`}
              type="button"
              disabled={saving}
              onClick={triggerReimburse}
            >
              {saving
                ? "Saving…"
                : reimburseArmed
                  ? "Click again to confirm"
                  : count === 1
                    ? "Exclude — this is a reimbursement"
                    : `Exclude ${count} — reimbursements`}
            </button>
          </section>

          {error && <p className="error">{error}</p>}

          <div className="classify-panel-footer">
            <button
              className="btn primary"
              type="button"
              disabled={saving || !categoryId}
              onClick={() => onSave(categoryId, subcategoryId || null)}
            >
              {saving
                ? "Saving…"
                : count === 1
                  ? "Save & verify"
                  : `Save & verify ${count}`}
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}
