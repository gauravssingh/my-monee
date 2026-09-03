import { useCallback, useEffect, useState, useId, useRef } from "react";
import { createPortal } from "react-dom";
import { api, type Account } from "../api";
import { useToast } from "../hooks/useToast";
import { useBackdropClose, useModalChrome } from "../hooks/useModalChrome";

const STRATEGY_OPTIONS = [
  { value: "NAME4_DDMM", label: "NAME4 + DOB_DDMM (e.g. CKAJ1102 for Axis / HDFC / ICICI)" },
  { value: "NAME4_CARD4", label: "NAME4 + CARD_LAST4 (e.g. CKAJ4951 for Axis Option 2)" },
  { value: "NAME4_DDMMYYYY", label: "NAME4 + DOB_DDMMYYYY (e.g. CKAJ11021985)" },
  { value: "CARD4_DOB", label: "CARD_LAST4 + DOB_DDMM (e.g. 49511102)" },
  { value: "DOB_DDMMYYYY", label: "DOB_DDMMYYYY (e.g. 11021985 for Scapia / Federal)" },
  { value: "DOB_DDMM", label: "DOB_DDMM (e.g. 1102)" },
  { value: "PAN_DOB", label: "PAN4 + DOB_DDMM (e.g. ABCD1102)" },
  { value: "CUSTOM", label: "Custom Static Password" },
];

function extractCleanName4(nameStr: string): string {
  const cleaned = nameStr.replace(/[^a-zA-Z]/g, "");
  return cleaned.slice(0, 4).toUpperCase();
}

function extractDobParts(dobStr: string): { dd: string; mm: string; yyyy: string } {
  const s = dobStr.trim();
  // YYYY-MM-DD
  let m = s.match(/^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$/);
  if (m) return { dd: m[3].padStart(2, "0"), mm: m[2].padStart(2, "0"), yyyy: m[1] };

  // DD-MM-YYYY or DD.MM.YYYY or DD/MM/YYYY
  m = s.match(/^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})$/);
  if (m) return { dd: m[1].padStart(2, "0"), mm: m[2].padStart(2, "0"), yyyy: m[3] };

  // DDMMYYYY
  m = s.match(/^(\d{2})(\d{2})(\d{4})$/);
  if (m) return { dd: m[1], mm: m[2], yyyy: m[3] };

  // DDMM
  m = s.match(/^(\d{2})(\d{2})$/);
  if (m) return { dd: m[1], mm: m[2], yyyy: "" };

  return { dd: "", mm: "", yyyy: "" };
}

