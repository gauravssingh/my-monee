import { createPortal } from "react-dom";
import { type Transaction } from "../api";
import { formatDate, formatMoney, formatSource } from "../format";
import { useBackdropClose, useModalChrome } from "../hooks/useModalChrome";
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
  const isVisible = open && Boolean(transaction);
  useModalChrome(isVisible, onClose);
  const onBackdropClick = useBackdropClose(isVisible, onClose);

  if (!open || !transaction) return null;

  const isCredit = transaction.direction === "credit";
  const merchant = transaction.merchant_normalized || transaction.merchant_raw || "Unidentified Merchant";
  const rawMerchant = transaction.merchant_raw;

  return createPortal(
    <div className="modal-backdrop" role="presentation" onClick={onBackdropClick}>
      <div
        className="modal-panel transaction-detail-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="tx-detail-title"
        style={{ width: "min(560px, 100%)", padding: "24px", boxSizing: "border-box" }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header Strip */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "18px" }}>
          <div style={{ minWidth: 0, flex: "1 1 auto" }}>
            <div style={{ fontSize: "11px", color: "var(--ink-muted)", fontWeight: 500, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 3 }}>
              Transaction Details
            </div>
            <h2
              id="tx-detail-title"
              style={{
                margin: 0,
                fontSize: "22px",
                fontWeight: 600,
                lineHeight: 1.25,
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
                maxWidth: "380px",
              }}
              title={merchant}
            >
              {merchant}
            </h2>
            <div style={{ fontSize: "13px", color: "var(--ink-muted)", marginTop: 4 }}>
              {formatDate(transaction.transaction_date)}
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 10, flexShrink: 0 }}>
            {transaction.source_email_id && (
              <button
                type="button"
                className="btn quiet"
                onClick={() => {
                  if (onViewEmail) {
                    onViewEmail(transaction);
                  } else if (transaction.source_email_id) {
                    openInGmail(transaction.source_email_id);
                  }
                }}
                style={{
                  fontSize: "13px",
                  color: "var(--ink-muted)",
                  padding: "4px 8px",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 5,
                  fontWeight: 500,
                }}
                title="View source notification email"
              >
                <span style={{ fontSize: "14px" }}>✉</span>
                <span>Email</span>
                <span style={{ fontSize: "11px", opacity: 0.8 }}>↗</span>
              </button>
            )}
            <button
              type="button"
              className="btn quiet"
              onClick={onClose}
              aria-label="Close"
              style={{ fontSize: "1.25rem", padding: "4px 8px", lineHeight: 1 }}
            >
              ×
            </button>
          </div>
        </div>

        {/* Amount & Classification Banner */}
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
            <div style={{ fontSize: "11px", color: "var(--ink-muted)", fontWeight: 500, letterSpacing: "0.04em" }}>
              {isCredit ? "INFLOW / CREDIT" : "OUTFLOW / DEBIT"}
            </div>
            <div
              style={{
                fontSize: "24px",
                fontWeight: 700,
                fontVariantNumeric: "tabular-nums",
                color: isCredit ? "var(--credit)" : "var(--debit)",
                marginTop: 2,
              }}
            >
              {isCredit ? "+" : "−"}
              {formatMoney(transaction.amount ?? 0, transaction.currency)}
            </div>
          </div>
          <div>
            {transaction.needs_review ? (
              <span className="badge review" style={{ fontSize: "12px", padding: "4px 9px", fontWeight: 600 }}>
                ⚠ Needs Review
              </span>
            ) : (
              <span className="badge ok" style={{ fontSize: "12px", padding: "4px 9px", fontWeight: 600 }}>
                ✓ Classified
              </span>
            )}
          </div>
        </div>

        {/* Structured Field Grid */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px 14px", marginBottom: "20px" }}>
          <div>
            <div style={{ fontSize: "11px", color: "var(--ink-muted)", fontWeight: 500, textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 4 }}>
              Category
            </div>
            <div
              style={{
                fontSize: "14px",
                lineHeight: 1.4,
                display: "flex",
                alignItems: "center",
                flexWrap: "wrap",
                gap: "6px",
                color: "var(--ink)",
              }}
            >
              {transaction.category ? (
                <>
                  <span style={{ fontSize: "15px", lineHeight: 1, display: "inline-flex", alignItems: "center" }} aria-hidden="true">
                    {getCategoryIcon(transaction.category)}
                  </span>
                  <span style={{ fontWeight: 600 }}>{transaction.category}</span>
                  {transaction.subcategory && (
                    <span style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}>
                      <span style={{ color: "var(--ink-muted)", fontWeight: 400, fontSize: "13px" }}>→</span>
                      <span style={{ fontWeight: 500, color: "var(--ink)" }}>{transaction.subcategory}</span>
                    </span>
                  )}
                </>
              ) : (
                <span style={{ color: "var(--ink-muted)", fontWeight: 400 }}>Uncategorized</span>
              )}
            </div>
          </div>

          <div>
            <div style={{ fontSize: "11px", color: "var(--ink-muted)", fontWeight: 500, textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 4 }}>
              Account
            </div>
            <div style={{ fontWeight: 600, fontSize: "14px", lineHeight: 1.4 }}>
              {transaction.account || <span style={{ color: "var(--ink-muted)", fontWeight: 400 }}>Unknown / Unlinked</span>}
            </div>
          </div>

          <div>
            <div style={{ fontSize: "11px", color: "var(--ink-muted)", fontWeight: 500, textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 4 }}>
              Classification Source
            </div>
            <div style={{ fontSize: "14px", color: "var(--ink)", lineHeight: 1.4, fontWeight: 500 }}>
              {formatSource(transaction.classification_source)}
            </div>
          </div>

          <div>
            <div style={{ fontSize: "11px", color: "var(--ink-muted)", fontWeight: 500, textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 4 }}>
              Transaction Type
            </div>
            <div style={{ fontSize: "14px", textTransform: "capitalize", color: "var(--ink)", lineHeight: 1.4, fontWeight: 500 }}>
              {transaction.transaction_type || "Purchase"}
            </div>
          </div>
        </div>

        {/* Raw Bank Notification / Description */}
        <div style={{ marginBottom: "24px" }}>
          <div style={{ fontSize: "11px", color: "var(--ink-muted)", fontWeight: 500, textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 6 }}>
            Raw Bank Notification / Description
          </div>
          <div
            style={{
              padding: "10px 14px",
              background: "var(--surface-muted, rgba(0,0,0,0.02))",
              border: "1px solid var(--line)",
              borderRadius: "var(--radius-sm)",
              fontSize: "13px",
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
          <div style={{ display: "flex", gap: "10px", flexWrap: "wrap", alignItems: "center" }}>
            {onMarkRecurring && (
              <button
                type="button"
                className="btn quiet"
                onClick={() => onMarkRecurring(transaction)}
                style={{ fontSize: "0.82rem", height: "36px", padding: "0 12px", display: "inline-flex", alignItems: "center", gap: 5 }}
              >
                <span>↻</span>
                <span>Recurring</span>
              </button>
            )}
            {onFlagIssue && (
              <button
                type="button"
                className="btn quiet"
                onClick={() => onFlagIssue(transaction)}
                style={{ fontSize: "0.82rem", height: "36px", padding: "0 12px", display: "inline-flex", alignItems: "center", gap: 5 }}
              >
                <span>⚑</span>
                <span>Flag issue</span>
              </button>
            )}
          </div>

          <div style={{ marginLeft: "auto" }}>
            {onClassify && (
              <button
                type="button"
                className="btn primary"
                onClick={() => onClassify(transaction)}
                style={{ fontSize: "0.84rem", height: "36px", padding: "0 16px" }}
              >
                Reclassify →
              </button>
            )}
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}
