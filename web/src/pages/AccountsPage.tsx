import { useEffect, useState, useId, useRef } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";
import { api, type Account, type CreditCardStatement } from "../api";
import { useToast } from "../hooks/useToast";
import { formatMoney } from "../format";
import { useBackdropClose, useModalChrome } from "../hooks/useModalChrome";
import { StatementDetailModal } from "../components/StatementDetailModal";
import { PasswordProfileModal } from "../components/PasswordProfileModal";
import { UploadStatementModal } from "../components/UploadStatementModal";
import Badge from "../components/common/Badge";
import PageHeader from "../components/common/PageHeader";
import AccountBadge from "../components/common/AccountBadge";
import { IconCheck, IconAlertTriangle, IconLock } from "../components/common/Icons";


function AccountModal({
  open,
  account,
  onClose,
  onSave,
  showToast,
  validHandles,
}: {
  open: boolean;
  account: Partial<Account> | null;
  onClose: () => void;
  onSave: (data: Partial<Account>) => Promise<void>;
  showToast: (msg: string, type: "success" | "error") => void;
  validHandles: string[];
}) {
  const titleId = useId();
  const closeRef = useRef<HTMLButtonElement>(null);
  const [formData, setFormData] = useState<Partial<Account>>({});
  const [saving, setSaving] = useState(false);

  useModalChrome(open, onClose, closeRef);
  const onBackdropClick = useBackdropClose(open, onClose);

  useEffect(() => {
    if (open && account) {
      setFormData(account);
    } else {
      setFormData({
        name: "",
        account_type: "BANK",
        is_asset: true,
        is_liability: false,
        currency: "INR",
        account_number_masked: "",
        card_last4: "",
        upi_identifier_masked: "",
        credit_limit: 0,
        opening_balance: 0,
      });
    }
  }, [open, account]);

  if (!open) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    // Validate UPI IDs or Phones
    if (formData.upi_identifier_masked && formData.account_type !== "CREDIT_CARD") {
      const identifiers = formData.upi_identifier_masked.split(",").map(s => s.trim()).filter(Boolean);
      const phoneRegex = /^[0-9]{10}$/; // Basic 10-digit phone
      
      for (const id of identifiers) {
        if (phoneRegex.test(id)) continue;

        const parts = id.split("@");
        if (parts.length !== 2) {
          showToast(`Invalid format: '${id}'. Must be a valid UPI ID (e.g. user@bank) or a 10-digit phone number.`, "error");
          return;
        }

        const [username, handle] = parts;
        if (!/^[a-zA-Z0-9._-]{2,256}$/.test(username)) {
          showToast(`Invalid UPI username in '${id}'.`, "error");
          return;
        }
        
        if (validHandles.length > 0 && !validHandles.includes(handle.toLowerCase())) {
          showToast(`Unsupported UPI handle: '@${handle}'. Accepted handles: ${validHandles.join(", ")}`, "error");
          return;
        }
      }
    }

    setSaving(true);
    try {
      await onSave(formData);
    } finally {
      setSaving(false);
    }
  };

  return createPortal(
    <div className="modal-backdrop" role="presentation" onClick={onBackdropClick}>
      <form
        className="modal-panel"
        aria-labelledby={titleId}
        onClick={(e) => e.stopPropagation()}
        onSubmit={handleSubmit}
        style={{ width: "100%", maxWidth: 650, display: "flex", flexDirection: "column", height: "min(760px, 86dvh)", maxHeight: "86dvh", boxSizing: "border-box" }}
      >
        <div className="sheet-handle" onClick={onClose} aria-label="Dismiss sheet" />

        <header className="modal-header" style={{ flexShrink: 0 }}>
          <div>
            <h2 id={titleId}>{account?.id ? "Edit Account" : "Add Account"}</h2>
            <p className="lead">Add a bank, card, wallet, or other financial account.</p>
          </div>
          <div className="modal-actions">
            <button ref={closeRef} type="button" className="btn icon-btn" onClick={onClose} aria-label="Close modal">
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
            </button>
          </div>
        </header>

        <div className="modal-body" style={{ display: "flex", flexDirection: "column", gap: 20, flex: "1 1 0%", minHeight: 0, overflowY: "auto", width: "100%", boxSizing: "border-box" }}>
          
          {/* Section: Basic Info */}
          <section style={{ display: "flex", flexDirection: "column", gap: 16, width: "100%", minWidth: 0 }}>
            <h3 style={{ fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--ink-muted)", margin: 0, fontWeight: 600 }}>BASIC INFORMATION</h3>
            <div style={{ display: "flex", flexDirection: "column", gap: 16, width: "100%", minWidth: 0 }}>
              <div className="field" style={{ width: "100%", minWidth: 0 }}>
                <label className="label">Account Name <span style={{color: "var(--accent)"}}>*</span></label>
                <input
                  type="text"
                  className="input"
                  value={formData.name || ""}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  required
                  placeholder="e.g. HDFC Checking"
                  style={{ width: "100%", minWidth: 0, boxSizing: "border-box" }}
                />
              </div>

              <div className="field" style={{ width: "100%", minWidth: 0 }}>
                <label className="label">Account Type</label>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8, width: "100%", minWidth: 0 }}>
                  {[
                    { id: "BANK", label: "Bank" },
                    { id: "CREDIT_CARD", label: "Credit Card" },
                    { id: "WALLET", label: "Wallet" },
                    { id: "INVESTMENT", label: "Investment" },
                    { id: "LOAN", label: "Loan" },
                    { id: "CASH", label: "Cash" },
                  ].map(type => (
                    <button
                      key={type.id}
                      type="button"
                      onClick={() => {
                        const isLiab = type.id === "CREDIT_CARD" || type.id.includes("LOAN");
                        setFormData({
                          ...formData,
                          account_type: type.id,
                          is_asset: !isLiab,
                          is_liability: isLiab,
                        });
                      }}
                      style={{
                        padding: "6px 12px",
                        borderRadius: "var(--radius-sm)",
                        border: `1px solid ${formData.account_type === type.id ? "var(--accent)" : "var(--line)"}`,
                        background: formData.account_type === type.id ? "var(--accent-soft)" : "transparent",
                        color: formData.account_type === type.id ? "var(--accent)" : "var(--ink)",
                        fontWeight: formData.account_type === type.id ? 500 : 400,
                        cursor: "pointer",
                        fontSize: "0.85rem",
                        outline: "none"
                      }}
                    >
                      {type.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </section>

          {/* Section: Identifiers */}
          <section style={{ display: "flex", flexDirection: "column", gap: 16, width: "100%", minWidth: 0 }}>
            <h3 style={{ fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--ink-muted)", margin: 0, fontWeight: 600 }}>IDENTIFIERS (OPTIONAL)</h3>
            <div className="account-form-grid">
              <div className="field" style={{ width: "100%", minWidth: 0 }}>
                <label className="label">Account Mask (Last 4)</label>
                <input
                  type="text"
                  className="input"
                  value={formData.account_number_masked || ""}
                  onChange={(e) => setFormData({ ...formData, account_number_masked: e.target.value })}
                  placeholder="e.g. x1234"
                  style={{ width: "100%", minWidth: 0, boxSizing: "border-box" }}
                />
              </div>
              
              {formData.account_type === "CREDIT_CARD" ? (
                <div className="field" style={{ width: "100%", minWidth: 0 }}>
                  <label className="label">Card Last 4</label>
                  <input
                    type="text"
                    className="input"
                    value={formData.card_last4 || ""}
                    onChange={(e) => setFormData({ ...formData, card_last4: e.target.value })}
                    placeholder="e.g. 5678"
                    maxLength={4}
                    style={{ width: "100%", minWidth: 0, boxSizing: "border-box" }}
                  />
                </div>
              ) : (
                <div className="field" style={{ width: "100%", minWidth: 0 }}>
                  <label className="label">UPI IDs / Phones</label>
                  <div style={{ display: "flex", flexDirection: "column", gap: 8, width: "100%", minWidth: 0 }}>
                    {(formData.upi_identifier_masked ? formData.upi_identifier_masked.split(",") : [""]).map((upi, i, arr) => (
                      <div key={i} style={{ display: "flex", gap: 8, width: "100%", minWidth: 0 }}>
                        <input
                          type="text"
                          className="input"
                          value={upi}
                          onChange={(e) => {
                            const newUpis = [...arr];
                            newUpis[i] = e.target.value;
                            setFormData({ ...formData, upi_identifier_masked: newUpis.join(",") });
                          }}
                          placeholder="e.g. user@okhdfcbank"
                          style={{ flex: 1, minWidth: 0, boxSizing: "border-box" }}
                        />
                        {arr.length > 1 && (
                          <button 
                            type="button" 
                            className="btn quiet icon-btn" 
                            title="Remove UPI ID"
                            onClick={() => {
                              const newUpis = arr.filter((_, idx) => idx !== i);
                              setFormData({ ...formData, upi_identifier_masked: newUpis.join(",") });
                            }}
                            style={{ padding: 8, flexShrink: 0 }}
                          >
                            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
                          </button>
                        )}
                      </div>
                    ))}
                    <button 
                      type="button" 
                      className="btn quiet" 
                      onClick={() => {
                        const arr = formData.upi_identifier_masked ? formData.upi_identifier_masked.split(",") : [""];
                        setFormData({ ...formData, upi_identifier_masked: [...arr, ""].join(",") });
                      }}
                      style={{ fontSize: "0.85rem", padding: "4px 8px", alignSelf: "flex-start" }}
                    >
                      + Add UPI ID
                    </button>
                  </div>
                </div>
              )}
            </div>
          </section>

          {/* Section: Balances */}
          <section style={{ display: "flex", flexDirection: "column", gap: 16, width: "100%", minWidth: 0 }}>
            <h3 style={{ fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--ink-muted)", margin: 0, fontWeight: 600 }}>BALANCES & LIMITS</h3>
            <div className="account-form-grid">
              <div className="field" style={{ width: "100%", minWidth: 0 }}>
                <label className="label">Opening Balance</label>
                <div style={{ display: "flex", gap: 8, width: "100%", minWidth: 0 }}>
                  <div style={{ padding: "0 10px", border: "1px solid var(--line)", borderRadius: "var(--radius-sm)", background: "var(--surface)", color: "var(--ink-muted)", fontSize: "0.85rem", display: "flex", alignItems: "center", flexShrink: 0 }}>
                    ₹ INR
                  </div>
                  <input
                    type="number"
                    className="input"
                    style={{ flex: 1, minWidth: 0, boxSizing: "border-box" }}
                    value={formData.opening_balance || ""}
                    onChange={(e) => setFormData({ ...formData, opening_balance: parseFloat(e.target.value) || 0 })}
                    placeholder="0.00"
                    step="0.01"
                  />
                </div>
              </div>

              {formData.account_type === "CREDIT_CARD" && (
                <div className="field" style={{ width: "100%", minWidth: 0 }}>
                  <label className="label">Credit Limit</label>
                  <div style={{ display: "flex", gap: 8, width: "100%", minWidth: 0 }}>
                    <div style={{ padding: "0 10px", border: "1px solid var(--line)", borderRadius: "var(--radius-sm)", background: "var(--surface)", color: "var(--ink-muted)", fontSize: "0.85rem", display: "flex", alignItems: "center", flexShrink: 0 }}>
                      ₹ INR
                    </div>
                    <input
                      type="number"
                      className="input"
                      style={{ flex: 1, minWidth: 0, boxSizing: "border-box" }}
                      value={formData.credit_limit || ""}
                      onChange={(e) => setFormData({ ...formData, credit_limit: parseFloat(e.target.value) || 0 })}
                      placeholder="e.g. 500000"
                      min="0"
                      step="0.01"
                    />
                  </div>
                </div>
              )}
            </div>
          </section>
        </div>

        <footer className="modal-footer" style={{ flexShrink: 0, padding: "12px 18px max(16px, env(safe-area-inset-bottom, 16px))" }}>
          <button type="button" className="btn quiet" onClick={onClose} disabled={saving}>Cancel</button>
          <button type="submit" className="btn primary" disabled={saving}>
            {saving ? "Saving..." : "Save Account"}
          </button>
        </footer>
      </form>
    </div>,
    document.body
  );
}

function formatPeriod(startStr: string | null | undefined, endStr: string | null | undefined): string {
  if (!startStr && !endStr) return "—";
  if (startStr && endStr) {
    try {
      const d1 = new Date(startStr).toLocaleDateString("en-IN", { month: "short", year: "numeric" });
      return d1;
    } catch {
      return startStr;
    }
  }
  return startStr || endStr || "—";
}

function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return "—";
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short" });
  } catch {
    return dateStr;
  }
}

function formatAccountType(type: string): string {
  switch (type) {
    case "BANK":
      return "Bank";
    case "CREDIT_CARD":
      return "Credit Card";
    case "WALLET":
      return "Wallet";
    case "CASH":
      return "Cash";
    case "INVESTMENT":
      return "Investment";
    case "LOAN":
      return "Loan";
    default:
      return type ? type.charAt(0).toUpperCase() + type.slice(1).toLowerCase() : "Account";
  }
}

function formatMaskedNumber(val: string | null | undefined): string {
  if (!val) return "—";
  return val.replace(/[*X]+/g, "••••");
}

function getStatusBadge(status: string) {
  switch (status) {
    case "READY_FOR_EXTRACTION":
    case "UNLOCKED":
      return <Badge variant="credit" icon={<IconCheck size={11} />}>Ready</Badge>;
    case "PASSWORD_REQUIRED":
      return <Badge variant="warn" icon={<IconLock size={11} />}>Locked</Badge>;
    case "PASSWORD_FAILED":
      return <Badge variant="danger" icon={<IconAlertTriangle size={11} />}>Review</Badge>;
    default:
      return <Badge variant="neutral">{status}</Badge>;
  }
}

function CreditCardAccountItem({
  account,
  onEdit,
  onDelete,
  onOpenStatementDetail,
  onOpenPasswordProfile,
  onOpenUploadStatement,
}: {
  account: Account;
  onEdit: () => void;
  onDelete: () => void;
  onOpenStatementDetail: (stmt: CreditCardStatement) => void;
  onOpenPasswordProfile: (acc: Account) => void;
  onOpenUploadStatement: (acc: Account) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [activeTab, setActiveTab] = useState<"overview" | "statements">("overview");
  const [statements, setStatements] = useState<CreditCardStatement[]>([]);
  const [loadingStatements, setLoadingStatements] = useState(false);
  const [stmtSortField, setStmtSortField] = useState<"period" | "date" | "received">("received");
  const [stmtSortDir, setStmtSortDir] = useState<"asc" | "desc">("desc");

  const handleStmtSort = (field: "period" | "date" | "received") => {
    if (stmtSortField === field) {
      setStmtSortDir(stmtSortDir === "asc" ? "desc" : "asc");
    } else {
      setStmtSortField(field);
      setStmtSortDir("desc");
    }
  };

  const sortedStatements = [...statements].sort((a, b) => {
    let cmp = 0;
    if (stmtSortField === "received") {
      const recA = a.email_received_at || a.discovered_at || a.created_at || "";
      const recB = b.email_received_at || b.discovered_at || b.created_at || "";
      cmp = recA.localeCompare(recB);
    } else if (stmtSortField === "period") {
      const dateA = a.statement_period_start || a.statement_period_end || "";
      const dateB = b.statement_period_start || b.statement_period_end || "";
      cmp = dateA.localeCompare(dateB);
    } else if (stmtSortField === "date") {
      const dateA = a.statement_date || "";
      const dateB = b.statement_date || "";
      cmp = dateA.localeCompare(dateB);
    }
    return stmtSortDir === "asc" ? cmp : -cmp;
  });

  const loadStatements = async () => {
    setLoadingStatements(true);
    try {
      const res = await api.accountStatements(account.id);
      setStatements(res.statements);
    } catch {
      // ignore
    } finally {
      setLoadingStatements(false);
    }
  };

  useEffect(() => {
    if (expanded && activeTab === "statements") {
      loadStatements();
    }
  }, [expanded, activeTab]);

  const maskedCard = account.card_last4
    ? `•••• ${account.card_last4}`
    : (account.account_number_masked ? formatMaskedNumber(account.account_number_masked) : null);

  return (
    <div
      style={{
        background: "var(--surface)",
        border: "1px solid var(--line)",
        borderRadius: "var(--radius-md)",
        marginBottom: 12,
        overflow: "hidden",
      }}
    >
      {/* Account Header Row (Fully Clickable for progressive disclosure) */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "14px 18px",
          gap: 12,
          flexWrap: "wrap",
          cursor: "pointer",
          userSelect: "none",
        }}
        onClick={() => setExpanded(!expanded)}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 200, flex: 1 }}>
          <div
            style={{
              width: 28,
              height: 28,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "var(--ink-muted)",
              flexShrink: 0,
            }}
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              style={{
                transform: expanded ? "rotate(90deg)" : "rotate(0deg)",
                transition: "transform 0.15s ease",
              }}
            >
              <polyline points="9 18 15 12 9 6" />
            </svg>
          </div>
          <AccountBadge
            accountName={account.name}
            accountType={account.account_type}
            cardLast4={account.card_last4}
            accountNumberMasked={account.account_number_masked}
            logoSize={28}
          />
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          {/* Outstanding Amount (Links to Transactions) */}
          <Link
            to={`/transactions?account=${encodeURIComponent(account.name)}`}
            onClick={(e) => e.stopPropagation()}
            style={{ textAlign: "right", textDecoration: "none", color: "inherit" }}
            title={`View transactions for ${account.name}`}
          >
            <div style={{ fontSize: "0.72rem", color: "var(--ink-muted)", textTransform: "uppercase", letterSpacing: "0.05em", fontWeight: 600 }}>
              OUTSTANDING
            </div>
            <div className="tx-amount debit" style={{ fontWeight: 700, fontSize: "1.08rem" }}>
              {formatMoney(account.balance, account.currency)}
            </div>
          </Link>

          {/* Edit / Delete actions */}
          <div style={{ display: "flex", gap: 6 }} onClick={(e) => e.stopPropagation()}>
            <button
              className="icon-action"
              type="button"
              title="Edit Account"
              aria-label={`Edit ${account.name}`}
              onClick={onEdit}
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/></svg>
            </button>
            <button
              className="icon-action danger"
              type="button"
              title="Delete Account"
              aria-label={`Delete ${account.name}`}
              onClick={onDelete}
              style={{ color: "var(--danger)" }}
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>
            </button>
          </div>
        </div>
      </div>

      {/* Tabs navigation row */}
      <div
        style={{
          display: "flex",
          borderTop: "1px solid var(--line)",
          background: "rgba(0, 0, 0, 0.02)",
          padding: "0 18px",
          gap: 8,
        }}
      >
        <button
          type="button"
          onClick={() => {
            setActiveTab("overview");
            setExpanded(true);
          }}
          style={{
            padding: "8px 14px",
            border: "none",
            borderBottom: activeTab === "overview" && expanded ? "2px solid var(--accent)" : "2px solid transparent",
            background: "none",
            fontSize: "0.82rem",
            fontWeight: activeTab === "overview" && expanded ? 600 : 400,
            color: activeTab === "overview" && expanded ? "var(--accent)" : "var(--ink-muted)",
            cursor: "pointer",
          }}
        >
          Overview
        </button>
        <button
          type="button"
          onClick={() => {
            setActiveTab("statements");
            setExpanded(true);
          }}
          style={{
            padding: "8px 14px",
            border: "none",
            borderBottom: activeTab === "statements" && expanded ? "2px solid var(--accent)" : "2px solid transparent",
            background: "none",
            fontSize: "0.82rem",
            fontWeight: activeTab === "statements" && expanded ? 600 : 400,
            color: activeTab === "statements" && expanded ? "var(--accent)" : "var(--ink-muted)",
            cursor: "pointer",
          }}
        >
          Statements {statements.length > 0 ? `(${statements.length})` : ""}
        </button>
      </div>

      {/* Expanded Tab Content */}
      {expanded && (
        <div style={{ padding: "14px 16px", borderTop: "1px solid var(--line)" }}>
          {activeTab === "overview" ? (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: 14 }}>
              <div>
                <div style={{ fontSize: "0.72rem", color: "var(--ink-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>Outstanding Balance</div>
                <div className="tx-amount debit" style={{ fontSize: "1.05rem", fontWeight: 700, marginTop: 3 }}>
                  {formatMoney(account.balance, account.currency)}
                </div>
              </div>
              <div>
                <div style={{ fontSize: "0.72rem", color: "var(--ink-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>Credit Limit</div>
                <div style={{ fontSize: "0.95rem", fontWeight: 600, marginTop: 3 }}>
                  {account.credit_limit ? formatMoney(account.credit_limit, account.currency) : "—"}
                </div>
              </div>
              <div>
                <div style={{ fontSize: "0.72rem", color: "var(--ink-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>Available Credit</div>
                <div style={{ fontSize: "0.95rem", fontWeight: 600, marginTop: 3, color: "var(--credit)" }}>
                  {account.credit_limit ? formatMoney(Math.max(0, account.credit_limit - account.balance), account.currency) : "—"}
                </div>
              </div>
              <div>
                <div style={{ fontSize: "0.72rem", color: "var(--ink-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>Card Number</div>
                <div style={{ fontSize: "0.95rem", fontWeight: 500, marginTop: 3, fontFamily: "var(--font-mono, monospace)" }}>
                  {maskedCard || "—"}
                </div>
              </div>
              <div>
                <div style={{ fontSize: "0.72rem", color: "var(--ink-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>Account Type</div>
                <div style={{ fontSize: "0.95rem", fontWeight: 500, marginTop: 3 }}>
                  {formatAccountType(account.account_type)}
                </div>
              </div>
              <div style={{ display: "flex", alignItems: "flex-end" }}>
                <Link
                  to={`/transactions?account=${encodeURIComponent(account.name)}`}
                  className="btn quiet"
                  style={{ fontSize: "0.82rem", display: "inline-flex", alignItems: "center", gap: 5 }}
                >
                  <span>View Transactions</span>
                  <span>→</span>
                </Link>
              </div>
            </div>
          ) : (
            <div>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  marginBottom: 12,
                  flexWrap: "wrap",
                  gap: 8,
                }}
              >
                <div style={{ fontSize: "0.85rem", fontWeight: 600 }}>Account & Card Statements</div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <button
                    type="button"
                    className="btn quiet"
                    style={{ fontSize: "0.8rem", padding: "4px 10px" }}
                    onClick={() => onOpenPasswordProfile(account)}
                  >
                    ⚙ Password Profile
                  </button>
                  <button
                    type="button"
                    className="btn quiet"
                    style={{ fontSize: "0.8rem", padding: "4px 10px" }}
                    onClick={() => onOpenUploadStatement(account)}
                  >
                    + Upload Statement
                  </button>
                </div>
              </div>

              {loadingStatements ? (
                <div className="empty" style={{ padding: 20 }}>Loading statements...</div>
              ) : statements.length > 0 ? (
                <>
                  {/* Desktop Statements Table */}
                  <div className="tx-table-desktop" style={{ overflowX: "auto" }}>
                    <table style={{ width: "100%", fontSize: "0.85rem" }}>
                      <thead>
                        <tr style={{ borderBottom: "1px solid var(--line)" }}>
                          <th
                            style={{ textAlign: "left", padding: "8px 6px", cursor: "pointer", userSelect: "none" }}
                            onClick={() => handleStmtSort("period")}
                            title="Sort by Period"
                          >
                            <div style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                              <span>Period</span>
                              <span style={{ fontSize: "0.72rem", opacity: stmtSortField === "period" ? 1 : 0.3 }}>
                                {stmtSortField === "period" ? (stmtSortDir === "asc" ? "▲" : "▼") : "⇅"}
                              </span>
                            </div>
                          </th>
                          <th
                            style={{ textAlign: "left", padding: "8px 6px", cursor: "pointer", userSelect: "none" }}
                            onClick={() => handleStmtSort("date")}
                            title="Sort by Statement Date"
                          >
                            <div style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                              <span>Statement Date</span>
                              <span style={{ fontSize: "0.72rem", opacity: stmtSortField === "date" ? 1 : 0.3 }}>
                                {stmtSortField === "date" ? (stmtSortDir === "asc" ? "▲" : "▼") : "⇅"}
                              </span>
                            </div>
                          </th>
                          <th
                            style={{ textAlign: "left", padding: "8px 6px", cursor: "pointer", userSelect: "none" }}
                            onClick={() => handleStmtSort("received")}
                            title="Sort by Date Statement Email Was Received"
                          >
                            <div style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                              <span>Received On</span>
                              <span style={{ fontSize: "0.72rem", opacity: stmtSortField === "received" ? 1 : 0.3 }}>
                                {stmtSortField === "received" ? (stmtSortDir === "asc" ? "▲" : "▼") : "⇅"}
                              </span>
                            </div>
                          </th>
                          <th style={{ textAlign: "left", padding: "8px 6px" }}>Status</th>
                          <th style={{ textAlign: "right", padding: "8px 6px" }}>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {sortedStatements.map((stmt) => (
                          <tr
                            key={stmt.id}
                            style={{ borderBottom: "1px solid var(--line)", cursor: "pointer" }}
                            onClick={() => onOpenStatementDetail(stmt)}
                          >
                            <td style={{ padding: "10px 6px", fontWeight: 500 }}>
                              {formatPeriod(stmt.statement_period_start, stmt.statement_period_end)}
                            </td>
                            <td style={{ padding: "10px 6px", color: "var(--ink-muted)" }}>
                              {formatDate(stmt.statement_date)}
                            </td>
                            <td style={{ padding: "10px 6px", color: "var(--ink-muted)", fontSize: "0.82rem" }}>
                              {formatDate(stmt.email_received_at || stmt.discovered_at)}
                            </td>
                            <td style={{ padding: "10px 6px" }}>
                              {getStatusBadge(stmt.status)}
                            </td>
                            <td style={{ padding: "10px 6px", textAlign: "right" }} onClick={(e) => e.stopPropagation()}>
                              <div style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                                <a
                                  href={api.statementOriginalUrl(stmt.id, false)}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="btn quiet"
                                  style={{ fontSize: "0.76rem", padding: "3px 8px" }}
                                >
                                  Original
                                </a>
                                {stmt.has_unlocked_file ? (
                                  <a
                                    href={api.statementUnlockedUrl(stmt.id, false)}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="btn quiet"
                                    style={{ fontSize: "0.76rem", padding: "3px 8px" }}
                                  >
                                    Unlocked
                                  </a>
                                ) : (
                                  <button
                                    type="button"
                                    className="btn primary"
                                    style={{ fontSize: "0.76rem", padding: "3px 8px" }}
                                    onClick={() => onOpenStatementDetail(stmt)}
                                  >
                                    Unlock
                                  </button>
                                )}
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  {/* Mobile Statements Cards */}
                  <div className="tx-cards-mobile" style={{ marginTop: 8 }}>
                    {sortedStatements.map((stmt) => (
                      <article
                        key={stmt.id}
                        className="tx-card"
                        style={{ cursor: "pointer", padding: "10px 12px" }}
                        onClick={() => onOpenStatementDetail(stmt)}
                      >
                        <div className="tx-card-header" style={{ alignItems: "flex-start", gap: 8 }}>
                          <div>
                            <div style={{ fontWeight: 600, fontSize: "0.88rem" }}>
                              {formatPeriod(stmt.statement_period_start, stmt.statement_period_end)}
                            </div>
                            <div style={{ fontSize: "0.76rem", color: "var(--ink-muted)", marginTop: 2 }}>
                              Date: {formatDate(stmt.statement_date)} · Rcvd: {formatDate(stmt.email_received_at || stmt.discovered_at)}
                            </div>
                          </div>
                          <div>
                            {getStatusBadge(stmt.status)}
                          </div>
                        </div>
                        <div className="tx-card-footer" style={{ borderTop: "1px solid var(--line)", paddingTop: 8, marginTop: 8, display: "flex", justifyContent: "flex-end", gap: 6 }} onClick={(e) => e.stopPropagation()}>
                          <a
                            href={api.statementOriginalUrl(stmt.id, false)}
                            target="_blank"
                            rel="noreferrer"
                            className="btn quiet"
                            style={{ fontSize: "0.78rem", padding: "4px 10px" }}
                          >
                            Original
                          </a>
                          {stmt.has_unlocked_file ? (
                            <a
                              href={api.statementUnlockedUrl(stmt.id, false)}
                              target="_blank"
                              rel="noreferrer"
                              className="btn quiet"
                              style={{ fontSize: "0.78rem", padding: "4px 10px" }}
                            >
                              Unlocked
                            </a>
                          ) : (
                            <button
                              type="button"
                              className="btn primary"
                              style={{ fontSize: "0.78rem", padding: "4px 10px" }}
                              onClick={() => onOpenStatementDetail(stmt)}
                            >
                              Unlock
                            </button>
                          )}
                        </div>
                      </article>
                    ))}
                  </div>
                </>
              ) : (
                <div className="empty" style={{ padding: 20 }}>
                  No statements discovered for this credit card yet.
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function AccountsPage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [validHandles, setValidHandles] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);

  // Account editing modal
  const [modalOpen, setModalOpen] = useState(false);
  const [editingAccount, setEditingAccount] = useState<Partial<Account> | null>(null);
  const [deleteTargetAccount, setDeleteTargetAccount] = useState<Account | null>(null);

  // Statement & Password modals
  const [selectedStatement, setSelectedStatement] = useState<CreditCardStatement | null>(null);
  const [statementDetailOpen, setStatementDetailOpen] = useState(false);
  const [passwordProfileAccount, setPasswordProfileAccount] = useState<Account | null>(null);
  const [passwordProfileOpen, setPasswordProfileOpen] = useState(false);
  const [uploadAccount, setUploadAccount] = useState<Account | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);

  const { showToast } = useToast();

  const loadData = async () => {
    setLoading(true);
    try {
      const [accRes, sysRes] = await Promise.all([
        api.accounts(),
        api.system()
      ]);
      setAccounts(accRes.accounts);
      if (sysRes.app?.upi_handles) {
        setValidHandles(sysRes.app.upi_handles);
      }
    } catch (err: any) {
      showToast(err.message, "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleSave = async (data: Partial<Account>) => {
    try {
      if (data.id) {
        await api.updateAccount(data.id, data);
        showToast("Account updated successfully", "success");
      } else {
        await api.createAccount(data);
        showToast("Account created successfully", "success");
      }
      setModalOpen(false);
      loadData();
    } catch (err: any) {
      showToast(err.message, "error");
    }
  };

  const performDelete = async (id: string) => {
    try {
      await api.deleteAccount(id);
      showToast("Account deleted", "success");
      loadData();
    } catch (err: any) {
      showToast(err.message, "error");
    }
  };

  if (loading && accounts.length === 0) return <div className="empty">Loading accounts...</div>;

  const assets = accounts.filter(a => a.is_asset);
  const liabilities = accounts.filter(a => a.is_liability);

  const totalAssetBalance = assets.reduce((sum, a) => sum + (a.balance || 0), 0);
  const totalLiabilityBalance = liabilities.reduce((sum, a) => sum + (a.balance || 0), 0);

  return (
    <>
      <PageHeader
        title="Accounts"
        subtitle={
          <>
            Manage your bank accounts, credit cards, and wallets.
            <span style={{ opacity: 0.4, margin: "0 6px" }}>·</span>
            <span style={{ color: "var(--ink-muted)" }}>
              {assets.length} {assets.length === 1 ? "asset account" : "asset accounts"} · {liabilities.length} credit {liabilities.length === 1 ? "card" : "cards"}
            </span>
          </>
        }
        actions={
          <>
            <Link
              to="/statements"
              className="btn quiet"
              style={{
                height: 38,
                minHeight: 38,
                padding: "0 14px",
                borderRadius: "var(--radius-md)",
                fontSize: "0.85rem",
                fontWeight: 600,
                border: "1px solid var(--line)",
                background: "var(--surface)",
                color: "var(--ink-muted)",
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                textDecoration: "none",
                boxSizing: "border-box",
              }}
            >
              <span>Statements Vault</span>
              <span>→</span>
            </Link>
            <button
              className="btn primary"
              type="button"
              style={{
                height: 38,
                minHeight: 38,
                padding: "0 14px",
                borderRadius: "var(--radius-md)",
                fontSize: "0.85rem",
                fontWeight: 600,
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                boxSizing: "border-box",
              }}
              onClick={() => {
                setEditingAccount(null);
                setModalOpen(true);
              }}
            >
              Add Account
            </button>
          </>
        }
      />

      {/* Assets Section */}
      <div className="section table-wrap">
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12, flexWrap: "wrap", gap: 8 }}>
          <div>
            <h2 style={{ margin: 0 }}>Bank Accounts & Assets</h2>
            <div style={{ fontSize: "0.82rem", color: "var(--ink-muted)", marginTop: 2 }}>
              {assets.length} {assets.length === 1 ? "account" : "accounts"}
            </div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontSize: "0.72rem", color: "var(--ink-muted)", textTransform: "uppercase", letterSpacing: "0.05em", fontWeight: 600 }}>Total Balance</div>
            <div className="tx-amount credit" style={{ fontWeight: 700, fontSize: "1.1rem" }}>
              {formatMoney(totalAssetBalance)}
            </div>
          </div>
        </div>

        {/* Desktop Table View (>= 768px) */}
        <div className="tx-table-desktop">
          <table style={{ marginTop: 8 }}>
            <thead>
              <tr>
                <th>Account</th>
                <th>Type</th>
                <th>Identifier</th>
                <th className="num">Current Balance</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {assets.map(a => {
                const maskedNum = a.account_number_masked ? formatMaskedNumber(a.account_number_masked) : null;
                const upiList = a.upi_identifier_masked ? a.upi_identifier_masked.split(",").map(s => s.trim()).filter(Boolean) : [];

                return (
                  <tr key={a.id}>
                    <td style={{ fontWeight: 600 }}>
                      <Link
                        to={`/transactions?account=${encodeURIComponent(a.name)}`}
                        style={{ textDecoration: "none", color: "inherit", display: "inline-flex", alignItems: "center", gap: 4 }}
                        title={`View transactions for ${a.name}`}
                      >
                        <AccountBadge
                          accountName={a.name}
                          accountType={a.account_type}
                          accountNumberMasked={a.account_number_masked}
                          cardLast4={a.card_last4}
                          logoSize={22}
                          showIdentifiers={false}
                        />
                        <span style={{ fontSize: "0.75rem", opacity: 0.5 }}>↗</span>
                      </Link>
                    </td>
                    <td>
                      <span className="badge" style={{ fontWeight: 500, textTransform: "none", fontSize: "0.78rem" }}>
                        {formatAccountType(a.account_type)}
                      </span>
                    </td>
                    <td>
                      <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                        <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: "0.84rem", color: "var(--ink)" }}>
                          {maskedNum || "—"}
                        </span>
                        {upiList.length > 0 && (
                          <span style={{ color: "var(--ink-muted)", fontSize: "0.76rem" }}>
                            {upiList.join(" · ")}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="num">
                      <Link
                        to={`/transactions?account=${encodeURIComponent(a.name)}`}
                        style={{ textDecoration: "none" }}
                        title={`View transactions for ${a.name}`}
                      >
                        <span className="tx-amount credit" style={{ fontWeight: 600 }}>
                          {formatMoney(a.balance, a.currency)}
                        </span>
                      </Link>
                    </td>
                    <td className="row-actions">
                      <button className="icon-action" type="button" title="Edit Account" aria-label={`Edit ${a.name}`} onClick={() => { setEditingAccount(a); setModalOpen(true); }}>
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/></svg>
                      </button>
                      <button className="icon-action danger" type="button" title="Delete Account" aria-label={`Delete ${a.name}`} onClick={() => setDeleteTargetAccount(a)} style={{ color: "var(--danger)" }}>
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>
                      </button>
                    </td>
                  </tr>
                );
              })}
              {assets.length === 0 && <tr><td colSpan={5} className="empty">No assets recorded.</td></tr>}
            </tbody>
          </table>
        </div>

        {/* Mobile Card Layout (< 768px) */}
        <div className="tx-cards-mobile" style={{ marginTop: 8 }}>
          {assets.map(a => {
            const maskedNum = a.account_number_masked ? formatMaskedNumber(a.account_number_masked) : null;
            const upiList = a.upi_identifier_masked ? a.upi_identifier_masked.split(",").map(s => s.trim()).filter(Boolean) : [];

            return (
              <article key={a.id} className="tx-card">
                <div className="tx-card-header">
                  <div>
                    <Link
                      to={`/transactions?account=${encodeURIComponent(a.name)}`}
                      style={{ textDecoration: "none", color: "inherit" }}
                    >
                      <AccountBadge
                        accountName={a.name}
                        accountType={a.account_type}
                        accountNumberMasked={a.account_number_masked}
                        cardLast4={a.card_last4}
                        logoSize={24}
                        showIdentifiers={false}
                      />
                    </Link>
                    <div style={{ color: "var(--ink-muted)", fontSize: "0.78rem", marginTop: 4, display: "flex", flexWrap: "wrap", gap: "4px 8px" }}>
                      {maskedNum && <span style={{ fontFamily: "var(--font-mono, monospace)" }}>{maskedNum}</span>}
                      {upiList.map(u => <span key={u}>{u}</span>)}
                      {!maskedNum && upiList.length === 0 && <span>No identifiers</span>}
                    </div>
                  </div>
                  <Link
                    to={`/transactions?account=${encodeURIComponent(a.name)}`}
                    style={{ textDecoration: "none" }}
                  >
                    <div className="tx-card-amount credit">{formatMoney(a.balance, a.currency)}</div>
                  </Link>
                </div>
                <div className="tx-card-footer" style={{ borderTop: "1px solid var(--line)", paddingTop: 8 }}>
                  <span className="badge" style={{ textTransform: "none", fontSize: "0.78rem" }}>
                    {formatAccountType(a.account_type)}
                  </span>
                  <div className="tx-card-actions">
                    <button className="btn quiet icon-btn" type="button" title="Edit Account" aria-label={`Edit ${a.name}`} onClick={() => { setEditingAccount(a); setModalOpen(true); }} style={{ width: 34, height: 34 }}>
                      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/></svg>
                    </button>
                    <button className="btn quiet icon-btn" type="button" title="Delete Account" aria-label={`Delete ${a.name}`} onClick={() => setDeleteTargetAccount(a)} style={{ width: 34, height: 34, color: "var(--danger)" }}>
                      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>
                    </button>
                  </div>
                </div>
              </article>
            );
          })}
          {assets.length === 0 && <div className="empty" style={{ padding: 16 }}>No assets recorded.</div>}
        </div>
      </div>

      {/* Credit Cards & Liabilities Section */}
      <div className="section" style={{ marginTop: 32 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12, flexWrap: "wrap", gap: 8 }}>
          <div>
            <h2 style={{ margin: 0 }}>Credit Cards & Liabilities</h2>
            <div style={{ fontSize: "0.82rem", color: "var(--ink-muted)", marginTop: 2 }}>
              {liabilities.length} {liabilities.length === 1 ? "card" : "cards"}
            </div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontSize: "0.72rem", color: "var(--ink-muted)", textTransform: "uppercase", letterSpacing: "0.05em", fontWeight: 600 }}>Total Outstanding</div>
            <div className="tx-amount debit" style={{ fontWeight: 700, fontSize: "1.1rem" }}>
              {formatMoney(totalLiabilityBalance)}
            </div>
          </div>
        </div>

        <div>
          {liabilities.map((acc) => (
            <CreditCardAccountItem
              key={acc.id}
              account={acc}
              onEdit={() => {
                setEditingAccount(acc);
                setModalOpen(true);
              }}
              onDelete={() => setDeleteTargetAccount(acc)}
              onOpenStatementDetail={(stmt) => {
                setSelectedStatement(stmt);
                setStatementDetailOpen(true);
              }}
              onOpenPasswordProfile={(a) => {
                setPasswordProfileAccount(a);
                setPasswordProfileOpen(true);
              }}
              onOpenUploadStatement={(a) => {
                setUploadAccount(a);
                setUploadOpen(true);
              }}
            />
          ))}
          {liabilities.length === 0 && (
            <div className="empty" style={{ padding: 24, background: "var(--surface)", border: "1px solid var(--line)", borderRadius: "var(--radius-md)" }}>
              No liabilities or credit cards recorded.
            </div>
          )}
        </div>
      </div>

      <AccountModal
        open={modalOpen}
        account={editingAccount}
        onClose={() => setModalOpen(false)}
        onSave={handleSave}
        showToast={showToast}
        validHandles={validHandles}
      />

      {/* Delete Account Safe Confirmation Modal */}
      {deleteTargetAccount && (
        <div className="modal-backdrop" role="presentation" onClick={() => setDeleteTargetAccount(null)}>
          <div
            className="modal-panel"
            role="dialog"
            aria-modal="true"
            style={{ width: "min(480px, 100%)", padding: 24, boxSizing: "border-box" }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
              <div
                style={{
                  width: 40,
                  height: 40,
                  borderRadius: "50%",
                  background: "rgba(239, 68, 68, 0.12)",
                  color: "var(--danger)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  flexShrink: 0,
                }}
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>
              </div>
              <div>
                <h3 style={{ margin: 0, fontSize: "1.1rem" }}>Delete Account?</h3>
                <div style={{ color: "var(--ink-muted)", fontSize: "0.85rem", marginTop: 2 }}>{deleteTargetAccount.name}</div>
              </div>
            </div>
            <p style={{ fontSize: "0.88rem", color: "var(--ink)", lineHeight: 1.5, margin: "16px 0" }}>
              This will not delete existing imported transactions, but the account will no longer be available for new classifications and statements.
            </p>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
              <button type="button" className="btn quiet" onClick={() => setDeleteTargetAccount(null)}>
                Cancel
              </button>
              <button
                type="button"
                className="btn"
                style={{ background: "var(--danger)", color: "#fff", border: "none", padding: "6px 14px" }}
                onClick={() => {
                  const id = deleteTargetAccount.id;
                  setDeleteTargetAccount(null);
                  void performDelete(id);
                }}
              >
                Delete Account
              </button>
            </div>
          </div>
        </div>
      )}

      <StatementDetailModal
        open={statementDetailOpen}
        statement={selectedStatement}
        onClose={() => setStatementDetailOpen(false)}
        onStatementUpdated={(updated) => {
          setSelectedStatement(updated);
        }}
      />

      <PasswordProfileModal
        open={passwordProfileOpen}
        account={passwordProfileAccount}
        onClose={() => setPasswordProfileOpen(false)}
        onSaved={() => {
          showToast("Password profile updated", "success");
        }}
      />

      <UploadStatementModal
        open={uploadOpen}
        accounts={accounts}
        defaultAccountId={uploadAccount?.id}
        onClose={() => setUploadOpen(false)}
        onUploaded={(stmt) => {
          setSelectedStatement(stmt);
          setStatementDetailOpen(true);
        }}
      />
    </>
  );
}

