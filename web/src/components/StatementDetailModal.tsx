import { useState, useId, useRef } from "react";
import { createPortal } from "react-dom";
import { api, type CreditCardStatement } from "../api";
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

function getStatusBadge(status: string) {
  switch (status) {
    case "READY_FOR_EXTRACTION":
    case "UNLOCKED":
      return <span className="badge" style={{ background: "rgba(16, 185, 129, 0.15)", color: "var(--success, #10b981)", fontWeight: 600 }}>✓ Ready for Extraction</span>;
    case "PASSWORD_REQUIRED":
      return <span className="badge" style={{ background: "rgba(245, 158, 11, 0.15)", color: "var(--warning, #f59e0b)", fontWeight: 600 }}>🔒 Password Required</span>;
    case "PASSWORD_FAILED":
      return <span className="badge" style={{ background: "rgba(239, 68, 68, 0.15)", color: "var(--danger, #ef4444)", fontWeight: 600 }}>⚠ Password Failed</span>;
    case "INVALID_PDF":
    case "DOWNLOAD_FAILED":
    case "UNLOCK_FAILED":
      return <span className="badge" style={{ background: "rgba(239, 68, 68, 0.15)", color: "var(--danger, #ef4444)", fontWeight: 600 }}>✕ {status.replace("_", " ")}</span>;
    case "UNLOCKING":
    case "DOWNLOADING":
    case "DISCOVERED":
      return <span className="badge" style={{ background: "rgba(59, 130, 246, 0.15)", color: "#3b82f6", fontWeight: 600 }}>⏳ {status}</span>;
    default:
      return <span className="badge">{status}</span>;
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

  const [password, setPassword] = useState("");
  const [saveToProfile, setSaveToProfile] = useState(true);
  const [showPassword, setShowPassword] = useState(false);
  const [unlocking, setUnlocking] = useState(false);
  const [activeStatement, setActiveStatement] = useState<CreditCardStatement | null>(statement);

  useModalChrome(open, onClose, closeRef);
  const onBackdropClick = useBackdropClose(open, onClose);

  // Sync state when incoming statement changes
  if (statement && activeStatement?.id !== statement.id) {
    setActiveStatement(statement);
    setPassword("");
  }

  if (!open || !activeStatement) return null;

  const currentStmt = activeStatement;
  const isLocked = currentStmt.status === "PASSWORD_REQUIRED" || currentStmt.status === "PASSWORD_FAILED";
  const gmailUrl = currentStmt.gmail_url || (currentStmt.source_email_id ? `https://mail.google.com/mail/u/0/#all/${currentStmt.source_email_id}` : null);

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
      showToast("Statement successfully unlocked!", "success");
      if (onStatementUpdated) onStatementUpdated(updated);
      setPassword("");
    } catch (err: any) {
      showToast(err.message || "Failed to unlock statement", "error");
    } finally {
      setUnlocking(false);
    }
  };

  return createPortal(
    <div className="modal-backdrop" role="presentation" onClick={onBackdropClick}>
      <div
        className="modal-panel"
        aria-labelledby={titleId}
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "100%",
          maxWidth: 720,
          display: "flex",
          flexDirection: "column",
          height: "min(820px, 90dvh)",
          maxHeight: "90dvh",
          boxSizing: "border-box",
        }}
      >
        <div className="sheet-handle" onClick={onClose} aria-label="Dismiss sheet" />

        <header className="modal-header" style={{ flexShrink: 0, borderBottom: "1px solid var(--line)", paddingBottom: 16 }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4, flexWrap: "wrap" }}>
              <span className="badge" style={{ textTransform: "uppercase", fontSize: "0.72rem" }}>
                {currentStmt.issuer} {currentStmt.card_last4 ? `•••• ${currentStmt.card_last4}` : ""}
              </span>
              {getStatusBadge(currentStmt.status)}
            </div>
            <h2 id={titleId} style={{ margin: 0, fontSize: "1.25rem", wordBreak: "break-word" }}>
              {currentStmt.original_filename}
            </h2>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 4 }}>
              <span style={{ fontSize: "0.85rem", color: "var(--ink-muted)" }}>
                {currentStmt.account_name || currentStmt.issuer}
              </span>
              <span
                className="badge"
                style={{
                  fontSize: "0.68rem",
                  padding: "2px 6px",
                  background: currentStmt.statement_type === "BANK_ACCOUNT" ? "rgba(59, 130, 246, 0.12)" : "rgba(139, 92, 246, 0.12)",
                  color: currentStmt.statement_type === "BANK_ACCOUNT" ? "var(--accent)" : "#8b5cf6",
                  border: "none",
                }}
              >
                {currentStmt.statement_type === "BANK_ACCOUNT" ? "Bank Statement" : "Credit Card"}
              </span>
            </div>
          </div>
          <div className="modal-actions">
            <button ref={closeRef} type="button" className="btn icon-btn" onClick={onClose} aria-label="Close modal">
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
            </button>
          </div>
        </header>

        <div className="modal-body" style={{ display: "flex", flexDirection: "column", gap: 24, flex: "1 1 0%", minHeight: 0, overflowY: "auto", padding: "20px 24px" }}>
          
          {/* Section: Overview Metadata */}
          <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 16, background: "var(--surface)", padding: 16, borderRadius: "var(--radius-md)", border: "1px solid var(--line)" }}>
            <div>
              <div style={{ fontSize: "0.75rem", color: "var(--ink-muted)", textTransform: "uppercase", fontWeight: 600 }}>
                {currentStmt.statement_type === "BANK_ACCOUNT" ? "Account Number" : "Card Number"}
              </div>
              <div style={{ fontSize: "0.92rem", fontWeight: 500, marginTop: 4 }}>
                {currentStmt.card_last4 ? `Ending in ${currentStmt.card_last4}` : "—"}
              </div>
            </div>
            <div>
              <div style={{ fontSize: "0.75rem", color: "var(--ink-muted)", textTransform: "uppercase", fontWeight: 600 }}>Statement Period</div>
              <div style={{ fontSize: "0.92rem", fontWeight: 500, marginTop: 4 }}>
                {formatPeriod(currentStmt.statement_period_start, currentStmt.statement_period_end)}
              </div>
            </div>
            <div>
              <div style={{ fontSize: "0.75rem", color: "var(--ink-muted)", textTransform: "uppercase", fontWeight: 600 }}>Statement Date</div>
              <div style={{ fontSize: "0.92rem", fontWeight: 500, marginTop: 4 }}>
                {formatDate(currentStmt.statement_date)}
              </div>
            </div>
            {currentStmt.payment_due_date && (
              <div>
                <div style={{ fontSize: "0.75rem", color: "var(--ink-muted)", textTransform: "uppercase", fontWeight: 600 }}>Payment Due Date</div>
                <div style={{ fontSize: "0.92rem", fontWeight: 600, color: "var(--warning, #f59e0b)", marginTop: 4 }}>
                  {formatDate(currentStmt.payment_due_date)}
                </div>
              </div>
            )}
            {currentStmt.total_amount_due != null && (
              <div>
                <div style={{ fontSize: "0.75rem", color: "var(--ink-muted)", textTransform: "uppercase", fontWeight: 600 }}>Total Amount Due</div>
                <div style={{ fontSize: "0.92rem", fontWeight: 600, color: "var(--danger, #ef4444)", marginTop: 4 }}>
                  ₹{currentStmt.total_amount_due.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </div>
              </div>
            )}
            <div>
              <div style={{ fontSize: "0.75rem", color: "var(--ink-muted)", textTransform: "uppercase", fontWeight: 600 }}>Received On</div>
              <div style={{ fontSize: "0.92rem", fontWeight: 500, marginTop: 4 }}>
                {formatDate(currentStmt.email_received_at || currentStmt.discovered_at)}
              </div>
            </div>
            <div>
              <div style={{ fontSize: "0.75rem", color: "var(--ink-muted)", textTransform: "uppercase", fontWeight: 600 }}>Source</div>
              <div style={{ fontSize: "0.92rem", fontWeight: 500, marginTop: 4, display: "flex", alignItems: "center", gap: 6 }}>
                {currentStmt.source_email_id ? (
                  <>
                    <GmailLogo size={14} />
                    <span>Gmail</span>
                    {gmailUrl && (
                      <a
                        href={gmailUrl}
                        target="_blank"
                        rel="noreferrer"
                        style={{ fontSize: "0.78rem", color: "var(--accent)", textDecoration: "none", marginLeft: 2 }}
                      >
                        Open ↗
                      </a>
                    )}
                  </>
                ) : (
                  "Manual Upload"
                )}
              </div>
            </div>
            <div>
              <div style={{ fontSize: "0.75rem", color: "var(--ink-muted)", textTransform: "uppercase", fontWeight: 600 }}>Password Strategy</div>
              <div style={{ fontSize: "0.92rem", fontWeight: 500, marginTop: 4 }}>
                {currentStmt.password_strategy_id || (currentStmt.is_encrypted ? "None" : "Unencrypted")}
              </div>
            </div>
          </section>

          {/* Section: Password Unlock Recovery (if needed) */}
          {isLocked && (
            <section style={{ background: "rgba(245, 158, 11, 0.08)", border: "1px solid rgba(245, 158, 11, 0.3)", borderRadius: "var(--radius-md)", padding: 16 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--warning, #f59e0b)", fontWeight: 600, fontSize: "0.95rem" }}>
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect width="18" height="11" x="3" y="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
                Password Unlock Required
              </div>
              <p style={{ fontSize: "0.85rem", color: "var(--ink-muted)", margin: "6px 0 14px" }}>
                {currentStmt.error_message || "Could not automatically unlock this statement. Please enter the PDF password below."}
              </p>
              <form onSubmit={handleManualUnlock} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
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
                      {showPassword ? (
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M9.88 9.88a3 3 0 1 0 4.24 4.24"/><path d="M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68"/><path d="M6.61 6.61A13.526 13.526 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61"/><line x1="2" x2="22" y1="2" y2="22"/></svg>
                      ) : (
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/></svg>
                      )}
                    </button>
                  </div>
                  <button type="submit" className="btn primary" disabled={unlocking || !password.trim()}>
                    {unlocking ? "Unlocking..." : "Unlock Statement"}
                  </button>
                </div>
                {currentStmt.account_id && (
                  <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: "0.82rem", color: "var(--ink-muted)", cursor: "pointer" }}>
                    <input
                      type="checkbox"
                      checked={saveToProfile}
                      onChange={(e) => setSaveToProfile(e.target.checked)}
                    />
                    Save this password strategy for future statements from this card
                  </label>
                )}
              </form>
            </section>
          )}

          {/* Section: Vault Files (Original & Unlocked) */}
          <section>
            <h3 style={{ fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--ink-muted)", margin: "0 0 12px", fontWeight: 600 }}>
              STATEMENT VAULT ARTIFACTS
            </h3>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              
              {/* Original PDF Card */}
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 16px", background: "var(--surface)", border: "1px solid var(--line)", borderRadius: "var(--radius-sm)" }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontWeight: 600, fontSize: "0.9rem" }}>Original PDF</span>
                    <span className="badge" style={{ fontSize: "0.7rem" }}>Immutable Source</span>
                  </div>
                  <div style={{ fontSize: "0.76rem", color: "var(--ink-muted)", fontFamily: "monospace", marginTop: 4, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    SHA-256: {currentStmt.original_sha256 || "Computing..."}
                  </div>
                </div>
                <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
                  <a
                    href={api.statementOriginalUrl(currentStmt.id, false)}
                    target="_blank"
                    rel="noreferrer"
                    className="btn quiet"
                    style={{ fontSize: "0.82rem", padding: "6px 12px" }}
                  >
                    View
                  </a>
                  <a
                    href={api.statementOriginalUrl(currentStmt.id, true)}
                    className="btn quiet"
                    style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: "0.82rem", padding: "6px 12px" }}
                    title="Download Original PDF"
                  >
                    <DownloadIcon size={14} />
                    <span>Download</span>
                  </a>
                </div>
              </div>

              {/* Unlocked PDF Card */}
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 16px", background: "var(--surface)", border: "1px solid var(--line)", borderRadius: "var(--radius-sm)" }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontWeight: 600, fontSize: "0.9rem" }}>Unlocked PDF</span>
                    <span className="badge" style={{ fontSize: "0.7rem", color: currentStmt.has_unlocked_file ? "var(--success, #10b981)" : "var(--ink-muted)" }}>
                      {currentStmt.has_unlocked_file ? "Derived Artifact" : "Not yet unlocked"}
                    </span>
                  </div>
                  <div style={{ fontSize: "0.76rem", color: "var(--ink-muted)", fontFamily: "monospace", marginTop: 4, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    SHA-256: {currentStmt.unlocked_sha256 || "—"}
                  </div>
                </div>
                <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
                  {currentStmt.has_unlocked_file ? (
                    <>
                      <a
                        href={api.statementUnlockedUrl(currentStmt.id, false)}
                        target="_blank"
                        rel="noreferrer"
                        className="btn quiet"
                        style={{ fontSize: "0.82rem", padding: "6px 12px" }}
                      >
                        View
                      </a>
                      <a
                        href={api.statementUnlockedUrl(currentStmt.id, true)}
                        className="btn quiet"
                        style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: "0.82rem", padding: "6px 12px" }}
                        title="Download Unlocked PDF"
                      >
                        <DownloadIcon size={14} />
                        <span>Download</span>
                      </a>
                    </>
                  ) : (
                    <button type="button" className="btn quiet" disabled style={{ fontSize: "0.82rem", opacity: 0.5 }}>
                      Unavailable
                    </button>
                  )}
                </div>
              </div>
            </div>
          </section>

          {/* Section: Structured Processing Events */}
          <section>
            <h3 style={{ fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--ink-muted)", margin: "0 0 12px", fontWeight: 600 }}>
              PROCESSING TIMELINE
            </h3>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {currentStmt.events && currentStmt.events.length > 0 ? (
                currentStmt.events.map((evt) => (
                  <div
                    key={evt.id}
                    style={{
                      display: "flex",
                      alignItems: "flex-start",
                      gap: 12,
                      padding: "10px 14px",
                      background: "var(--surface)",
                      border: "1px solid var(--line)",
                      borderRadius: "var(--radius-sm)",
                    }}
                  >
                    <div style={{ marginTop: 2, flexShrink: 0 }}>
                      {evt.status === "SUCCESS" ? (
                        <span style={{ color: "var(--success, #10b981)", fontWeight: 700 }}>✓</span>
                      ) : evt.status === "FAILED" ? (
                        <span style={{ color: "var(--danger, #ef4444)", fontWeight: 700 }}>✕</span>
                      ) : evt.status === "SKIPPED" ? (
                        <span style={{ color: "var(--ink-muted)", fontWeight: 700 }}>○</span>
                      ) : (
                        <span style={{ color: "#3b82f6", fontWeight: 700 }}>●</span>
                      )}
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                        <strong style={{ fontSize: "0.85rem", textTransform: "uppercase" }}>{evt.stage}</strong>
                        <span style={{ fontSize: "0.75rem", color: "var(--ink-muted)" }}>
                          {formatDate(evt.started_at)}
                        </span>
                      </div>
                      {evt.message && (
                        <p style={{ fontSize: "0.82rem", color: "var(--ink-muted)", margin: "4px 0 0" }}>
                          {evt.message}
                        </p>
                      )}
                    </div>
                  </div>
                ))
              ) : (
                <div className="empty" style={{ padding: 12, fontSize: "0.85rem" }}>
                  No processing events recorded.
                </div>
              )}
            </div>
          </section>

          {/* Section: Next Step (Phase 2 Entry Point) */}
          <section style={{ padding: 16, background: "var(--surface)", border: "1px dashed var(--line)", borderRadius: "var(--radius-md)" }}>
            <div style={{ fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--ink-muted)", fontWeight: 600 }}>
              NEXT STEP — PHASE 2
            </div>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 8 }}>
              <div>
                <div style={{ fontWeight: 600, fontSize: "0.92rem" }}>Transaction Extraction</div>
                <div style={{ fontSize: "0.8rem", color: "var(--ink-muted)", marginTop: 2 }}>
                  {currentStmt.status === "READY_FOR_EXTRACTION"
                    ? "Ready for parser pipeline (Not processed yet in Phase 1)"
                    : "Awaiting statement unlock before extraction"}
                </div>
              </div>
              <span className="badge" style={{ opacity: 0.8 }}>
                Phase 2 Hand-off
              </span>
            </div>
          </section>

        </div>

        <footer className="modal-footer" style={{ flexShrink: 0, padding: "12px 24px", borderTop: "1px solid var(--line)", display: "flex", justifyContent: "flex-end" }}>
          <button type="button" className="btn primary" onClick={onClose}>
            Close
          </button>
        </footer>
      </div>
    </div>,
    document.body
  );
}
