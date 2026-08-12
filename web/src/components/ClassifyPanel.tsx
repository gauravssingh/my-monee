import { useEffect, useId, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { CategoryTree, Transaction } from "../api";
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

  useModalChrome(open, onClose, closeRef);
  const onBackdropClick = useBackdropClose(open, onClose);
  const { armed: excludeArmed, trigger: triggerExclude } = useConfirm(onExclude);
  const { armed: reimburseArmed, trigger: triggerReimburse } = useConfirm(onReimburse);

  useEffect(() => {
    if (!open) return;
    setCategoryId("");
    setSubcategoryId("");
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
