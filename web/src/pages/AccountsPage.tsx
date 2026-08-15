import { useEffect, useState, useId, useRef } from "react";
import { createPortal } from "react-dom";
import { api, type Account } from "../api";
import { useToast } from "../hooks/useToast";
import { formatMoney } from "../format";
import { useBackdropClose, useModalChrome } from "../hooks/useModalChrome";

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
      <form className="modal-panel" aria-labelledby={titleId} onClick={(e) => e.stopPropagation()} onSubmit={handleSubmit} style={{ width: "100%", maxWidth: 650 }}>
        <header className="modal-header">
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

        <div className="modal-body" style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          
          {/* Section: Basic Info */}
          <section style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <h3 style={{ fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--ink-muted)", margin: 0, fontWeight: 600 }}>BASIC INFORMATION</h3>
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <div className="field">
                <label className="label">Account Name <span style={{color: "var(--accent)"}}>*</span></label>
                <input
                  type="text"
                  className="input"
                  value={formData.name || ""}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  required
                  placeholder="e.g. HDFC Checking"
                />
              </div>

              <div className="field">
                <label className="label">Account Type</label>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
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
          <section style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <h3 style={{ fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--ink-muted)", margin: 0, fontWeight: 600 }}>IDENTIFIERS (OPTIONAL)</h3>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
              <div className="field">
                <label className="label">Account Mask (Last 4)</label>
                <input
                  type="text"
                  className="input"
                  value={formData.account_number_masked || ""}
                  onChange={(e) => setFormData({ ...formData, account_number_masked: e.target.value })}
                  placeholder="e.g. x1234"
                />
              </div>
              
              {formData.account_type === "CREDIT_CARD" ? (
                <div className="field">
                  <label className="label">Card Last 4</label>
                  <input
                    type="text"
                    className="input"
                    value={formData.card_last4 || ""}
                    onChange={(e) => setFormData({ ...formData, card_last4: e.target.value })}
                    placeholder="e.g. 5678"
                    maxLength={4}
                  />
                </div>
              ) : (
                <div className="field">
                  <label className="label">UPI IDs / Phones</label>
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {(formData.upi_identifier_masked ? formData.upi_identifier_masked.split(",") : [""]).map((upi, i, arr) => (
                      <div key={i} style={{ display: "flex", gap: 8 }}>
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
          <section style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <h3 style={{ fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--ink-muted)", margin: 0, fontWeight: 600 }}>BALANCES & LIMITS</h3>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
              <div className="field">
                <label className="label">Opening Balance</label>
                <div style={{ display: "flex", gap: 8 }}>
                  <div style={{ padding: "0 12px", border: "1px solid var(--line)", borderRadius: "var(--radius-sm)", background: "var(--surface)", color: "var(--ink-muted)", fontSize: "0.9rem", display: "flex", alignItems: "center" }}>
                    ₹ INR
                  </div>
                  <input
                    type="number"
                    className="input"
                    style={{ flex: 1 }}
                    value={formData.opening_balance || ""}
                    onChange={(e) => setFormData({ ...formData, opening_balance: parseFloat(e.target.value) || 0 })}
                    placeholder="0.00"
                    step="0.01"
                  />
                </div>
              </div>

              {formData.account_type === "CREDIT_CARD" && (
                <div className="field">
                  <label className="label">Credit Limit</label>
                  <div style={{ display: "flex", gap: 8 }}>
                    <div style={{ padding: "0 12px", border: "1px solid var(--line)", borderRadius: "var(--radius-sm)", background: "var(--surface)", color: "var(--ink-muted)", fontSize: "0.9rem", display: "flex", alignItems: "center" }}>
                      ₹ INR
                    </div>
                    <input
                      type="number"
                      className="input"
                      style={{ flex: 1 }}
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

        <footer className="modal-footer">
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

export default function AccountsPage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [validHandles, setValidHandles] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingAccount, setEditingAccount] = useState<Partial<Account> | null>(null);
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

  const handleDelete = async (id: string) => {
    if (!confirm("Are you sure you want to delete this account? This cannot be undone.")) return;
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

  return (
    <>
      <header className="page-header">
        <div>
          <h1>Accounts</h1>
          <p className="lead">Manage your bank accounts, credit cards, and wallets.</p>
        </div>
        <div className="page-actions">
          <button 
            className="btn primary"
            onClick={() => {
              setEditingAccount(null);
              setModalOpen(true);
            }}
          >
            Add Account
          </button>
        </div>
      </header>

      <div className="section table-wrap">
        <h2>Assets</h2>
        <table style={{ marginTop: 8 }}>
          <thead>
            <tr>
              <th>Account Name</th>
              <th>Type</th>
              <th>Identifiers</th>
              <th className="num">Current Balance</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {assets.map(a => (
              <tr key={a.id}>
                <td style={{ fontWeight: 600 }}>{a.name}</td>
                <td><span className="badge">{a.account_type}</span></td>
                <td style={{ color: "var(--ink-muted)", fontSize: "0.88rem" }}>
                  {[a.account_number_masked, ...(a.upi_identifier_masked ? a.upi_identifier_masked.split(",").filter(s => s.trim()) : [])].filter(Boolean).join(" · ") || "—"}
                </td>
                <td className="num tx-amount credit">{formatMoney(a.balance, a.currency)}</td>
                <td className="row-actions">
                  <button className="icon-action" type="button" title="Edit Account" aria-label={`Edit ${a.name}`} onClick={() => { setEditingAccount(a); setModalOpen(true); }}>
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/></svg>
                  </button>
                  <button className="icon-action danger" type="button" title="Delete Account" aria-label={`Delete ${a.name}`} onClick={() => handleDelete(a.id)} style={{ color: "var(--danger)" }}>
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>
                  </button>
                </td>
              </tr>
            ))}
            {assets.length === 0 && <tr><td colSpan={5} className="empty">No assets recorded.</td></tr>}
          </tbody>
        </table>
      </div>

      <div className="section table-wrap" style={{ marginTop: 32 }}>
        <h2>Liabilities & Credit Cards</h2>
        <table style={{ marginTop: 8 }}>
          <thead>
            <tr>
              <th>Account Name</th>
              <th>Type</th>
              <th>Identifiers</th>
              <th className="num">Current Balance</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {liabilities.map(a => (
              <tr key={a.id}>
                <td style={{ fontWeight: 600 }}>{a.name}</td>
                <td><span className="badge">{a.account_type}</span></td>
                <td style={{ color: "var(--ink-muted)", fontSize: "0.88rem" }}>
                  {[a.account_number_masked, a.card_last4].filter(Boolean).join(" · ") || "—"}
                </td>
                <td className="num tx-amount debit">{formatMoney(a.balance, a.currency)}</td>
                <td className="row-actions">
                  <button className="icon-action" type="button" title="Edit Account" aria-label={`Edit ${a.name}`} onClick={() => { setEditingAccount(a); setModalOpen(true); }}>
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/></svg>
                  </button>
                  <button className="icon-action danger" type="button" title="Delete Account" aria-label={`Delete ${a.name}`} onClick={() => handleDelete(a.id)} style={{ color: "var(--danger)" }}>
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>
                  </button>
                </td>
              </tr>
            ))}
            {liabilities.length === 0 && <tr><td colSpan={5} className="empty">No liabilities recorded.</td></tr>}
          </tbody>
        </table>
      </div>

      <AccountModal
        open={modalOpen}
        account={editingAccount}
        onClose={() => setModalOpen(false)}
        onSave={handleSave}
        showToast={showToast}
        validHandles={validHandles}
      />
    </>
  );
}
