import { createPortal } from "react-dom";
import { type Transaction } from "../api";
import { formatDate, formatMoney, formatSource } from "../format";
import { getCategoryIcon } from "../utils/categoryIcons";
import { openInGmail } from "../utils/gmail";

type Props = {
  open: boolean;
  transaction: Transaction | null;
  onClose: () => void;
  onClassify?: (tx: Transaction) => void;
  onViewEmail?: (tx: Transaction) => void;
  onMarkRecurring?: (tx: Transaction) => void;
  onFlagIssue?: (tx: Transaction) => void;
};

export default function TransactionDetailModal({
  open,
  transaction,
  onClose,
  onClassify,
  onViewEmail,
  onMarkRecurring,
  onFlagIssue,
}: Props) {
  if (!open || !transaction) return null;

  const isCredit = transaction.direction === "credit";
  const merchant = transaction.merchant_normalized || transaction.merchant_raw || "Unidentified Merchant";
  const rawMerchant = transaction.merchant_raw;

  return createPortal(
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="modal-panel transaction-detail-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="tx-detail-title"
        style={{ width: "min(560px, 100%)", padding: "24px", boxSizing: "border-box" }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header Strip */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "16px" }}>
          <div>
            <div style={{ fontSize: "0.78rem", color: "var(--ink-muted)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 2 }}>
              Transaction Details
            </div>
            <h2 id="tx-detail-title" style={{ margin: 0, fontSize: "1.35rem", wordBreak: "break-word", lineHeight: 1.25 }}>
              {merchant}
            </h2>
            <div style={{ fontSize: "0.85rem", color: "var(--ink-muted)", marginTop: 4 }}>
              {formatDate(transaction.transaction_date)}
            </div>
          </div>
          <button
            type="button"
            className="btn quiet"
            onClick={onClose}
            aria-label="Close"
            style={{ fontSize: "1.2rem", padding: "4px 8px", lineHeight: 1 }}
          >
            ×
          </button>
        </div>

        {/* Amount Hero Banner */}
        <div
          style={{
            padding: "14px 18px",
            background: "var(--surface)",
            border: "1px solid var(--line)",
            borderRadius: "var(--radius-sm)",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: "20px",
          }}
        >
          <div>
            <div style={{ fontSize: "0.75rem", color: "var(--ink-muted)", fontWeight: 500 }}>
              {isCredit ? "INFLOW / CREDIT" : "OUTFLOW / DEBIT"}
            </div>
            <div
              style={{
                fontSize: "1.65rem",
                fontWeight: 700,
                fontVariantNumeric: "tabular-nums",
                color: isCredit ? "var(--credit)" : "var(--debit)",
              }}
            >
              {isCredit ? "+" : "−"}
              {formatMoney(transaction.amount ?? 0, transaction.currency)}
            </div>
          </div>
          <div>
            {transaction.needs_review ? (
              <span className="badge review" style={{ fontSize: "0.82rem", padding: "4px 10px" }}>
                Needs Review
              </span>
            ) : (
              <span className="badge ok" style={{ fontSize: "0.82rem", padding: "4px 10px" }}>
                ✓ Classification OK
              </span>
            )}
          </div>
        </div>

        {/* Structured Field Grid */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "14px", marginBottom: "20px" }}>
          <div>
            <div style={{ fontSize: "0.74rem", color: "var(--ink-muted)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 3 }}>
              Category
            </div>
            <div style={{ fontWeight: 600, fontSize: "0.92rem", display: "flex", alignItems: "center", gap: 6 }}>
              {transaction.category ? (
                <>
                  <span style={{ fontSize: "1rem", lineHeight: 1 }} aria-hidden="true">
                    {getCategoryIcon(transaction.category)}
                  </span>
                  <span>{transaction.category}</span>
                </>
              ) : (
                <span>Uncategorized</span>
              )}
              {transaction.subcategory && (
                <span style={{ color: "var(--ink-muted)", fontWeight: 400 }}>→ {transaction.subcategory}</span>
              )}
            </div>
          </div>

          <div>
            <div style={{ fontSize: "0.74rem", color: "var(--ink-muted)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 3 }}>
              Account / Payment Method
            </div>
            <div style={{ fontWeight: 600, fontSize: "0.92rem" }}>
              {transaction.account || <span style={{ color: "var(--ink-muted)" }}>Unknown / Unlinked</span>}
            </div>
          </div>

          <div>
            <div style={{ fontSize: "0.74rem", color: "var(--ink-muted)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 3 }}>
              Classification Source
            </div>
            <div style={{ fontSize: "0.88rem", color: "var(--ink)" }}>
              {formatSource(transaction.classification_source)}
            </div>
          </div>

          <div>
            <div style={{ fontSize: "0.74rem", color: "var(--ink-muted)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 3 }}>
              Transaction Type
            </div>
            <div style={{ fontSize: "0.88rem", textTransform: "capitalize", color: "var(--ink)" }}>
              {transaction.transaction_type || "Purchase"}
            </div>
          </div>
        </div>

        {/* Raw Merchant / Description */}
        <div style={{ marginBottom: "24px" }}>
          <div style={{ fontSize: "0.74rem", color: "var(--ink-muted)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 4 }}>
            Raw Bank Notification / Description
          </div>
          <div
            style={{
              padding: "10px 12px",
              background: "var(--surface-muted, rgba(0,0,0,0.02))",
              border: "1px solid var(--line)",
              borderRadius: "var(--radius-sm)",
              fontSize: "0.84rem",
              lineHeight: 1.45,
              color: "var(--ink)",
              wordBreak: "break-word",
              maxHeight: 120,
              overflowY: "auto",
              fontFamily: "var(--font-mono, monospace)",
            }}
          >
            {transaction.description || rawMerchant || "No raw description available"}
          </div>
        </div>

        {/* Actions Footer */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexWrap: "wrap",
            gap: "10px",
            borderTop: "1px solid var(--line)",
            paddingTop: "16px",
          }}
        >
          <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
            {transaction.source_email_id && onViewEmail && (
              <button
                type="button"
                className="btn"
                onClick={() => onViewEmail(transaction)}
                style={{ fontSize: "0.82rem", display: "inline-flex", alignItems: "center", gap: 5 }}
              >
                <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
                  <path d="M20 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4-8 5L4 8V6l8 5 8-5v2z"/>
                </svg>
                View Email
              </button>
            )}
            {transaction.source_email_id && (
              <button
                type="button"
                className="btn quiet"
                onClick={() => openInGmail(transaction.source_email_id!)}
                style={{ fontSize: "0.82rem", display: "inline-flex", alignItems: "center", gap: 5 }}
                title="Launch native Gmail app on iOS/mobile or open web thread"
              >
                <span>Gmail App</span>
                <span style={{ fontSize: "0.74rem" }}>↗</span>
              </button>
            )}
            {onMarkRecurring && (
              <button
                type="button"
                className="btn"
                onClick={() => onMarkRecurring(transaction)}
                style={{ fontSize: "0.82rem" }}
              >
                ↻ Mark Recurring
              </button>
            )}
            {onFlagIssue && (
              <button
                type="button"
                className="btn"
                onClick={() => onFlagIssue(transaction)}
                style={{ fontSize: "0.82rem" }}
              >
                ⚑ Flag Issue
              </button>
            )}
          </div>

          <div style={{ display: "flex", gap: "8px", marginLeft: "auto" }}>
            {onClassify && (
              <button
                type="button"
                className="btn primary"
                onClick={() => onClassify(transaction)}
                style={{ fontSize: "0.84rem" }}
              >
                Reclassify →
              </button>
            )}
            <button type="button" className="btn quiet" onClick={onClose} style={{ fontSize: "0.84rem" }}>
              Close
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}