export function PasswordProfileModal({
  open,
  account,
  accounts = [],
  onClose,
  onSaved,
}: {
  open: boolean;
  account: Account | null;
  accounts?: Account[];
  onClose: () => void;
  onSaved?: () => void;
}) {
  const titleId = useId();
  const closeRef = useRef<HTMLButtonElement>(null);
  const { showToast } = useToast();

  const [selectedAccountId, setSelectedAccountId] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [strategy, setStrategy] = useState("NAME4_DDMM");
  const [issuer, setIssuer] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [dob, setDob] = useState("");
  const [cardLast4, setCardLast4] = useState("");
  const [pan, setPan] = useState("");
  const [customPassword, setCustomPassword] = useState("");
  const [hasSavedPassword, setHasSavedPassword] = useState(false);

  useModalChrome(open, onClose, closeRef);
  const onBackdropClick = useBackdropClose(open, onClose);

  const activeAccount =
    (accounts.length > 0 && selectedAccountId
      ? accounts.find((a) => a.id === selectedAccountId)
      : null) || account;
  const loadProfileForAccount = useCallback((acc: Account) => {
    const isScapia = acc.name.toLowerCase().includes("scapia") || acc.name.toLowerCase().includes("federal");
    setIssuer(isScapia ? "SCAPIA" : (acc.name.split(" ")[0] || "AXIS"));
    setCardLast4(acc.card_last4 || "");

    api.accountPasswordProfile(acc.id)
      .then((res) => {
        if (res.issuer) setIssuer(res.issuer);
        if (res.strategy) {
          setStrategy(res.strategy);
        } else if (isScapia) {
          setStrategy("CUSTOM");
        }
        const config = res.configuration || {};
        setName(config.name || "");
        setEmail(config.email || "");
        setDob(config.dob || "");
        setCardLast4(config.card_last4 || acc.card_last4 || "");
        setPan(config.pan || "");
        setCustomPassword("");
        setHasSavedPassword(Boolean(config.has_custom_password));
      })
      .catch((err) => {
        console.warn("Could not load password profile:", err);
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    if (open) {
      const targetAcc = account || (accounts.length > 0 ? accounts[0] : null);
      if (targetAcc) {
        setSelectedAccountId(targetAcc.id);
        loadProfileForAccount(targetAcc);
      }
    }
  }, [open, account, accounts, loadProfileForAccount]);

  const handleAccountChange = (newAccId: string) => {
    setSelectedAccountId(newAccId);
    const target = accounts.find((a) => a.id === newAccId);
    if (target) {
      loadProfileForAccount(target);
    }
  };

  if (!open || !activeAccount) return null;

  // Live password candidates calculation for UI preview
  const name4 = extractCleanName4(name);
  const { dd, mm, yyyy } = extractDobParts(dob);
  const card4 = cardLast4.trim() || activeAccount.card_last4 || "";

  const previewCandidates: { label: string; value: string }[] = [];
  if (customPassword.trim()) {
    previewCandidates.push({ label: "Custom Password", value: customPassword.trim() });
  }
  if (name4 && dd && mm) {
    previewCandidates.push({ label: "Option 1 (Name 4 + DDMM)", value: `${name4}${dd}${mm}` });
  }
  if (name4 && card4) {
    previewCandidates.push({ label: "Option 2 (Name 4 + Card Last 4)", value: `${name4}${card4}` });
  }
  if (name4 && dd && mm && yyyy) {
    previewCandidates.push({ label: "Name 4 + DDMMYYYY", value: `${name4}${dd}${mm}${yyyy}` });
  }
  if (card4 && dd && mm) {
    previewCandidates.push({ label: "Card 4 + DDMM", value: `${card4}${dd}${mm}` });
  }
  if (dd && mm && yyyy) {
    previewCandidates.push({ label: "DOB (DDMMYYYY)", value: `${dd}${mm}${yyyy}` });
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const res = await api.updateAccountPasswordProfile(activeAccount.id, {
        issuer: issuer.trim() || activeAccount.name.split(" ")[0] || "AXIS",
        strategy,
        configuration: {
          name: name.trim(),
          email: email.trim(),
          dob: dob.trim(),
          card_last4: cardLast4.trim() || activeAccount.card_last4 || "",
          pan: pan.trim(),
          custom_password: customPassword.trim(),
        },
      });
      const unlockedCount = (res as any)?.unlocked_statements_count || 0;
      if (unlockedCount > 0) {
        showToast(`Saved profile and unlocked ${unlockedCount} pending statement(s)!`, "success");
      } else {
        showToast("Statement password profile saved successfully", "success");
      }
      if (onSaved) onSaved();
      onClose();
    } catch (err: any) {
      showToast(err.message || "Failed to save password profile", "error");
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
        style={{
          width: "100%",
          maxWidth: 580,
          display: "flex",
          flexDirection: "column",
          maxHeight: "90dvh",
          boxSizing: "border-box",
        }}
      >
        <div className="sheet-handle" onClick={onClose} aria-label="Dismiss sheet" />

        <header className="modal-header" style={{ flexShrink: 0, borderBottom: "1px solid var(--line)", paddingBottom: 16 }}>
          <div>
            <div style={{ fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--ink-muted)", fontWeight: 600 }}>
              STATEMENT PASSWORD CONFIGURATION
            </div>
            <h2 id={titleId} style={{ margin: "4px 0 0", fontSize: "1.2rem" }}>
              {activeAccount.name} {activeAccount.card_last4 ? `(•••• ${activeAccount.card_last4})` : ""}
            </h2>
            <p className="lead" style={{ margin: "4px 0 0", fontSize: "0.85rem", color: "var(--ink-muted)" }}>
              Provide account holder details to automatically unlock password-protected PDF statements.
            </p>
          </div>
          <div className="modal-actions">
            <button ref={closeRef} type="button" className="btn icon-btn" onClick={onClose} aria-label="Close modal">
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
            </button>
          </div>
        </header>

        <div className="modal-body" style={{ display: "flex", flexDirection: "column", gap: 16, flex: "1 1 0%", minHeight: 0, overflowY: "auto", padding: "20px 24px" }}>
          {loading ? (
            <div className="empty">Loading profile...</div>
          ) : (
            <>
              {accounts.length > 1 && (
                <div className="field">
                  <label className="label">Select Account to Configure</label>
                  <select
                    className="input"
                    value={selectedAccountId}
                    onChange={(e) => handleAccountChange(e.target.value)}
                  >
                    {accounts.map((acc) => (
                      <option key={acc.id} value={acc.id}>
                        {acc.name} {acc.card_last4 ? `(•••• ${acc.card_last4})` : ""}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                <div className="field">
                  <label className="label">Bank / Card Issuer</label>
                  <input
                    type="text"
                    className="input"
                    value={issuer}
                    onChange={(e) => setIssuer(e.target.value)}
                    placeholder="e.g. AXIS, HDFC, ICICI, SCAPIA"
                    required
                  />
                </div>

                <div className="field">
                  <label className="label">Primary Strategy</label>
                  <select
                    className="input"
                    value={strategy}
                    onChange={(e) => setStrategy(e.target.value)}
                  >
                    {STRATEGY_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Profile Details Section */}
              <div style={{ background: "var(--surface)", border: "1px solid var(--line)", borderRadius: "var(--radius-md)", padding: 16 }}>
                <div style={{ fontSize: "0.82rem", fontWeight: 600, marginBottom: 12 }}>
                  Cardholder / Account Credentials
                </div>

                <div className="field" style={{ marginBottom: 12 }}>
                  <label className="label">Full Name (as appears on account/card)</label>
                  <input
                    type="text"
                    className="input"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="e.g. C.K. Ajay Kumar"
                  />
                  <span style={{ fontSize: "0.76rem", color: "var(--ink-muted)", marginTop: 2 }}>
                    First 4 letters will be used: <strong>{name4 || "—"}</strong> (spaces and periods are automatically omitted).
                  </span>
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 12 }}>
                  <div className="field">
                    <label className="label">Date of Birth (DOB)</label>
                    <input
                      type="text"
                      className="input"
                      value={dob}
                      onChange={(e) => setDob(e.target.value)}
                      placeholder="11.02.1985 or 1985-02-11"
                    />
                    <span style={{ fontSize: "0.74rem", color: "var(--ink-muted)", marginTop: 2 }}>
                      Format: DD.MM.YYYY, DD/MM/YYYY, or YYYY-MM-DD
                    </span>
                  </div>

                  <div className="field">
                    <label className="label">Card / Account Last 4</label>
                    <input
                      type="text"
                      className="input"
                      maxLength={4}
                      value={cardLast4}
                      onChange={(e) => setCardLast4(e.target.value)}
                      placeholder={activeAccount.card_last4 || "e.g. 4951"}
                    />
                    <span style={{ fontSize: "0.74rem", color: "var(--ink-muted)", marginTop: 2 }}>
                      Last 4 digits of card number
                    </span>
                  </div>
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                  <div className="field">
                    <label className="label">Email Address (optional)</label>
                    <input
                      type="email"
                      className="input"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="e.g. name@example.com"
                    />
                  </div>

                  <div className="field">
                    <label className="label">PAN Number (optional)</label>
                    <input
                      type="text"
                      className="input"
                      maxLength={10}
                      value={pan}
                      onChange={(e) => setPan(e.target.value.toUpperCase())}
                      placeholder="e.g. ABCDE1234F"
                    />
                  </div>
                </div>
              </div>

              {/* Custom Fixed Password (Optional) */}
              <div className="field">
                <label className="label">Custom Password Fallback (optional)</label>
                <input
                  type="password"
                  className="input"
                  value={customPassword}
                  onChange={(e) => setCustomPassword(e.target.value)}
                  placeholder={
                    hasSavedPassword
                      ? "Password already saved — leave blank to keep it"
                      : "Enter fixed PDF password if known"
                  }
                  autoComplete="new-password"
                />
              </div>

              {/* Live Candidate Preview */}
              {previewCandidates.length > 0 && (
                <div style={{ background: "rgba(59, 130, 246, 0.06)", border: "1px solid rgba(59, 130, 246, 0.2)", borderRadius: "var(--radius-md)", padding: "12px 16px" }}>
                  <div style={{ fontSize: "0.78rem", textTransform: "uppercase", fontWeight: 600, color: "var(--accent)", marginBottom: 6 }}>
                    Generated Password Candidates Preview
                  </div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                    {previewCandidates.map((c, i) => (
                      <span
                        key={i}
                        className="badge"
                        style={{
                          fontSize: "0.78rem",
                          fontFamily: "monospace",
                          background: "var(--surface)",
                          border: "1px solid var(--line)",
                          padding: "3px 8px",
                        }}
                      >
                        {c.label}: <strong>{c.value}</strong>
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        <footer className="modal-footer" style={{ flexShrink: 0, padding: "12px 24px", borderTop: "1px solid var(--line)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <button type="button" className="btn quiet" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button type="submit" className="btn primary" disabled={saving || loading}>
            {saving ? "Saving & Reprocessing..." : "Save Profile & Unlock Statements"}
          </button>
        </footer>
      </form>
    </div>,
    document.body
  );
}
