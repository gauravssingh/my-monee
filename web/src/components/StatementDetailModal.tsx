import { useState, useId, useRef } from "react";
import { createPortal } from "react-dom";
import { api, type CreditCardStatement, type StatementTransaction } from "../api";
import { useToast } from "../hooks/useToast";
import { useBackdropClose, useModalChrome } from "../hooks/useModalChrome";
import { GmailLogo } from "./GmailLogo";
import { DownloadIcon } from "./DownloadIcon";

function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return "—";
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
  } catch {
    return dateStr;
  }
}

function formatPeriod(startStr: string | null | undefined, endStr: string | null | undefined): string {
  if (!startStr && !endStr) return "—";
  if (startStr && endStr) {
    return `${formatDate(startStr)} – ${formatDate(endStr)}`;
  }
  return formatDate(startStr || endStr);
}

function extractUpiRrn(text: string | null | undefined): string | null {
  if (!text) return null;
  const m = text.match(/(?:UPI[/-](?:[A-Za-z0-9]+[/-])?)?(\d{12})\b/i);
  return m ? m[1] : null;
}

function getStatementTitle(stmt: CreditCardStatement): string {
  const issuerName = stmt.account_name || stmt.issuer || "Statement";
  let monthYear = "";
  if (stmt.statement_period_end || stmt.statement_date) {
    try {
      const d = new Date(stmt.statement_period_end || stmt.statement_date || "");
      monthYear = d.toLocaleDateString("en-IN", { month: "long", year: "numeric" });
    } catch {
      monthYear = "";
    }
  }
  const typeLabel = stmt.statement_type === "BANK_ACCOUNT" ? "Bank Statement" : "Credit Card Statement";
  return monthYear ? `${issuerName} — ${monthYear} ${typeLabel}` : `${issuerName} ${typeLabel}`;
}

function getStatusBadge(status: string, validationStatus?: string | null) {
  if (status === "VALIDATED" || validationStatus === "VALIDATED") {
    return <span className="badge" style={{ background: "rgba(16, 185, 129, 0.15)", color: "var(--success, #10b981)", fontWeight: 600 }}>✓ Validated</span>;
  }
  if (status === "REVIEW_REQUIRED" || validationStatus === "REVIEW_REQUIRED") {
    return <span className="badge" style={{ background: "rgba(245, 158, 11, 0.15)", color: "var(--warning, #f59e0b)", fontWeight: 600 }}>⚠ Review Required</span>;
  }
  switch (status) {
    case "READY_FOR_EXTRACTION":
    case "UNLOCKED":
      return <span className="badge" style={{ background: "rgba(59, 130, 246, 0.15)", color: "var(--accent, #3b82f6)", fontWeight: 600 }}>⚡ Ready to Extract</span>;
    case "PASSWORD_REQUIRED":
      return <span className="badge" style={{ background: "rgba(245, 158, 11, 0.15)", color: "var(--warning, #f59e0b)", fontWeight: 600 }}>🔒 Needs Unlocking</span>;
    case "PASSWORD_FAILED":
      return <span className="badge" style={{ background: "rgba(239, 68, 68, 0.15)", color: "var(--danger, #ef4444)", fontWeight: 600 }}>⚠ Password Failed</span>;
    case "EXTRACTION_FAILED":
    case "VALIDATION_FAILED":
    case "INVALID_PDF":
    case "DOWNLOAD_FAILED":
      return <span className="badge" style={{ background: "rgba(239, 68, 68, 0.15)", color: "var(--danger, #ef4444)", fontWeight: 600 }}>✕ Failed</span>;
    default:
      return <span className="badge">{status}</span>;
  }
}

function getMatchBadge(status: string) {
  switch (status) {
    case "MATCHED":
      return <span className="badge" style={{ background: "rgba(16, 185, 129, 0.15)", color: "var(--success, #10b981)", fontSize: "0.68rem", fontWeight: 600 }}>✓ MATCHED</span>;
    case "POSSIBLE_MATCH":
      return <span className="badge" style={{ background: "rgba(245, 158, 11, 0.15)", color: "var(--warning, #f59e0b)", fontSize: "0.68rem", fontWeight: 600 }}>⚠ POSSIBLE MATCH</span>;
    case "LIABILITY_PAYMENT":
      return <span className="badge" style={{ background: "rgba(139, 92, 246, 0.15)", color: "#8b5cf6", fontSize: "0.68rem", fontWeight: 600 }}>⇄ SETTLEMENT</span>;
    default:
      return <span className="badge" style={{ opacity: 0.6, fontSize: "0.68rem" }}>○ UNMATCHED</span>;
  }
}

