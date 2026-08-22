import { useEffect, useId, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api, type AISuggestion, type CategoryTree, type Transaction } from "../api";
import { formatDate, formatMoney } from "../format";
import { getCategoryIcon } from "../utils/categoryIcons";
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
        style={{ display: "flex", flexDirection: "column", maxHeight: "86dvh" }}
      >
        <div className="sheet-handle" onClick={onClose} aria-label="Dismiss sheet" />

        <header className="modal-header" style={{ flexShrink: 0, background: "var(--surface)" }}>
          <div>
            <h2 id={titleId} style={{ fontSize: "1.15rem", fontWeight: 700 }}>
              {count === 1 ? "Classify transaction" : `Classify ${count} transactions`}
            </h2>
            <p className="metric-hint">
              Choose a category, then save to verify and clear Needs Review.
            </p>
          </div>
          <div className="modal-actions">
            <button
              ref={closeRef}
              className="btn icon-btn"
              type="button"
              onClick={onClose}
              disabled={saving}
              aria-label="Close"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
            </button>
          </div>
        </header>

        <div className="modal-body classify-panel-body" style={{ overflowY: "auto", flex: "1 1 auto", WebkitOverflowScrolling: "touch" }}>
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
                        {formatMoney(tx.amount ?? 0, tx.currency)} · {formatDate(tx.transaction_date)}
                      </span>
                      <button
                        className="icon-action"
                        type="button"
                        title="Flag an issue with this transaction"
                        aria-label="Flag issue"
                        onClick={() => onFlag(tx)}
                      >
                        <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" focusable="false">
                          <path
                            fill="currentColor"
                            d="M14.4 6 14 4H5v17h2v-7h5.6l.4 2h7V6z"
                          />
                        </svg>
                      </button>
                    </span>
                  </li>
                );
              })}
            </ul>
            {remaining > 0 && (
              <p className="metric-hint" style={{ marginTop: 6 }}>
                + {remaining} more selected
              </p>
            )}
          </section>

          {aiLoading && (
            <div style={{ padding: "10px 14px", background: "var(--accent-soft)", borderRadius: "var(--radius-sm)", border: "1px solid var(--line)", display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ fontSize: "1rem" }}>✨</span>
              <span style={{ fontSize: "0.85rem", color: "var(--accent)", fontWeight: 500 }}>
                Checking smart suggestion…
              </span>
            </div>
          )}

          {aiSuggestion && (
            <section
              style={{
                padding: "12px 14px",
                background: "var(--accent-soft)",
                borderRadius: "var(--radius)",
                border: "1px solid var(--accent)",
                marginBottom: "16px",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span style={{ fontSize: "1rem" }}>✨</span>
                  <span style={{ fontSize: "0.78rem", fontWeight: 700, color: "var(--accent)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                    Suggested
                  </span>
                </div>
                <span style={{ fontSize: "0.75rem", color: "var(--ink-muted)", fontWeight: 500 }}>
                  {Math.round(aiSuggestion.confidence * 100)}% confident
                </span>
              </div>

              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
                <div>
                  <div style={{ fontWeight: 600, color: "var(--ink)", display: "flex", alignItems: "center", gap: 6, fontSize: "0.95rem" }}>
                    <span aria-hidden="true">{getCategoryIcon(aiSuggestion.category_name)}</span>
                    <span>
                      {aiSuggestion.category_name}
                      {aiSuggestion.subcategory_name && (
                        <span style={{ color: "var(--ink-muted)", fontWeight: 400 }}> › {aiSuggestion.subcategory_name}</span>
                      )}
                    </span>
                  </div>
                  {aiSuggestion.signals.length > 0 && (
                    <div style={{ fontSize: "0.75rem", color: "var(--ink-muted)", marginTop: 2 }}>
                      Signals: {aiSuggestion.signals.join(" · ")}
                    </div>
                  )}
                </div>
                <button
                  type="button"
                  className="btn primary"
                  style={{ padding: "6px 14px", fontSize: "0.82rem", whiteSpace: "nowrap" }}
                  onClick={() => {
                    setCategoryId(aiSuggestion.category_id);
                    if (aiSuggestion.subcategory_id) {
                      setSubcategoryId(aiSuggestion.subcategory_id);
                    } else {
                      setSubcategoryId("");
                    }
                  }}
                >
                  Use suggestion
                </button>
              </div>
            </section>
          )}

          {aiError && (
            <p className="metric-hint" style={{ color: "var(--warn)", margin: 0, fontSize: "0.8rem" }}>
              Note: {aiError}
            </p>
          )}

          {/* Progressive Disclosure Category Picker */}
          {selectedCategory ? (
            <>
              {/* Category Selected Breadcrumb State */}
              <section className="classify-categories" style={{ marginBottom: "16px" }}>
                <h3 className="classify-section-title" style={{ marginBottom: 6 }}>Category</h3>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    padding: "10px 14px",
                    background: "var(--surface)",
                    border: "1px solid var(--accent, #7c3aed)",
                    borderRadius: "var(--radius-sm)",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 8, fontWeight: 600, fontSize: "0.95rem", color: "var(--ink)" }}>
                    <span style={{ color: "var(--accent)", fontWeight: 700 }}>✓</span>
                    <span aria-hidden="true" style={{ fontSize: "1.05rem", lineHeight: 1 }}>
                      {getCategoryIcon(selectedCategory.name, selectedCategory.expense_type)}
                    </span>
                    <span>{selectedCategory.name}</span>
                  </div>
                  <button
                    type="button"
                    className="btn quiet"
                    onClick={() => {
                      setCategoryId("");
                      setSubcategoryId("");
                    }}
                    style={{
                      fontSize: "0.84rem",
                      padding: "4px 10px",
                      color: "var(--accent)",
                      fontWeight: 600,
                      height: "auto",
                      lineHeight: 1.3,
                    }}
                  >
                    Change
                  </button>
                </div>
              </section>

              {/* Subcategory Picker */}
              <section className="classify-subcategories" style={{ marginBottom: "16px" }}>
                <h3 className="classify-section-title" style={{ marginBottom: 6 }}>Subcategory</h3>
                {selectedCategory.subcategories.length > 0 ? (
                  <div className="classify-chip-grid" role="listbox" aria-label="Subcategories">
                    <button
                      type="button"
                      role="option"
                      aria-selected={subcategoryId === ""}
                      className={`classify-chip${subcategoryId === "" ? " active" : ""}`}
                      onClick={() => setSubcategoryId("")}
                    >
                      {subcategoryId === "" && <span style={{ marginRight: 5 }}>✓</span>}
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
                          {active && <span style={{ marginRight: 5 }}>✓</span>}
                          {sub.name}
                        </button>
                      );
                    })}
                  </div>
                ) : (
                  <p className="metric-hint" style={{ margin: 0, fontSize: "0.84rem" }}>
                    No specific subcategories for {selectedCategory.name}.
                  </p>
                )}
              </section>
            </>
          ) : (
            /* Initial State: Full Category Grid */
            <section className="classify-categories" style={{ marginBottom: "16px" }}>
              <h3 className="classify-section-title" style={{ marginBottom: 8 }}>Category</h3>
              <div className="classify-chip-grid" role="listbox" aria-label="Categories">
                {categories.map((cat) => (
                  <button
                    key={cat.id}
                    type="button"
                    role="option"
                    aria-selected={false}
                    className="classify-chip"
                    onClick={() => {
                      setCategoryId(cat.id);
                      setSubcategoryId("");
                    }}
                  >
                    <span aria-hidden="true" style={{ marginRight: 6 }}>
                      {getCategoryIcon(cat.name, cat.expense_type)}
                    </span>
                    <span>{cat.name}</span>
                  </button>
                ))}
              </div>
            </section>
          )}

          <section style={{ marginTop: "16px", paddingTop: "14px", borderTop: "1px solid var(--line)" }}>
            <div style={{ fontSize: "11px", color: "var(--ink-muted)", fontWeight: 500, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 8 }}>
              Other Actions
            </div>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              <button
                className={`btn quiet${excludeArmed ? " confirm-armed" : ""}`}
                type="button"
                disabled={saving}
                onClick={triggerExclude}
                style={{
                  fontSize: "0.82rem",
                  padding: "6px 12px",
                  height: "36px",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                  color: excludeArmed ? "var(--debit, #ef4444)" : "var(--ink-muted)",
                  border: "1px solid var(--line)",
                  borderRadius: "var(--radius-sm)",
                }}
                title="Exclude: not a valid bank or transaction email. Clears from Needs Review and ignores from spending."
              >
                <span>🚫</span>
                <span>{excludeArmed ? "Confirm: Not a transaction" : "Not a transaction"}</span>
              </button>

              <button
                className={`btn quiet${reimburseArmed ? " confirm-armed" : ""}`}
                type="button"
                disabled={saving}
                onClick={triggerReimburse}
                style={{
                  fontSize: "0.82rem",
                  padding: "6px 12px",
                  height: "36px",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                  color: reimburseArmed ? "var(--credit, #10b981)" : "var(--ink-muted)",
                  border: "1px solid var(--line)",
                  borderRadius: "var(--radius-sm)",
                }}
                title="Exclude: purchase fronted or repayment received. Excluded from spending and clears Needs Review."
              >
                <span>🤝</span>
                <span>{reimburseArmed ? "Confirm: Reimbursement" : "Reimbursement"}</span>
              </button>
            </div>
          </section>

          {error && <p className="error">{error}</p>}
        </div>

        <footer
          className="modal-footer classify-panel-footer"
          style={{
            flexShrink: 0,
            background: "var(--surface)",
            borderTop: "1px solid var(--line)",
            padding: "12px 18px max(16px, env(safe-area-inset-bottom, 16px))",
            display: "flex",
            gap: 10,
          }}
        >
          <button
            className="btn quiet"
            type="button"
            onClick={onClose}
            disabled={saving}
            style={{ padding: "12px 18px" }}
          >
            Cancel
          </button>
          <button
            className="btn primary"
            type="button"
            disabled={saving || !categoryId}
            onClick={() => onSave(categoryId, subcategoryId || null)}
            style={{ flex: 1, padding: "12px 18px", fontSize: "0.95rem", fontWeight: 600 }}
          >
            {saving
              ? "Saving…"
              : count === 1
                ? "Save & verify"
                : `Save & verify ${count}`}
          </button>
        </footer>
      </div>
    </div>,
    document.body,
  );
}
