import { useState, useId, useRef } from "react";
import { createPortal } from "react-dom";
import { api, type CreditCardStatement, type StatementTransaction } from "../api";
import { useToast } from "../hooks/useToast";
import { useBackdropClose, useModalChrome } from "../hooks/useModalChrome";
import { GmailLogo } from "./GmailLogo";
import { DownloadIcon } from "./DownloadIcon";
import { openInGmail } from "../utils/gmail";

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

function formatDateCompact(dateStr: string | null | undefined): string {
  if (!dateStr) return "—";
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short" });
  } catch {
    return dateStr;
  }
}

function getStatementSubtitle(stmt: CreditCardStatement): string {
  let monthYear = "";
  if (stmt.statement_period_end || stmt.statement_date) {
    try {
      const d = new Date(stmt.statement_period_end || stmt.statement_date || "");
      monthYear = d.toLocaleDateString("en-IN", { month: "short", year: "numeric" });
    } catch {
      monthYear = "";
    }
  }
  const period = formatPeriod(stmt.statement_period_start, stmt.statement_period_end);
  return monthYear ? `${monthYear} Statement · ${period}` : `Statement · ${period}`;
}

function getStatusBadge(status: string, validationStatus?: string | null) {
  if (status === "VALIDATED" || validationStatus === "VALIDATED") {
    return <span className="badge" style={{ background: "rgba(16, 185, 129, 0.15)", color: "var(--success, #10b981)", fontWeight: 600, fontSize: "0.74rem" }}>✓ Validated</span>;
  }
  if (status === "REVIEW_REQUIRED" || validationStatus === "REVIEW_REQUIRED") {
    return <span className="badge" style={{ background: "rgba(245, 158, 11, 0.15)", color: "var(--warning, #f59e0b)", fontWeight: 600, fontSize: "0.74rem" }}>⚠ Review Required</span>;
  }
  switch (status) {
    case "READY_FOR_EXTRACTION":
    case "UNLOCKED":
      return <span className="badge" style={{ background: "rgba(59, 130, 246, 0.15)", color: "var(--accent, #3b82f6)", fontWeight: 600, fontSize: "0.74rem" }}>⚡ Ready to Extract</span>;
    case "PASSWORD_REQUIRED":
      return <span className="badge" style={{ background: "rgba(245, 158, 11, 0.15)", color: "var(--warning, #f59e0b)", fontWeight: 600, fontSize: "0.74rem" }}>🔒 Needs Unlocking</span>;
    case "PASSWORD_FAILED":
      return <span className="badge" style={{ background: "rgba(239, 68, 68, 0.15)", color: "var(--danger, #ef4444)", fontWeight: 600, fontSize: "0.74rem" }}>⚠ Password Failed</span>;
    case "EXTRACTION_FAILED":
    case "VALIDATION_FAILED":
    case "INVALID_PDF":
    case "DOWNLOAD_FAILED":
      return <span className="badge" style={{ background: "rgba(239, 68, 68, 0.15)", color: "var(--danger, #ef4444)", fontWeight: 600, fontSize: "0.74rem" }}>✕ Failed</span>;
    default:
      return <span className="badge" style={{ fontSize: "0.74rem" }}>{status}</span>;
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
  const [showValDetails, setShowValDetails] = useState(false);

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
          maxWidth: "min(1080px, 94vw)",
          display: "flex",
          flexDirection: "column",
          height: "min(880px, 92dvh)",
          maxHeight: "92dvh",
          boxSizing: "border-box",
          borderRadius: "var(--radius-lg, 12px)",
        }}
      >
        <div className="sheet-handle" onClick={onClose} aria-label="Dismiss sheet" />

        {/* 1. Header: Account name + Last4, Subtitle, Validation Badge, and Action Buttons */}
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
            <h2
              id={titleId}
              style={{
                margin: 0,
                fontSize: "1.1rem",
                fontWeight: 650,
                color: "var(--ink)",
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
              }}
            >
              {currentStmt.account_name || currentStmt.issuer}{currentStmt.card_last4 ? ` ••••${currentStmt.card_last4}` : ""}
            </h2>
            <div style={{ fontSize: "0.82rem", color: "var(--ink-muted)", marginTop: 3 }}>
              {getStatementSubtitle(currentStmt)}
            </div>
          </div>

          <div className="modal-actions" style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
            {getStatusBadge(currentStmt.status, currentStmt.validation_status)}
            {currentStmt.has_unlocked_file && (
              <>
                <button
                  type="button"
                  className="btn quiet"
                  disabled={reExtracting}
                  onClick={handleReExtract}
                  style={{ fontSize: "0.78rem", padding: "5px 10px", display: "inline-flex", alignItems: "center", gap: 4 }}
                  title="Re-run deterministic parser & arithmetic validator"
                >
                  {reExtracting ? "Extracting..." : "↻"}
                </button>
                <button
                  type="button"
                  className="btn primary"
                  disabled={reconciling}
                  onClick={handleReconcile}
                  style={{ fontSize: "0.78rem", padding: "5px 12px", display: "inline-flex", alignItems: "center", gap: 4 }}
                  title="Reconcile extracted transactions against notification alerts"
                >
                  {reconciling ? "Reconciling..." : "✓ Reconcile"}
                </button>
              </>
            )}
            <button ref={closeRef} type="button" className="btn icon-btn" onClick={onClose} aria-label="Close modal">
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
            </button>
          </div>
        </header>

        {/* Scrollable Body */}
        <div
          className="modal-body"
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 12,
            flex: "1 1 0%",
            minHeight: 0,
            overflowY: "auto",
            padding: "16px 24px",
          }}
        >
          {/* 2. Metadata Strip: Period, Statement Date, Amount Due, Gmail Source */}
          <section
            style={{
              display: "flex",
              alignItems: "center",
              flexWrap: "wrap",
              gap: "8px 24px",
              padding: "10px 14px",
              borderRadius: "var(--radius-sm)",
              background: "var(--surface)",
              border: "1px solid var(--line)",
              fontSize: "0.82rem",
            }}
          >
            <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
              <span>📅</span>
              <strong>{formatPeriod(currentStmt.statement_period_start, currentStmt.statement_period_end)}</strong>
            </span>
            {currentStmt.statement_date && (
              <span style={{ display: "inline-flex", alignItems: "center", gap: 6, color: "var(--ink-muted)" }}>
                <span>🧾</span>
                <span style={{ color: "var(--ink)" }}>{formatDateCompact(currentStmt.statement_date)}</span>
              </span>
            )}
            {currentStmt.total_amount_due != null && (
              <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                <strong style={{ color: "var(--ink)" }}>₹{currentStmt.total_amount_due.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</strong>
                <span style={{ color: "var(--ink-muted)", fontSize: "0.78rem" }}>{isBank ? "closing balance" : "due"}</span>
              </span>
            )}
            {currentStmt.source_email_id ? (
              <button
                type="button"
                onClick={() => openInGmail(currentStmt.source_email_id!)}
                style={{
                  background: "none",
                  border: "none",
                  padding: 0,
                  cursor: "pointer",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                  color: "var(--accent, #6366f1)",
                  fontSize: "0.82rem",
                  fontWeight: 500,
                  marginLeft: "auto",
                }}
                title="Open source notification email in Gmail"
              >
                <GmailLogo size={14} />
                <span>Gmail</span>
              </button>
            ) : (
              <span style={{ color: "var(--ink-muted)", marginLeft: "auto", fontSize: "0.78rem" }}>Manual Upload</span>
            )}
          </section>

          {/* 3. Documents & Compact Validation Strip */}
          <section
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 8,
              padding: "10px 14px",
              borderRadius: "var(--radius-sm)",
              background: "var(--surface)",
              border: "1px solid var(--line)",
              fontSize: "0.82rem",
            }}
          >
            {/* Documents Row */}
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--ink-muted)" }}>
                <span>📎</span>
                <strong style={{ color: "var(--ink)" }}>Documents</strong>
                <span>· {currentStmt.has_unlocked_file ? "2 files" : "1 file"}</span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <a
                  href={api.statementOriginalUrl(currentStmt.id, false)}
                  target="_blank"
                  rel="noreferrer"
                  className="btn quiet"
                  style={{ fontSize: "0.76rem", padding: "3px 10px", display: "inline-flex", alignItems: "center", gap: 5 }}
                  title="Download original statement PDF"
                >
                  <DownloadIcon size={12} />
                  PDF
                </a>
                {currentStmt.has_unlocked_file && (
                  <a
                    href={api.statementUnlockedUrl(currentStmt.id, false)}
                    target="_blank"
                    rel="noreferrer"
                    className="btn quiet"
                    style={{ fontSize: "0.76rem", padding: "3px 10px", display: "inline-flex", alignItems: "center", gap: 5 }}
                    title="Download parsed/decrypted copy"
                  >
                    <DownloadIcon size={12} />
                    Parsed copy
                  </a>
                )}
              </div>
            </div>

            {/* Validation Row */}
            {valDetails && (
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8, borderTop: "1px solid var(--line)", paddingTop: 8 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <span style={{ color: primaryEquation?.is_balanced ? "var(--success, #10b981)" : "var(--warning, #f59e0b)", fontWeight: 600, display: "inline-flex", alignItems: "center", gap: 5 }}>
                    {primaryEquation?.is_balanced ? "✓ Exact match" : `⚠ Difference ₹${primaryEquation ? primaryEquation.difference.toFixed(2) : ""}`}
                  </span>
                  {primaryEquation && (
                    <span style={{ color: "var(--ink-muted)", fontSize: "0.78rem" }}>
                      ₹{primaryEquation.calculated.toLocaleString("en-IN", { minimumFractionDigits: 2 })} = ₹{primaryEquation.expected.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                    </span>
                  )}
                </div>
                <button
                  type="button"
                  className="btn quiet"
                  onClick={() => setShowValDetails(!showValDetails)}
                  style={{ fontSize: "0.74rem", padding: "2px 6px", color: "var(--ink-muted)" }}
                >
                  {showValDetails ? "Hide details ▴" : "Details ›"}
                </button>
              </div>
            )}

            {/* Expandable Validation Calculation Details */}
            {valDetails && showValDetails && (
              <div style={{ background: "rgba(0, 0, 0, 0.15)", borderRadius: "var(--radius-sm)", padding: "8px 12px", display: "flex", flexDirection: "column", gap: 6, fontSize: "0.76rem", marginTop: 4 }}>
                {primaryEquation && (
                  <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", color: "var(--ink-muted)" }}>
                      <span>{primaryEquation.name}</span>
                      <code>{primaryEquation.formula}</code>
                    </div>
                  </div>
                )}
                {valDetails.messages && valDetails.messages.length > 0 && (
                  <div style={{ display: "flex", flexDirection: "column", gap: 2, borderTop: "1px solid var(--line)", paddingTop: 6 }}>
                    {valDetails.messages.map((msg, i) => (
                      <div key={i} style={{ color: "var(--success, #10b981)", display: "flex", alignItems: "center", gap: 6 }}>
                        <span>✓</span>
                        <span>{msg.replace("✓ ", "")}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </section>

          {/* Password Unlock Form (when locked) */}
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

          {/* 4. TRANSACTIONS SECTION */}
          <section style={{ display: "flex", flexDirection: "column", gap: 10, flex: "1 1 0%", minHeight: 0 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
              <span style={{ fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--ink-muted)", fontWeight: 700 }}>
                TRANSACTIONS
              </span>
              <span style={{ fontSize: "0.82rem", fontWeight: 700, color: matchedCount === transactions.length && transactions.length > 0 ? "var(--success, #10b981)" : "var(--ink)" }}>
                {transactions.length > 0 ? `${matchedCount} / ${transactions.length} ✓ MATCHED` : "0 Transactions"}
              </span>
            </div>

            {/* Filter Pills */}
            <div style={{ display: "flex", justifyContent: "center", gap: 6, flexWrap: "wrap" }}>
              <button
                type="button"
                className={`pill-btn ${reconFilter === "ALL" ? "active" : ""}`}
                onClick={() => setReconFilter("ALL")}
                style={{
                  border: reconFilter === "ALL" ? "1px solid var(--line-active, #4b5563)" : "1px solid var(--line)",
                  background: reconFilter === "ALL" ? "var(--line)" : "transparent",
                  color: reconFilter === "ALL" ? "var(--ink)" : "var(--ink-muted)",
                  padding: "3px 12px",
                  borderRadius: "var(--radius-full, 9999px)",
                  fontSize: "0.76rem",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                All {transactions.length}
              </button>
              <button
                type="button"
                className={`pill-btn ${reconFilter === "MATCHED" ? "active" : ""}`}
                onClick={() => setReconFilter("MATCHED")}
                style={{
                  border: reconFilter === "MATCHED" ? "1px solid rgba(16, 185, 129, 0.4)" : "1px solid var(--line)",
                  background: reconFilter === "MATCHED" ? "rgba(16, 185, 129, 0.12)" : "transparent",
                  color: reconFilter === "MATCHED" ? "var(--success, #10b981)" : "var(--ink-muted)",
                  padding: "3px 12px",
                  borderRadius: "var(--radius-full, 9999px)",
                  fontSize: "0.76rem",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                Matched {matchedCount}
              </button>
              <button
                type="button"
                className={`pill-btn ${reconFilter === "REVIEW" ? "active" : ""}`}
                onClick={() => setReconFilter("REVIEW")}
                style={{
                  border: reconFilter === "REVIEW" ? "1px solid rgba(245, 158, 11, 0.4)" : "1px solid var(--line)",
                  background: reconFilter === "REVIEW" ? "rgba(245, 158, 11, 0.12)" : "transparent",
                  color: reconFilter === "REVIEW" ? "var(--warning, #f59e0b)" : "var(--ink-muted)",
                  padding: "3px 12px",
                  borderRadius: "var(--radius-full, 9999px)",
                  fontSize: "0.76rem",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                Review {reviewCount}
              </button>
              <button
                type="button"
                className={`pill-btn ${reconFilter === "UNMATCHED" ? "active" : ""}`}
                onClick={() => setReconFilter("UNMATCHED")}
                style={{
                  border: reconFilter === "UNMATCHED" ? "1px solid var(--line-active, #4b5563)" : "1px solid var(--line)",
                  background: reconFilter === "UNMATCHED" ? "var(--line)" : "transparent",
                  color: reconFilter === "UNMATCHED" ? "var(--ink)" : "var(--ink-muted)",
                  padding: "3px 12px",
                  borderRadius: "var(--radius-full, 9999px)",
                  fontSize: "0.76rem",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                Unmatched {unmatchedCount}
              </button>
            </div>

            {/* EMI Bundles */}
            {emiBundles.length > 0 && (
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                {emiBundles.map((b, idx) => (
                  <div
                    key={idx}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      flexWrap: "wrap",
                      gap: 8,
                      padding: "6px 12px",
                      borderRadius: "var(--radius-sm)",
                      background: b.allMatched ? "rgba(16, 185, 129, 0.05)" : "rgba(139, 92, 246, 0.06)",
                      border: `1px solid ${b.allMatched ? "rgba(16, 185, 129, 0.2)" : "rgba(139, 92, 246, 0.25)"}`,
                      fontSize: "0.8rem",
                    }}
                  >
                    <span style={{ display: "inline-flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                      <span>💳</span>
                      <span style={{ fontWeight: 600 }}>{b.merchant} · Installment {b.installment} of {b.tenure}</span>
                      <span style={{ color: "var(--ink-muted)", fontSize: "0.74rem" }}>({formatDate(b.date)})</span>
                    </span>
                    <span style={{ display: "inline-flex", alignItems: "center", gap: 10 }}>
                      <strong>₹{b.totalAmount.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</strong>
                      {b.allMatched ? (
                        <span style={{ color: "var(--success, #10b981)", fontWeight: 700, fontSize: "0.9rem" }}>✓</span>
                      ) : (
                        <button
                          type="button"
                          className="btn quiet"
                          disabled={importingBundle}
                          onClick={() => handleImportEmiBundle(b.txs.map((t) => t.id))}
                          style={{ fontSize: "0.74rem", padding: "2px 8px", color: "var(--accent, #6366f1)", fontWeight: 600 }}
                        >
                          {importingBundle ? "Importing..." : "+ Import"}
                        </button>
                      )}
                    </span>
                  </div>
                ))}
              </div>
            )}

            {/* Clean Table with Comfortable Spacing */}
            <div
              style={{
                flex: "1 1 0%",
                minHeight: 200,
                overflowY: "auto",
                border: "1px solid var(--line)",
                borderRadius: "var(--radius-md, 8px)",
                position: "relative",
              }}
            >
              <table className="table" style={{ width: "100%", fontSize: "0.86rem", margin: 0 }}>
                <thead style={{ position: "sticky", top: 0, background: "var(--surface)", zIndex: 2, borderBottom: "1px solid var(--line)" }}>
                  <tr>
                    <th style={{ padding: "11px 16px", width: 95, fontSize: "0.74rem", letterSpacing: "0.05em" }}>DATE</th>
                    <th style={{ padding: "11px 16px", fontSize: "0.74rem", letterSpacing: "0.05em" }}>DESCRIPTION</th>
                    <th style={{ padding: "11px 16px", textAlign: "right", width: 130, fontSize: "0.74rem", letterSpacing: "0.05em" }}>AMOUNT</th>
                    <th style={{ padding: "11px 16px", textAlign: "center", width: 110, fontSize: "0.74rem", letterSpacing: "0.05em" }}>STATUS</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredTransactions.map((tx) => {
                    const rrn = extractUpiRrn(tx.description);
                    const isUnmatched = (!tx.match_status || tx.match_status === "UNMATCHED");
                    const isMatched = tx.match_status === "MATCHED" || tx.match_status === "LIABILITY_PAYMENT";
                    const isReview = tx.match_status === "POSSIBLE_MATCH";

                    return (
                      <tr
                        key={tx.id}
                        onClick={() => {
                          if (isReview || isUnmatched) {
                            setSelectedReviewTx(tx);
                          }
                        }}
                        style={{
                          cursor: (isReview || isUnmatched) ? "pointer" : "default",
                          background: isReview ? "rgba(245, 158, 11, 0.06)" : "transparent",
                          borderBottom: "1px solid var(--line)",
                        }}
                        title={isReview ? `Review candidate: ${tx.match_reason || "Click to verify correlation"}` : undefined}
                      >
                        <td style={{ padding: "12px 16px", whiteSpace: "nowrap", fontSize: "0.84rem", color: "var(--ink-muted)" }}>
                          {formatDateCompact(tx.transaction_date)}
                        </td>
                        <td style={{ padding: "12px 16px" }}>
                          <div style={{ fontWeight: 500, fontSize: "0.88rem", lineHeight: 1.35, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: 540 }} title={tx.description}>
                            {tx.description}
                          </div>
                          {rrn && isUnmatched && (
                            <div style={{ fontSize: "0.7rem", color: "var(--accent, #6366f1)", marginTop: 3, display: "inline-block", background: "rgba(99, 102, 241, 0.08)", padding: "2px 6px", borderRadius: 4 }}>
                              UPI RRN: {rrn}
                            </div>
                          )}
                        </td>
                        <td style={{ padding: "12px 16px", textAlign: "right", fontWeight: 600, fontSize: "0.92rem", color: tx.credit_amount ? "var(--success, #10b981)" : "var(--ink)", whiteSpace: "nowrap" }}>
                          {tx.credit_amount ? `+₹${Math.round(tx.amount).toLocaleString("en-IN")}` : `₹${Math.round(tx.amount).toLocaleString("en-IN")}`}
                        </td>
                        <td style={{ padding: "12px 16px", textAlign: "center", whiteSpace: "nowrap" }} onClick={(e) => isUnmatched ? e.stopPropagation() : undefined}>
                          {isMatched && (
                            <span style={{ color: "var(--success, #10b981)", fontWeight: 700, fontSize: "1.05rem" }} title="Matched in ledger">
                              ✓
                            </span>
                          )}
                          {isReview && (
                            <span
                              style={{
                                color: "var(--warning, #f59e0b)",
                                fontWeight: 600,
                                fontSize: "0.78rem",
                                display: "inline-flex",
                                alignItems: "center",
                                gap: 3,
                                background: "rgba(245, 158, 11, 0.14)",
                                padding: "3px 9px",
                                borderRadius: "var(--radius-full, 9999px)",
                              }}
                              title={tx.match_reason ? `Click to review (${tx.match_reason})` : "Click to review correlation"}
                            >
                              ⚠ Review
                            </span>
                          )}
                          {isUnmatched && (
                            <button
                              type="button"
                              className="btn quiet"
                              disabled={importingTxId === tx.id}
                              onClick={() => handleImportToLedger(tx)}
                              style={{ fontSize: "0.76rem", padding: "3px 10px" }}
                              title="Create corresponding ledger entry and match"
                            >
                              {importingTxId === tx.id ? "Adding..." : "+ Add"}
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                  {filteredTransactions.length === 0 && (
                    <tr>
                      <td colSpan={4} className="empty" style={{ padding: 32, textAlign: "center" }}>
                        {transactions.length === 0 ? "No transactions extracted yet. Click Re-Extract to run parser." : "No transactions match the selected filter."}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </div>

        {/* 5. Footer */}
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
            Showing {filteredTransactions.length} transactions
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