export function StatementDetailModal({
  open,
  statement,
  onClose,
  onStatementUpdated,
}: {
  open: boolean;
  statement: CreditCardStatement | null;
  onClose: () => void;
  onStatementUpdated?: (updated: CreditCardStatement) => void;
}) {
  const titleId = useId();
  const closeRef = useRef<HTMLButtonElement>(null);
  const { showToast } = useToast();

  // All Hooks Declared at the Top Unconditionally
  const [password, setPassword] = useState("");
  const [saveToProfile, setSaveToProfile] = useState(true);
  const [showPassword, setShowPassword] = useState(false);
  const [unlocking, setUnlocking] = useState(false);
  const [reExtracting, setReExtracting] = useState(false);
  const [reconciling, setReconciling] = useState(false);
  const [updatingMatch, setUpdatingMatch] = useState(false);
  const [importingTxId, setImportingTxId] = useState<string | null>(null);
  const [importingBundle, setImportingBundle] = useState(false);
  const [scanningTxId, setScanningTxId] = useState<string | null>(null);
  const [activeStatement, setActiveStatement] = useState<CreditCardStatement | null>(statement);
  const [reconFilter, setReconFilter] = useState<"ALL" | "MATCHED" | "REVIEW" | "UNMATCHED">("ALL");
  const [selectedReviewTx, setSelectedReviewTx] = useState<StatementTransaction | null>(null);
  const [showAuditDetails, setShowAuditDetails] = useState(false);

  useModalChrome(open, onClose, closeRef);
  const onBackdropClick = useBackdropClose(open, onClose);

  // Sync state when incoming statement changes
  if (statement && activeStatement?.id !== statement.id) {
    setActiveStatement(statement);
    setPassword("");
    setReconFilter("ALL");
    setSelectedReviewTx(null);
  }

  if (!open || !activeStatement) return null;

  const currentStmt = activeStatement;
  const isLocked = currentStmt.status === "PASSWORD_REQUIRED" || currentStmt.status === "PASSWORD_FAILED";
  const isBank = currentStmt.statement_type === "BANK_ACCOUNT";
  const gmailUrl = currentStmt.gmail_url || (currentStmt.source_email_id ? `https://mail.google.com/mail/u/0/#all/${currentStmt.source_email_id}` : null);

  const transactions = currentStmt.transactions || [];
  const matchedCount = transactions.filter((t) => t.match_status === "MATCHED" || t.match_status === "LIABILITY_PAYMENT").length;
  const reviewCount = transactions.filter((t) => t.match_status === "POSSIBLE_MATCH").length;
  const unmatchedCount = transactions.filter((t) => !t.match_status || t.match_status === "UNMATCHED").length;

  const filteredTransactions = transactions.filter((tx) => {
    if (reconFilter === "MATCHED") return tx.match_status === "MATCHED" || tx.match_status === "LIABILITY_PAYMENT";
    if (reconFilter === "REVIEW") return tx.match_status === "POSSIBLE_MATCH";
    if (reconFilter === "UNMATCHED") return !tx.match_status || tx.match_status === "UNMATCHED";
    return true;
  });

  // Detect and group EMI bundles on the statement
  const emiBundles = (() => {
    const bundles: Array<{
      date: string;
      merchant: string;
      installment: number;
      tenure: number;
      totalAmount: number;
      txs: StatementTransaction[];
      allMatched: boolean;
    }> = [];

    const emiTxs = transactions.filter((t) => /EMI\s+(PRINCIPAL|INTEREST)/i.test(t.description));
    const processedIds = new Set<string>();

    for (const tx of emiTxs) {
      if (processedIds.has(tx.id)) continue;
      const match = tx.description.match(/EMI\s+(?:PRINCIPAL|INTEREST)\s*-\s*(\d+)\/(\d+)(?:,?\s*REF#?\s*([A-Za-z0-9]+))?(?:\s+(.*))?/i);
      if (!match) continue;

      const inst = parseInt(match[1], 10);
      const ten = parseInt(match[2], 10);
      const merchantTag = (match[4] || "").trim();
      const dateStr = (tx.transaction_date || "").slice(0, 10);

      // Find related items (Principal, Interest, GST on this date)
      const related = transactions.filter((other) => {
        if ((other.transaction_date || "").slice(0, 10) !== dateStr) return false;
        if (/EMI\s+(?:PRINCIPAL|INTEREST)/i.test(other.description)) {
          return other.description.includes(`${inst}/${ten}`);
        }
        if (/^GST\b/i.test(other.description)) {
          return true;
        }
        return false;
      });

      related.forEach((r) => processedIds.add(r.id));
      const total = related.reduce((sum, r) => sum + r.amount, 0);
      const allMatched = related.every((r) => r.match_status === "MATCHED");

      bundles.push({
        date: dateStr,
        merchant: merchantTag || "EMI Plan",
        installment: inst,
        tenure: ten,
        totalAmount: total,
        txs: related,
        allMatched,
      });
    }
    return bundles;
  })();

  const handleManualUnlock = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!password.trim()) {
      showToast("Please enter a password", "error");
      return;
    }

    setUnlocking(true);
    try {
      const updated = await api.unlockStatement(currentStmt.id, {
        password: password.trim(),
        save_to_profile: saveToProfile,
        strategy: "CUSTOM",
      });
      setActiveStatement(updated);
      showToast("Statement successfully unlocked and extracted!", "success");
      if (onStatementUpdated) onStatementUpdated(updated);
      setPassword("");
    } catch (err: any) {
      showToast(err.message || "Failed to unlock statement", "error");
    } finally {
      setUnlocking(false);
    }
  };

  const handleReExtract = async () => {
    setReExtracting(true);
    try {
      const updated = await api.reExtractStatement(currentStmt.id);
      setActiveStatement(updated);
      showToast("Statement re-extracted and validated successfully!", "success");
      if (onStatementUpdated) onStatementUpdated(updated);
    } catch (err: any) {
      showToast(err.message || "Failed to re-extract statement", "error");
    } finally {
      setReExtracting(false);
    }
  };

  const handleReconcile = async () => {
    setReconciling(true);
    try {
      const res = await api.reconcileStatement(currentStmt.id);
      setActiveStatement(res.statement);
      showToast(`Reconciled: ${res.reconciliation.matched} matched, ${res.reconciliation.liability_payments} settlements`, "success");
      if (onStatementUpdated) onStatementUpdated(res.statement);
    } catch (err: any) {
      showToast(err.message || "Failed to reconcile statement", "error");
    } finally {
      setReconciling(false);
    }
  };

  const handleConfirmMatch = async (tx: StatementTransaction) => {
    setUpdatingMatch(true);
    try {
      const res = await api.updateTransactionMatch(currentStmt.id, tx.id, {
        match_status: "MATCHED",
        match_reason: `Manually confirmed (${tx.match_reason || "User verified"})`,
      });
      setActiveStatement(res.statement);
      if (onStatementUpdated) onStatementUpdated(res.statement);
      showToast("Transaction match confirmed!", "success");
      setSelectedReviewTx(null);
    } catch (err: any) {
      showToast(err.message || "Failed to confirm match", "error");
    } finally {
      setUpdatingMatch(false);
    }
  };

  const handleRejectMatch = async (tx: StatementTransaction) => {
    setUpdatingMatch(true);
    try {
      const res = await api.updateTransactionMatch(currentStmt.id, tx.id, {
        match_status: "UNMATCHED",
        match_reason: "Marked as non-match by user",
      });
      setActiveStatement(res.statement);
      if (onStatementUpdated) onStatementUpdated(res.statement);
      showToast("Transaction marked as unmatched.", "info");
      setSelectedReviewTx(null);
    } catch (err: any) {
      showToast(err.message || "Failed to update match", "error");
    } finally {
      setUpdatingMatch(false);
    }
  };

  const handleImportToLedger = async (tx: StatementTransaction) => {
    setImportingTxId(tx.id);
    try {
      const res = await api.importStatementTransaction(currentStmt.id, tx.id);
      setActiveStatement(res.statement);
      if (onStatementUpdated) onStatementUpdated(res.statement);
      showToast("Transaction added to ledger and matched!", "success");
      setSelectedReviewTx(null);
    } catch (err: any) {
      showToast(err.message || "Failed to import transaction", "error");
    } finally {
      setImportingTxId(null);
    }
  };

  const handleImportEmiBundle = async (txIds: string[]) => {
    setImportingBundle(true);
    try {
      const res = await api.importStatementBundle(currentStmt.id, txIds);
      setActiveStatement(res.statement);
      if (onStatementUpdated) onStatementUpdated(res.statement);
      showToast(`EMI bundle (${res.imported_count} items) imported to ledger!`, "success");
    } catch (err: any) {
      showToast(err.message || "Failed to import EMI bundle", "error");
    } finally {
      setImportingBundle(false);
    }
  };

  const handleScanGmail = async (tx: StatementTransaction) => {
    setScanningTxId(tx.id);
    try {
      const res = await api.scanGmailForTransaction(currentStmt.id, tx.id);
      if (res.found) {
        setActiveStatement(res.statement);
        if (onStatementUpdated) onStatementUpdated(res.statement);
        showToast(res.message, "success");
        setSelectedReviewTx(null);
      } else {
        showToast(res.message || "No matching email found in Gmail", "info");
      }
    } catch (err: any) {
      showToast(err.message || "Failed to search Gmail", "error");
    } finally {
      setScanningTxId(null);
    }
  };

  const valDetails = currentStmt.validation_details;
  const primaryEquation = valDetails?.equations && valDetails.equations.length > 0 ? valDetails.equations[0] : null;

  return createPortal(
    <div className="modal-backdrop" role="presentation" onClick={onBackdropClick}>
      <div
        className="modal-panel"
        aria-labelledby={titleId}
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "100%",
          maxWidth: "min(1160px, 94vw)",
          display: "flex",
          flexDirection: "column",
          height: "min(920px, 94dvh)",
          maxHeight: "94dvh",
          boxSizing: "border-box",
          borderRadius: "var(--radius-lg, 12px)",
        }}
      >
        <div className="sheet-handle" onClick={onClose} aria-label="Dismiss sheet" />

        {/* Level 1: Persistent Statement Identity Header */}
        <header
          className="modal-header"
          style={{
            flexShrink: 0,
            borderBottom: "1px solid var(--line)",
            padding: "16px 24px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 16,
          }}
        >
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 3 }}>
              <span style={{ fontSize: "0.85rem", fontWeight: 600, color: "var(--ink)" }}>
                {currentStmt.account_name || currentStmt.issuer} {currentStmt.card_last4 ? `•••• ${currentStmt.card_last4}` : ""}
              </span>
              <span
                className="badge"
                style={{
                  fontSize: "0.68rem",
                  padding: "1px 6px",
                  background: isBank ? "rgba(59, 130, 246, 0.12)" : "rgba(139, 92, 246, 0.12)",
                  color: isBank ? "var(--accent, #3b82f6)" : "#8b5cf6",
                  border: "none",
                }}
              >
                {isBank ? "Bank Account" : "Credit Card"}
              </span>
              {getStatusBadge(currentStmt.status, currentStmt.validation_status)}
            </div>

            <h2 id={titleId} style={{ margin: 0, fontSize: "1.25rem", fontWeight: 700, color: "var(--ink)", wordBreak: "break-word" }}>
              {getStatementTitle(currentStmt)}
            </h2>

            <div style={{ fontSize: "0.78rem", color: "var(--ink-muted)", marginTop: 2 }}>
              <span>Period: <strong>{formatPeriod(currentStmt.statement_period_start, currentStmt.statement_period_end)}</strong></span>
              <span style={{ margin: "0 6px" }}>·</span>
              <span>Source: <span style={{ opacity: 0.9 }}>{currentStmt.original_filename}</span></span>
            </div>
          </div>

          <div className="modal-actions" style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
            {currentStmt.has_unlocked_file && (
              <>
                <button
                  type="button"
                  className="btn quiet"
                  disabled={reExtracting}
                  onClick={handleReExtract}
                  style={{ fontSize: "0.8rem", padding: "6px 12px" }}
                  title="Re-run deterministic parser & arithmetic validator"
                >
                  {reExtracting ? "Extracting..." : "⚡ Re-Extract"}
                </button>
                <button
                  type="button"
                  className="btn primary"
                  disabled={reconciling}
                  onClick={handleReconcile}
                  style={{ fontSize: "0.8rem", padding: "6px 12px" }}
                  title="Reconcile extracted transactions against notification alerts"
                >
                  {reconciling ? "Reconciling..." : "⇄ Reconcile"}
                </button>
              </>
            )}
            <button ref={closeRef} type="button" className="btn icon-btn" onClick={onClose} aria-label="Close modal">
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
            </button>
          </div>
        </header>

        {/* Scrollable Body Workspace */}
        <div
          className="modal-body"
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 16,
            flex: "1 1 0%",
            minHeight: 0,
            overflowY: "auto",
            padding: "18px 24px",
          }}
        >
          {/* Top Row: Compact Statement Summary Strip */}
          <section
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
              gap: 14,
              background: "var(--surface)",
              padding: "12px 18px",
              borderRadius: "var(--radius-md)",
              border: "1px solid var(--line)",
            }}
          >
            <div>
              <div style={{ fontSize: "0.7rem", color: "var(--ink-muted)", textTransform: "uppercase", fontWeight: 600 }}>Period</div>
              <div style={{ fontSize: "0.88rem", fontWeight: 600, marginTop: 3 }}>
                {formatPeriod(currentStmt.statement_period_start, currentStmt.statement_period_end)}
              </div>
            </div>

            <div>
              <div style={{ fontSize: "0.7rem", color: "var(--ink-muted)", textTransform: "uppercase", fontWeight: 600 }}>Statement Date</div>
              <div style={{ fontSize: "0.88rem", fontWeight: 500, marginTop: 3 }}>
                {formatDate(currentStmt.statement_date)}
              </div>
            </div>

            {currentStmt.payment_due_date && !isBank && (
              <div>
                <div style={{ fontSize: "0.7rem", color: "var(--ink-muted)", textTransform: "uppercase", fontWeight: 600 }}>Payment Due Date</div>
                <div style={{ fontSize: "0.88rem", fontWeight: 600, color: "var(--warning, #f59e0b)", marginTop: 3 }}>
                  {formatDate(currentStmt.payment_due_date)}
                </div>
              </div>
            )}

            {currentStmt.total_amount_due != null && (
              <div>
                <div style={{ fontSize: "0.7rem", color: "var(--ink-muted)", textTransform: "uppercase", fontWeight: 600 }}>
                  {isBank ? "Closing Balance" : "Total Payment Due"}
                </div>
                <div style={{ fontSize: "1rem", fontWeight: 700, color: "var(--ink)", marginTop: 3 }}>
                  ₹{currentStmt.total_amount_due.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </div>
              </div>
            )}

            <div>
              <div style={{ fontSize: "0.7rem", color: "var(--ink-muted)", textTransform: "uppercase", fontWeight: 600 }}>Source Email</div>
              <div style={{ fontSize: "0.84rem", fontWeight: 500, marginTop: 3, display: "flex", alignItems: "center", gap: 6 }}>
                {currentStmt.source_email_id ? (
                  <>
                    <GmailLogo size={13} />
                    <span>Gmail</span>
                    {gmailUrl && (
                      <a href={gmailUrl} target="_blank" rel="noreferrer" style={{ fontSize: "0.75rem", color: "var(--accent, #6366f1)", textDecoration: "none", fontWeight: 500 }}>
                        Open email →
                      </a>
                    )}
                  </>
                ) : (
                  "Manual Upload"
                )}
              </div>
            </div>
          </section>

          {/* Top Row: Documents + Financial Validation Side by Side */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))", gap: 14 }}>
            {/* Column 1: Documents */}
            <section
              style={{
                background: "var(--surface)",
                border: "1px solid var(--line)",
                borderRadius: "var(--radius-md)",
                padding: "14px 16px",
                display: "flex",
                flexDirection: "column",
                gap: 10,
              }}
            >
              <div style={{ fontSize: "0.7rem", textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--ink-muted)", fontWeight: 700 }}>
                Documents
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {/* Original PDF */}
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: 10,
                    padding: "8px 12px",
                    background: "rgba(255,255,255,0.02)",
                    border: "1px solid var(--line)",
                    borderRadius: "var(--radius-sm)",
                  }}
                >
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <span style={{ fontSize: "0.82rem", fontWeight: 600 }}>🔒 Original PDF</span>
                      <span className="badge" style={{ fontSize: "0.62rem", padding: "1px 4px" }}>Immutable</span>
                    </div>
                    <div style={{ fontSize: "0.72rem", color: "var(--ink-muted)", marginTop: 2 }}>
                      Preserved source as received
                    </div>
                  </div>
                  <a
                    href={api.statementOriginalUrl(currentStmt.id, false)}
                    target="_blank"
                    rel="noreferrer"
                    className="btn quiet"
                    style={{ fontSize: "0.76rem", padding: "4px 8px", display: "inline-flex", alignItems: "center", gap: 4 }}
                    title="Download original statement"
                  >
                    <DownloadIcon size={12} />
                    <span>Download</span>
                  </a>
                </div>

                {/* Unlocked PDF */}
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: 10,
                    padding: "8px 12px",
                    background: "rgba(255,255,255,0.02)",
                    border: "1px solid var(--line)",
                    borderRadius: "var(--radius-sm)",
                  }}
                >
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <span style={{ fontSize: "0.82rem", fontWeight: 600 }}>⚡ Unlocked Copy</span>
                      <span
                        className="badge"
                        style={{
                          fontSize: "0.62rem",
                          padding: "1px 4px",
                          background: currentStmt.has_unlocked_file ? "rgba(16, 185, 129, 0.12)" : "rgba(245, 158, 11, 0.12)",
                          color: currentStmt.has_unlocked_file ? "var(--success, #10b981)" : "var(--warning, #f59e0b)",
                        }}
                      >
                        {currentStmt.has_unlocked_file ? "Ready" : "Locked"}
                      </span>
                    </div>
                    <div style={{ fontSize: "0.72rem", color: "var(--ink-muted)", marginTop: 2 }}>
                      Derivative used for parsing
                    </div>
                  </div>
                  {currentStmt.has_unlocked_file ? (
                    <a
                      href={api.statementUnlockedUrl(currentStmt.id, false)}
                      target="_blank"
                      rel="noreferrer"
                      className="btn quiet"
                      style={{ fontSize: "0.76rem", padding: "4px 8px", display: "inline-flex", alignItems: "center", gap: 4 }}
                      title="Download unlocked PDF"
                    >
                      <DownloadIcon size={12} />
                      <span>Download</span>
                    </a>
                  ) : (
                    <span className="badge" style={{ fontSize: "0.7rem", color: "var(--ink-muted)" }}>Locked</span>
                  )}
                </div>
              </div>
            </section>

            {/* Column 2: Financial Validation */}
            {valDetails && (
              <section
                style={{
                  background: currentStmt.validation_status === "VALIDATED" ? "rgba(16, 185, 129, 0.03)" : "rgba(245, 158, 11, 0.03)",
                  border: `1px solid ${currentStmt.validation_status === "VALIDATED" ? "rgba(16, 185, 129, 0.25)" : "rgba(245, 158, 11, 0.25)"}`,
                  borderRadius: "var(--radius-md)",
                  padding: "14px 16px",
                  display: "flex",
                  flexDirection: "column",
                  gap: 8,
                }}
              >
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <div style={{ fontSize: "0.7rem", textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--ink-muted)", fontWeight: 700 }}>
                    Financial Validation
                  </div>
                  {primaryEquation && (
                    <span style={{ fontSize: "0.76rem", fontWeight: 600, color: primaryEquation.is_balanced ? "var(--success, #10b981)" : "var(--danger, #ef4444)" }}>
                      {primaryEquation.is_balanced ? "✓ Exact match (Diff: ₹0.00)" : `⚠ Diff: ₹${primaryEquation.difference.toFixed(2)}`}
                    </span>
                  )}
                </div>

                {primaryEquation && (
                  <div style={{ fontSize: "0.8rem", display: "flex", flexDirection: "column", gap: 3, background: "rgba(0,0,0,0.15)", padding: "8px 12px", borderRadius: "var(--radius-sm)", border: "1px solid var(--line)" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", color: "var(--ink-muted)", fontSize: "0.74rem" }}>
                      <span>{primaryEquation.name}</span>
                      <span>{primaryEquation.formula}</span>
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", marginTop: 2 }}>
                      <span>Calculated: <strong style={{ color: "var(--ink)" }}>₹{primaryEquation.calculated.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</strong></span>
                      <span>Reported: <strong style={{ color: "var(--ink)" }}>₹{primaryEquation.expected.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</strong></span>
                    </div>
                  </div>
                )}

                {valDetails.messages && valDetails.messages.length > 0 && (
                  <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                    {valDetails.messages.slice(0, 3).map((msg, i) => (
                      <div key={i} style={{ fontSize: "0.74rem", color: "var(--success, #10b981)", display: "flex", alignItems: "center", gap: 6 }}>
                        <span>✓</span>
                        <span>{msg.replace("✓ ", "")}</span>
                      </div>
                    ))}
                  </div>
                )}
              </section>
            )}
          </div>

          {/* Section: Password Unlock Form (if locked) */}
          {isLocked && (
            <section style={{ background: "rgba(245, 158, 11, 0.08)", border: "1px solid rgba(245, 158, 11, 0.3)", borderRadius: "var(--radius-md)", padding: 14 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--warning, #f59e0b)", fontWeight: 600, fontSize: "0.92rem" }}>
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect width="18" height="11" x="3" y="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
                Password Unlock Required
              </div>
              <p style={{ fontSize: "0.82rem", color: "var(--ink-muted)", margin: "6px 0 12px" }}>
                {currentStmt.error_message || "Could not automatically unlock this statement. Please enter the PDF password below."}
              </p>
              <form onSubmit={handleManualUnlock} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <div style={{ position: "relative", flex: 1 }}>
                    <input
                      type={showPassword ? "text" : "password"}
                      className="input"
                      placeholder="Enter statement PDF password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      style={{ width: "100%", paddingRight: 40 }}
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      style={{
                        position: "absolute",
                        right: 10,
                        top: "50%",
                        transform: "translateY(-50%)",
                        background: "none",
                        border: "none",
                        cursor: "pointer",
                        color: "var(--ink-muted)",
                        padding: 4,
                      }}
                      aria-label={showPassword ? "Hide password" : "Show password"}
                    >
                      {showPassword ? "👁" : "🔒"}
                    </button>
                  </div>
                  <button type="submit" className="btn primary" disabled={unlocking || !password.trim()}>
                    {unlocking ? "Unlocking..." : "Unlock & Extract"}
                  </button>
                </div>
                {currentStmt.account_id && (
                  <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: "0.8rem", color: "var(--ink-muted)", cursor: "pointer" }}>
                    <input
                      type="checkbox"
                      checked={saveToProfile}
                      onChange={(e) => setSaveToProfile(e.target.checked)}
                    />
                    Save this password strategy for future statements from this card/account
                  </label>
                )}
              </form>
            </section>
          )}

          {/* Level 2: Reconciliation Summary & Actionable Filter Workspace */}
          <section style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 10 }}>
              <div>
                <div style={{ fontSize: "0.72rem", textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--ink-muted)", fontWeight: 700 }}>
                  Reconciliation Workspace
                </div>
                <div style={{ fontSize: "0.86rem", color: "var(--ink-muted)", marginTop: 2 }}>
                  <strong>{transactions.length}</strong> extracted · <span style={{ color: "var(--success, #10b981)" }}>{matchedCount} matched</span> · <span style={{ color: reviewCount > 0 ? "var(--warning, #f59e0b)" : "inherit" }}>{reviewCount} review</span> · <span>{unmatchedCount} unmatched</span>
                </div>
              </div>

              {/* Filter Tabs */}
              <div style={{ display: "inline-flex", background: "var(--surface)", border: "1px solid var(--line)", borderRadius: "var(--radius-sm)", padding: 2 }}>
                <button
                  type="button"
                  onClick={() => setReconFilter("ALL")}
                  style={{
                    border: "none",
                    background: reconFilter === "ALL" ? "var(--line)" : "transparent",
                    color: reconFilter === "ALL" ? "var(--ink)" : "var(--ink-muted)",
                    padding: "4px 12px",
                    borderRadius: "var(--radius-sm)",
                    fontSize: "0.78rem",
                    fontWeight: 600,
                    cursor: "pointer",
                  }}
                >
                  All ({transactions.length})
                </button>
                <button
                  type="button"
                  onClick={() => setReconFilter("MATCHED")}
                  style={{
                    border: "none",
                    background: reconFilter === "MATCHED" ? "var(--line)" : "transparent",
                    color: reconFilter === "MATCHED" ? "var(--success, #10b981)" : "var(--ink-muted)",
                    padding: "4px 12px",
                    borderRadius: "var(--radius-sm)",
                    fontSize: "0.78rem",
                    fontWeight: 600,
                    cursor: "pointer",
                  }}
                >
                  Matched ({matchedCount})
                </button>
                <button
                  type="button"
                  onClick={() => setReconFilter("REVIEW")}
                  style={{
                    border: "none",
                    background: reconFilter === "REVIEW" ? "var(--line)" : "transparent",
                    color: reconFilter === "REVIEW" ? "var(--warning, #f59e0b)" : "var(--ink-muted)",
                    padding: "4px 12px",
                    borderRadius: "var(--radius-sm)",
                    fontSize: "0.78rem",
                    fontWeight: 600,
                    cursor: "pointer",
                  }}
                >
                  Review ({reviewCount})
                </button>
                <button
                  type="button"
                  onClick={() => setReconFilter("UNMATCHED")}
                  style={{
                    border: "none",
                    background: reconFilter === "UNMATCHED" ? "var(--line)" : "transparent",
                    color: reconFilter === "UNMATCHED" ? "var(--ink)" : "var(--ink-muted)",
                    padding: "4px 12px",
                    borderRadius: "var(--radius-sm)",
                    fontSize: "0.78rem",
                    fontWeight: 600,
                    cursor: "pointer",
                  }}
                >
                  Unmatched ({unmatchedCount})
                </button>
              </div>
            </div>

            {/* Detected EMI Groups Card */}
            {emiBundles.length > 0 && (
              <div style={{ background: "rgba(139, 92, 246, 0.05)", border: "1px solid rgba(139, 92, 246, 0.2)", borderRadius: "var(--radius-sm)", padding: "10px 14px", display: "flex", flexDirection: "column", gap: 8 }}>
                <div style={{ fontSize: "0.72rem", textTransform: "uppercase", letterSpacing: "0.05em", color: "#8b5cf6", fontWeight: 700, display: "flex", alignItems: "center", gap: 6 }}>
                  <span>💳 Detected Credit Card EMI Plans ({emiBundles.length})</span>
                </div>
                {emiBundles.map((b, idx) => (
                  <div key={idx} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8, background: "rgba(0,0,0,0.12)", padding: "8px 12px", borderRadius: "var(--radius-sm)", border: "1px solid var(--line)" }}>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: "0.85rem", display: "flex", alignItems: "center", gap: 6 }}>
                        <span>{b.merchant} EMI · Installment {b.installment} of {b.tenure}</span>
                        <span className="badge" style={{ fontSize: "0.65rem", padding: "1px 5px", background: b.allMatched ? "rgba(16, 185, 129, 0.15)" : "rgba(245, 158, 11, 0.15)", color: b.allMatched ? "var(--success, #10b981)" : "var(--warning, #f59e0b)" }}>
                          {b.allMatched ? "✓ Matched in Ledger" : "○ Unmatched"}
                        </span>
                      </div>
                      <div style={{ fontSize: "0.75rem", color: "var(--ink-muted)", marginTop: 2 }}>
                        {formatDate(b.date)} · Total Installment: <strong style={{ color: "var(--ink)" }}>₹{b.totalAmount.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</strong> ({b.txs.length} items: Principal + Interest + GST)
                      </div>
                    </div>

                    {!b.allMatched && (
                      <button
                        type="button"
                        className="btn quiet"
                        disabled={importingBundle}
                        onClick={() => handleImportEmiBundle(b.txs.map((t) => t.id))}
                        style={{ fontSize: "0.76rem", padding: "4px 10px", color: "var(--accent, #6366f1)", fontWeight: 600 }}
                        title="Import all 3 line items (Principal, Interest, and GST) into ledger"
                      >
                        {importingBundle ? "Importing..." : "+ Import EMI to Ledger"}
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Sticky Table Workspace */}
            <div
              style={{
                maxHeight: "440px",
                overflowY: "auto",
                border: "1px solid var(--line)",
                borderRadius: "var(--radius-sm)",
                position: "relative",
              }}
            >
              <table className="table" style={{ width: "100%", fontSize: "0.83rem", margin: 0 }}>
                <thead style={{ position: "sticky", top: 0, background: "var(--surface)", zIndex: 2, borderBottom: "1px solid var(--line)" }}>
                  <tr>
                    <th style={{ padding: "9px 12px", width: 100 }}>Date</th>
                    <th style={{ padding: "9px 12px" }}>Description</th>
                    <th style={{ padding: "9px 12px", textAlign: "right", width: 120 }}>Amount</th>
                    <th style={{ padding: "9px 12px", textAlign: "right", width: 110 }}>Balance</th>
                    <th style={{ padding: "9px 12px", width: 110 }}>Account</th>
                    <th style={{ padding: "9px 12px", width: 140 }}>Match Status</th>
                    <th style={{ padding: "9px 12px", width: 140, textAlign: "right" }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredTransactions.map((tx) => {
                    const rrn = extractUpiRrn(tx.description);
                    const isUnmatched = (!tx.match_status || tx.match_status === "UNMATCHED");

                    return (
                      <tr
                        key={tx.id}
                        onClick={() => {
                          if (tx.match_status === "POSSIBLE_MATCH" || tx.match_status === "UNMATCHED") {
                            setSelectedReviewTx(tx);
                          }
                        }}
                        style={{
                          cursor: "pointer",
                          background: tx.match_status === "POSSIBLE_MATCH" ? "rgba(245, 158, 11, 0.04)" : "transparent",
                        }}
                      >
                        <td style={{ padding: "9px 12px", whiteSpace: "nowrap" }}>{formatDate(tx.transaction_date)}</td>
                        <td style={{ padding: "9px 12px" }}>
                          <div style={{ fontWeight: 500, wordBreak: "break-word" }}>{tx.description}</div>
                          {tx.match_reason && (
                            <div style={{ fontSize: "0.72rem", color: "var(--ink-muted)", marginTop: 2 }}>
                              {tx.match_reason}
                            </div>
                          )}
                          {rrn && isUnmatched && (
                            <div style={{ fontSize: "0.68rem", color: "var(--accent, #6366f1)", marginTop: 2, display: "inline-block", background: "rgba(99, 102, 241, 0.08)", padding: "1px 5px", borderRadius: 3 }}>
                              UPI RRN: {rrn}
                            </div>
                          )}
                        </td>
                        <td style={{ padding: "9px 12px", textAlign: "right", fontWeight: 600, color: tx.credit_amount ? "var(--success, #10b981)" : "var(--ink)", whiteSpace: "nowrap" }}>
                          {tx.credit_amount ? `+₹${tx.amount.toLocaleString("en-IN", { minimumFractionDigits: 2 })}` : `₹${tx.amount.toLocaleString("en-IN", { minimumFractionDigits: 2 })}`}
                        </td>
                        <td style={{ padding: "9px 12px", textAlign: "right", color: "var(--ink-muted)", fontSize: "0.78rem", whiteSpace: "nowrap" }}>
                          {tx.running_balance != null ? `₹${tx.running_balance.toLocaleString("en-IN", { minimumFractionDigits: 2 })}` : "—"}
                        </td>
                        <td style={{ padding: "9px 12px", whiteSpace: "nowrap" }}>
                          <span className="badge" style={{ fontSize: "0.68rem" }}>
                            {tx.attribution_status === "EXACT" ? (currentStmt.card_last4 ? `•••• ${currentStmt.card_last4}` : "Exact") : "Combined"}
                          </span>
                        </td>
                        <td style={{ padding: "9px 12px", whiteSpace: "nowrap" }}>
                          {getMatchBadge(tx.match_status)}
                        </td>
                        <td style={{ padding: "9px 12px", textAlign: "right", whiteSpace: "nowrap" }} onClick={(e) => e.stopPropagation()}>
                          {isUnmatched && (
                            <div style={{ display: "inline-flex", gap: 6, justifyContent: "flex-end" }}>
                              {rrn && (
                                <button
                                  type="button"
                                  className="btn quiet"
                                  disabled={scanningTxId === tx.id}
                                  onClick={() => handleScanGmail(tx)}
                                  style={{ fontSize: "0.72rem", padding: "2px 7px", color: "var(--accent, #6366f1)" }}
                                  title={`Scan Gmail for UPI RRN ${rrn}`}
                                >
                                  {scanningTxId === tx.id ? "Scanning..." : "🔍 Scan"}
                                </button>
                              )}
                              <button
                                type="button"
                                className="btn quiet"
                                disabled={importingTxId === tx.id}
                                onClick={() => handleImportToLedger(tx)}
                                style={{ fontSize: "0.72rem", padding: "2px 7px" }}
                                title="Create corresponding ledger entry and match"
                              >
                                {importingTxId === tx.id ? "Adding..." : "+ Add"}
                              </button>
                            </div>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                  {filteredTransactions.length === 0 && (
                    <tr>
                      <td colSpan={7} className="empty" style={{ padding: 24, textAlign: "center" }}>
                        {transactions.length === 0 ? "No transactions extracted yet. Click Re-Extract to run parser." : "No transactions match the selected filter."}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>

          {/* Level 3: Collapsible Technical Provenance & Processing Audit */}
          <div style={{ marginTop: 4 }}>
            <button
              type="button"
              className="btn quiet"
              onClick={() => setShowAuditDetails(!showAuditDetails)}
              style={{ fontSize: "0.75rem", color: "var(--ink-muted)", padding: "4px 8px" }}
            >
              {showAuditDetails ? "▾ Hide Technical Provenance & Processing Audit" : "▸ View Technical Provenance & Processing Audit"}
            </button>

            {showAuditDetails && (
              <div style={{ background: "var(--surface)", border: "1px solid var(--line)", borderRadius: "var(--radius-md)", padding: 14, marginTop: 8, fontSize: "0.78rem", display: "flex", flexDirection: "column", gap: 10 }}>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 10 }}>
                  <div>
                    <span style={{ color: "var(--ink-muted)" }}>Parser:</span>{" "}
                    <strong>{currentStmt.parser_name || "auto"} v{currentStmt.parser_version || "1.0.0"}</strong>
                  </div>
                  <div>
                    <span style={{ color: "var(--ink-muted)" }}>Discovered:</span>{" "}
                    <span>{formatDate(currentStmt.discovered_at)}</span>
                  </div>
                  <div>
                    <span style={{ color: "var(--ink-muted)" }}>Original SHA-256:</span>{" "}
                    <code style={{ fontSize: "0.72rem" }}>{currentStmt.original_sha256 ? `${currentStmt.original_sha256.slice(0, 16)}...` : "—"}</code>
                  </div>
                  <div>
                    <span style={{ color: "var(--ink-muted)" }}>Unlocked SHA-256:</span>{" "}
                    <code style={{ fontSize: "0.72rem" }}>{currentStmt.unlocked_sha256 ? `${currentStmt.unlocked_sha256.slice(0, 16)}...` : "—"}</code>
                  </div>
                </div>

                <div style={{ borderTop: "1px solid var(--line)", paddingTop: 8, display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap", color: "var(--ink-muted)", fontSize: "0.75rem" }}>
                  <span>✓ Ingested from Gmail</span>
                  <span>→</span>
                  <span>{currentStmt.has_unlocked_file ? "✓ Password Unlocked" : "🔒 Password Required"}</span>
                  <span>→</span>
                  <span>✓ Extracted ({transactions.length} rows)</span>
                  <span>→</span>
                  <span>✓ Validated ({currentStmt.validation_status || "Pending"})</span>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Modal Footer */}
        <footer
          className="modal-footer"
          style={{
            borderTop: "1px solid var(--line)",
            padding: "12px 24px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            flexShrink: 0,
          }}
        >
          <div style={{ fontSize: "0.78rem", color: "var(--ink-muted)" }}>
            {transactions.length > 0 ? `Showing ${filteredTransactions.length} of ${transactions.length} transactions` : "No transactions"}
          </div>
          <button type="button" className="btn quiet" onClick={onClose}>
            Close
          </button>
        </footer>
      </div>

      {/* Review / Import Dialog */}
      {selectedReviewTx && (() => {
        const isStmtCredit = (selectedReviewTx.credit_amount != null && selectedReviewTx.credit_amount > 0);
        const matchedTx = selectedReviewTx.matched_transaction;
        const isMatchedCredit = matchedTx ? (matchedTx.direction === "inflow" || (matchedTx as any).credit_amount > 0) : false;
        const isPossibleMatch = selectedReviewTx.match_status === "POSSIBLE_MATCH";
        const rrn = extractUpiRrn(selectedReviewTx.description);

        return (
          <div
            className="modal-backdrop"
            role="presentation"
            onClick={() => setSelectedReviewTx(null)}
            style={{ zIndex: 1100 }}
          >
            <div
              className="modal-panel"
              onClick={(e) => e.stopPropagation()}
              style={{ maxWidth: 700, width: "100%", padding: 24, display: "flex", flexDirection: "column", gap: 16 }}
            >
              {/* Header */}
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <div>
                  <div style={{ fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.05em", color: isPossibleMatch ? "var(--warning, #f59e0b)" : "var(--ink-muted)", fontWeight: 700, display: "flex", alignItems: "center", gap: 6 }}>
                    <span>{isPossibleMatch ? "⚠ Possible Match Correlation" : "○ Unmatched Statement Item"}</span>
                    {selectedReviewTx.match_confidence != null && (
                      <span className="badge" style={{ fontSize: "0.68rem", padding: "1px 6px", background: "rgba(245, 158, 11, 0.12)", color: "var(--warning, #f59e0b)" }}>
                        {Math.round(selectedReviewTx.match_confidence * 100)}% Confidence
                      </span>
                    )}
                  </div>
                  <h3 style={{ margin: "4px 0 0", fontSize: "1.05rem", fontWeight: 700, color: "var(--ink)" }}>
                    {isPossibleMatch ? "Review & Confirm Transaction Correlation" : "Statement Line Item Details"}
                  </h3>
                </div>
                <button type="button" className="btn icon-btn" onClick={() => setSelectedReviewTx(null)} aria-label="Close dialog">
                  ×
                </button>
              </div>

              {/* Match Reason Banner */}
              {selectedReviewTx.match_reason && (
                <div style={{ background: isPossibleMatch ? "rgba(245, 158, 11, 0.08)" : "rgba(255, 255, 255, 0.03)", border: `1px solid ${isPossibleMatch ? "rgba(245, 158, 11, 0.25)" : "var(--line)"}`, borderRadius: "var(--radius-sm)", padding: "8px 12px", fontSize: "0.78rem", color: "var(--ink)", display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ fontSize: "0.9rem" }}>{isPossibleMatch ? "💡" : "ℹ️"}</span>
                  <div>
                    <span style={{ fontWeight: 600, color: isPossibleMatch ? "var(--warning, #f59e0b)" : "var(--ink-muted)" }}>Matching Evidence:</span>{" "}
                    <span>{selectedReviewTx.match_reason}</span>
                  </div>
                </div>
              )}

              {/* UPI RRN Discovery Banner */}
              {rrn && !isPossibleMatch && (!selectedReviewTx.match_status || selectedReviewTx.match_status === "UNMATCHED") && (
                <div style={{ background: "rgba(99, 102, 241, 0.08)", border: "1px solid rgba(99, 102, 241, 0.25)", borderRadius: "var(--radius-sm)", padding: "10px 14px", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 10 }}>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: "0.84rem", color: "var(--accent, #6366f1)", display: "flex", alignItems: "center", gap: 6 }}>
                      <span>🔍 UPI Reference Detected: <strong>{rrn}</strong></span>
                    </div>
                    <div style={{ fontSize: "0.74rem", color: "var(--ink-muted)", marginTop: 2 }}>
                      Scan Gmail specifically for this 12-digit UPI RRN to ingest the original bank alert email.
                    </div>
                  </div>
                  <button
                    type="button"
                    className="btn primary"
                    disabled={scanningTxId === selectedReviewTx.id}
                    onClick={() => handleScanGmail(selectedReviewTx)}
                    style={{ fontSize: "0.78rem", padding: "5px 12px" }}
                  >
                    {scanningTxId === selectedReviewTx.id ? "Scanning Gmail..." : "🔍 Scan Gmail for Email"}
                  </button>
                </div>
              )}

              {/* Side-by-Side Comparison Container */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(290px, 1fr))", gap: 14 }}>
                {/* Left Card: Statement Item */}
                <div
                  style={{
                    background: "var(--surface)",
                    border: "1px solid var(--line)",
                    borderRadius: "var(--radius-md)",
                    padding: 14,
                    display: "flex",
                    flexDirection: "column",
                    gap: 10,
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                    <span style={{ fontSize: "0.7rem", textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--ink-muted)", fontWeight: 700 }}>
                      📄 Official PDF Statement
                    </span>
                    <span
                      className="badge"
                      style={{
                        fontSize: "0.68rem",
                        padding: "2px 6px",
                        fontWeight: 700,
                        background: isStmtCredit ? "rgba(16, 185, 129, 0.15)" : "rgba(239, 68, 68, 0.12)",
                        color: isStmtCredit ? "var(--success, #10b981)" : "var(--danger, #ef4444)",
                      }}
                    >
                      {isStmtCredit ? "↑ CREDIT (Inflow)" : "↓ DEBIT (Outflow)"}
                    </span>
                  </div>

                  <div>
                    <div style={{ fontSize: "1.25rem", fontWeight: 700, color: isStmtCredit ? "var(--success, #10b981)" : "var(--ink)" }}>
                      {isStmtCredit ? `+₹${selectedReviewTx.amount.toLocaleString("en-IN", { minimumFractionDigits: 2 })}` : `₹${selectedReviewTx.amount.toLocaleString("en-IN", { minimumFractionDigits: 2 })}`}
                    </div>
                    <div style={{ fontSize: "0.85rem", fontWeight: 600, marginTop: 4, wordBreak: "break-word" }}>
                      {selectedReviewTx.description}
                    </div>
                  </div>

                  <div style={{ borderTop: "1px solid var(--line)", paddingTop: 8, fontSize: "0.76rem", display: "flex", flexDirection: "column", gap: 4, color: "var(--ink-muted)" }}>
                    <div style={{ display: "flex", justifyContent: "space-between" }}>
                      <span>Date:</span>
                      <strong style={{ color: "var(--ink)" }}>{formatDate(selectedReviewTx.transaction_date)}</strong>
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between" }}>
                      <span>Account / Card:</span>
                      <strong style={{ color: "var(--ink)" }}>
                        {currentStmt.account_name || currentStmt.issuer} {currentStmt.card_last4 ? `•••• ${currentStmt.card_last4}` : ""}
                      </strong>
                    </div>
                    {selectedReviewTx.running_balance != null && (
                      <div style={{ display: "flex", justifyContent: "space-between" }}>
                        <span>Balance After Tx:</span>
                        <strong style={{ color: "var(--ink)" }}>₹{selectedReviewTx.running_balance.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</strong>
                      </div>
                    )}
                  </div>
                </div>

                {/* Right Card: Candidate Ledger Alert */}
                <div
                  style={{
                    background: matchedTx ? "var(--surface)" : "rgba(255, 255, 255, 0.02)",
                    border: `1px solid ${matchedTx ? "var(--line)" : "rgba(255, 255, 255, 0.06)"}`,
                    borderRadius: "var(--radius-md)",
                    padding: 14,
                    display: "flex",
                    flexDirection: "column",
                    gap: 10,
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                    <span style={{ fontSize: "0.7rem", textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--ink-muted)", fontWeight: 700 }}>
                      ✉️ Gmail Alert / Ledger
                    </span>
                    {matchedTx ? (
                      <span
                        className="badge"
                        style={{
                          fontSize: "0.68rem",
                          padding: "2px 6px",
                          fontWeight: 700,
                          background: isMatchedCredit ? "rgba(16, 185, 129, 0.15)" : "rgba(239, 68, 68, 0.12)",
                          color: isMatchedCredit ? "var(--success, #10b981)" : "var(--danger, #ef4444)",
                        }}
                      >
                        {isMatchedCredit ? "↑ CREDIT (Inflow)" : "↓ DEBIT (Outflow)"}
                      </span>
                    ) : (
                      <span className="badge" style={{ fontSize: "0.68rem", opacity: 0.7 }}>No Alert Found</span>
                    )}
                  </div>

                  {matchedTx ? (
                    <>
                      <div>
                        <div style={{ fontSize: "1.25rem", fontWeight: 700, color: isMatchedCredit ? "var(--success, #10b981)" : "var(--ink)" }}>
                          {isMatchedCredit ? `+₹${matchedTx.amount.toLocaleString("en-IN", { minimumFractionDigits: 2 })}` : `₹${matchedTx.amount.toLocaleString("en-IN", { minimumFractionDigits: 2 })}`}
                        </div>
                        <div style={{ fontSize: "0.85rem", fontWeight: 600, marginTop: 4, wordBreak: "break-word" }}>
                          {matchedTx.merchant_normalized || matchedTx.merchant_raw || "Transaction"}
                        </div>
                      </div>

                      <div style={{ borderTop: "1px solid var(--line)", paddingTop: 8, fontSize: "0.76rem", display: "flex", flexDirection: "column", gap: 4, color: "var(--ink-muted)" }}>
                        <div style={{ display: "flex", justifyContent: "space-between" }}>
                          <span>Alert Date:</span>
                          <strong style={{ color: "var(--ink)" }}>{formatDate(matchedTx.transaction_date)}</strong>
                        </div>
                        <div style={{ display: "flex", justifyContent: "space-between" }}>
                          <span>Category:</span>
                          <strong style={{ color: "var(--ink)" }}>{matchedTx.category || "Uncategorized"}</strong>
                        </div>
                        <div style={{ display: "flex", justifyContent: "space-between" }}>
                          <span>Source:</span>
                          <strong style={{ color: "var(--ink)" }}>{matchedTx.source || "Gmail"}</strong>
                        </div>
                      </div>
                    </>
                  ) : (
                    <div style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "center", textAlign: "center", padding: "16px 8px" }}>
                      <div style={{ fontSize: "1.2rem", marginBottom: 6 }}>📭</div>
                      <div style={{ fontSize: "0.82rem", fontWeight: 600, color: "var(--ink)" }}>No Matching Alert Found</div>
                      <div style={{ fontSize: "0.74rem", color: "var(--ink-muted)", marginTop: 4 }}>
                        This statement line item does not have a corresponding email notification in your database.
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {/* Action Buttons */}
              <div style={{ display: "flex", gap: 10, justifyContent: "flex-end", borderTop: "1px solid var(--line)", paddingTop: 14 }}>
                {isPossibleMatch ? (
                  <>
                    <button
                      type="button"
                      className="btn quiet"
                      disabled={updatingMatch}
                      onClick={() => handleRejectMatch(selectedReviewTx)}
                    >
                      {updatingMatch ? "Updating..." : "Not a Match"}
                    </button>
                    <button
                      type="button"
                      className="btn primary"
                      disabled={updatingMatch}
                      onClick={() => handleConfirmMatch(selectedReviewTx)}
                    >
                      {updatingMatch ? "Confirming..." : "✓ Confirm Match"}
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      type="button"
                      className="btn quiet"
                      onClick={() => setSelectedReviewTx(null)}
                    >
                      Dismiss
                    </button>
                    <button
                      type="button"
                      className="btn primary"
                      disabled={importingTxId === selectedReviewTx.id}
                      onClick={() => handleImportToLedger(selectedReviewTx)}
                    >
                      {importingTxId === selectedReviewTx.id ? "Adding..." : "+ Add to Ledger & Match"}
                    </button>
                  </>
                )}
              </div>
            </div>
          </div>
        );
      })()}
    </div>,
    document.body
  );
}
