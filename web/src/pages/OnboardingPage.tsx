import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";

const CURRENCIES = [
  { code: "INR", symbol: "₹", name: "Indian Rupee" },
  { code: "USD", symbol: "$", name: "US Dollar" },
  { code: "EUR", symbol: "€", name: "Euro" },
  { code: "GBP", symbol: "£", name: "British Pound" },
  { code: "JPY", symbol: "¥", name: "Japanese Yen" },
  { code: "CAD", symbol: "C$", name: "Canadian Dollar" },
  { code: "AUD", symbol: "A$", name: "Australian Dollar" },
  { code: "SGD", symbol: "S$", name: "Singapore Dollar" },
  { code: "AED", symbol: "AED", name: "UAE Dirham" },
];

const LOCALES = [
  { code: "en-IN", name: "English (India) · Lakhs & Crores (₹1,00,000)" },
  { code: "en-US", name: "English (US) · Millions ($100,000)" },
  { code: "en-GB", name: "English (UK) · Millions (£100,000)" },
  { code: "de-DE", name: "German (Europe) · 100.000 €" },
];

type DiscoveredInstitution = {
  name: string;
  type: string;
  icon: string;
  status: string;
  sample_subject?: string | null;
};

type AccountConfig = {
  id?: string;
  name: string;
  account_type: "bank" | "credit_card" | "wallet" | "cash";
  currency: string;
  is_asset: boolean;
  is_liability: boolean;
  opening_balance: number;
  payment_account_id?: string | null;
  auto_identify_bill_payments: boolean;
};

export default function OnboardingPage() {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // Step 1: Protect
  const [authConfigured, setAuthConfigured] = useState(false);
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [authError, setAuthError] = useState<string | null>(null);

  // Step 2: Region
  const [currency, setCurrency] = useState("INR");
  const [locale, setLocale] = useState("en-IN");

  // Step 3: Connect
  const [gmailConnected, setGmailConnected] = useState(false);
  const [showAdvancedOAuth, setShowAdvancedOAuth] = useState(false);
  const [oauthClientId, setOauthClientId] = useState("");
  const [oauthClientSecret, setOauthClientSecret] = useState("");

  // Step 4: Discover
  const [institutions, setInstitutions] = useState<DiscoveredInstitution[]>([]);
  const [scanLoading, setScanLoading] = useState(false);

  // Step 5: Configure Accounts & Relationships
  const [accounts, setAccounts] = useState<AccountConfig[]>([]);

  // Step 6: Historical Import & Calibration
  const [syncHorizon, setSyncHorizon] = useState<"3m" | "6m" | "1y" | "2y">("6m");
  const [isSyncing, setIsSyncing] = useState(false);
  const [calibrationDone, setCalibrationDone] = useState(false);
  const [calibrationSummary, setCalibrationSummary] = useState<{
    accounts_configured: number;
    transactions_ingested: number;
    recurring_configured: number;
    needs_review_count: number;
  }>({ accounts_configured: 0, transactions_ingested: 0, recurring_configured: 0, needs_review_count: 0 });

  // Load initial state
  useEffect(() => {
    setLoading(true);
    api.onboardingState()
      .then((state) => {
        setAuthConfigured(state.auth_configured);
        setGmailConnected(state.gmail_connected);
        setCurrency(state.currency || "INR");
        setLocale(state.locale || "en-IN");

        if (state.discovered.accounts.length > 0) {
          setAccounts(
            state.discovered.accounts.map((a) => ({
              id: a.id,
              name: a.name,
              account_type: (a.account_type.toLowerCase() as any) || "bank",
              currency: state.currency || "INR",
              is_asset: a.is_asset,
              is_liability: a.is_liability,
              opening_balance: a.opening_balance || 0,
              payment_account_id: a.payment_account_id || null,
              auto_identify_bill_payments: true,
            }))
          );
        } else {
          // Default initial accounts
          setAccounts([
            {
              name: "Primary Bank Account",
              account_type: "bank",
              currency: state.currency || "INR",
              is_asset: true,
              is_liability: false,
              opening_balance: 0,
              auto_identify_bill_payments: true,
            },
          ]);
        }

        // Set step based on progress
        if (!state.auth_configured) {
          setStep(1);
        } else if (state.completed) {
          setStep(6);
          setCalibrationDone(true);
        } else if (state.progress.step) {
          setStep(Math.min(6, state.progress.step));
        } else {
          setStep(2);
        }
      })
      .catch((err) => {
        console.error("Failed to load onboarding state:", err);
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);

  // Password strength calculation
  const passwordStrength = useMemo(() => {
    if (!password) return 0;
    let score = 0;
    if (password.length >= 6) score += 25;
    if (password.length >= 10) score += 25;
    if (/[A-Z]/.test(password) && /[a-z]/.test(password)) score += 25;
    if (/[0-9]/.test(password) || /[^A-Za-z0-9]/.test(password)) score += 25;
    return score;
  }, [password]);

  // Handle Step 1 Save (Password)
  const handleSavePassword = async () => {
    setAuthError(null);
    if (!authConfigured) {
      if (password.length < 4) {
        setAuthError("Password must be at least 4 characters.");
        return;
      }
      if (password !== confirmPassword) {
        setAuthError("Passwords do not match.");
        return;
      }
    }
    setSaving(true);
    try {
      if (password) {
        await api.saveOnboardingStep(1, { password });
        setAuthConfigured(true);
      }
      setStep(2);
    } catch (err: any) {
      setAuthError(err.message || "Failed to set master password.");
    } finally {
      setSaving(false);
    }
  };

  // Handle Step 2 Save (Region)
  const handleSaveRegion = async () => {
    setSaving(true);
    try {
      await api.saveOnboardingStep(2, { currency, locale });
      setStep(3);
    } catch (err) {
      console.error("Failed to save regional settings:", err);
    } finally {
      setSaving(false);
    }
  };

  // Handle Step 3 (Connect Gmail / Skip)
  const handleConnectGmail = () => {
    window.location.href = "/api/gmail/oauth/start";
  };

  const handleSkipGmail = async () => {
    setSaving(true);
    try {
      await api.saveOnboardingStep(3, { skipped: true });
      // Trigger fast discovery scan
      handleTriggerScan();
      setStep(4);
    } catch (err) {
      console.error("Failed to skip Gmail:", err);
    } finally {
      setSaving(false);
    }
  };

  // Handle Step 4 (Fast Discovery Scan)
  const handleTriggerScan = async () => {
    setScanLoading(true);
    try {
      const res = await api.onboardingFastScan();
      setInstitutions(res.institutions);

      // Synthesize account suggestions from discovered institutions if no accounts exist
      if (accounts.length <= 1) {
        const newAccs: AccountConfig[] = res.institutions.map((inst) => ({
          name: inst.name,
          account_type: inst.type === "CREDIT_CARD" ? "credit_card" : inst.type === "WALLET" ? "wallet" : "bank",
          currency: currency,
          is_asset: inst.type !== "CREDIT_CARD",
          is_liability: inst.type === "CREDIT_CARD",
          opening_balance: 0,
          auto_identify_bill_payments: true,
        }));
        if (newAccs.length > 0) {
          setAccounts(newAccs);
        }
      }
    } catch (err) {
      console.error("Failed to run fast scan:", err);
    } finally {
      setScanLoading(false);
    }
  };

  // Handle Step 5 (Save Accounts & Relationships)
  const handleSaveAccounts = async () => {
    setSaving(true);
    try {
      await api.saveOnboardingStep(5, { accounts });
      setStep(6);
    } catch (err) {
      console.error("Failed to save accounts:", err);
    } finally {
      setSaving(false);
    }
  };

  // Handle Step 6 (Historical Import & Calibration)
  const handleStartImport = async () => {
    setIsSyncing(true);
    try {
      if (gmailConnected) {
        await api.gmailSync().catch(() => {});
      }
      const completeRes = await api.completeOnboarding({
        primary_salary: { name: "Primary Income", expected_amount: 0 },
        recurring_items: [],
      });
      setCalibrationSummary(completeRes.calibration || {
        accounts_configured: accounts.length,
        transactions_ingested: 0,
        recurring_configured: 0,
        needs_review_count: 0,
      });
      setCalibrationDone(true);
    } catch (err) {
      console.error("Failed to complete historical calibration:", err);
      setCalibrationDone(true);
    } finally {
      setIsSyncing(false);
    }
  };

  const steps = [
    { num: 1, title: "Protect", desc: "Encryption & Passcode" },
    { num: 2, title: "Region", desc: "Currency & Locale" },
    { num: 3, title: "Connect", desc: "Financial Inbox" },
    { num: 4, title: "Discover", desc: "Institution Scan" },
    { num: 5, title: "Configure", desc: "Accounts & Relations" },
    { num: 6, title: "Import", desc: "Calibration & Launch" },
  ];

  if (loading) {
    return (
      <div style={{ minHeight: "80vh", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 12 }}>
        <div className="spinner" style={{ width: 32, height: 32, border: "3px solid var(--line)", borderTopColor: "var(--accent)", borderRadius: "50%" }} />
        <div style={{ color: "var(--ink-muted)", fontSize: "0.95rem" }}>Initializing MyMonee setup…</div>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 840, margin: "20px auto 60px", padding: "0 16px min(40px, env(safe-area-inset-bottom, 40px))" }}>
      {/* Top Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <img src="/logo.png" alt="MyMonee Logo" style={{ width: 32, height: 32, borderRadius: 8 }} />
          <div style={{ fontWeight: 700, fontSize: "1.1rem" }}>MyMonee Setup</div>
        </div>
        <button
          type="button"
          onClick={() => navigate("/")}
          className="btn quiet"
          style={{ fontSize: "0.82rem", color: "var(--ink-muted)" }}
        >
          ✕ Exit Setup
        </button>
      </div>

      {/* 6-Step Stepper Progress Bar */}
      <div style={{ marginBottom: 28 }}>
        <div className="wizard-desktop-steps" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", position: "relative" }}>
          <div
            style={{
              position: "absolute",
              top: 18,
              left: 40,
              right: 40,
              height: 2,
              background: "var(--line)",
              zIndex: 0,
            }}
          >
            <div
              style={{
                height: "100%",
                background: "var(--accent)",
                width: `${((step - 1) / (steps.length - 1)) * 100}%`,
                transition: "width 0.3s ease",
              }}
            />
          </div>

          {steps.map((s) => {
            const isCompleted = step > s.num;
            const isCurrent = step === s.num;
            return (
              <div
                key={s.num}
                onClick={() => {
                  if (s.num < step) setStep(s.num);
                }}
                style={{
                  position: "relative",
                  zIndex: 1,
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  cursor: s.num < step ? "pointer" : "default",
                }}
              >
                <div
                  style={{
                    width: 36,
                    height: 36,
                    borderRadius: "50%",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontWeight: 700,
                    fontSize: "0.88rem",
                    background: isCurrent ? "var(--accent)" : isCompleted ? "var(--surface)" : "var(--surface)",
                    color: isCurrent ? "#fff" : isCompleted ? "var(--credit, #2f6d4f)" : "var(--ink-muted)",
                    border: `2px solid ${isCurrent ? "var(--accent)" : isCompleted ? "var(--credit, #2f6d4f)" : "var(--line)"}`,
                    boxShadow: isCurrent ? "0 0 0 4px var(--accent-soft)" : "none",
                  }}
                >
                  {isCompleted ? "✓" : s.num}
                </div>
                <span
                  style={{
                    marginTop: 6,
                    fontSize: "0.78rem",
                    fontWeight: isCurrent ? 700 : 500,
                    color: isCurrent ? "var(--ink)" : "var(--ink-muted)",
                  }}
                >
                  {s.title}
                </span>
              </div>
            );
          })}
        </div>

        {/* Mobile Stepper Bar */}
        <div className="wizard-mobile-steps">
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.86rem", fontWeight: 600, marginBottom: 6 }}>
            <span>Step {step} of 6</span>
            <span style={{ color: "var(--accent)" }}>{steps[step - 1]?.title}</span>
          </div>
          <div style={{ width: "100%", height: 6, background: "var(--surface-muted)", borderRadius: 3, overflow: "hidden" }}>
            <div style={{ width: `${(step / 6) * 100}%`, height: "100%", background: "var(--accent)", transition: "width 0.3s ease" }} />
          </div>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* STEP 1: PROTECT YOUR FINANCIAL DATA */}
      {/* ========================================================================= */}
      {step === 1 && (
        <div className="surface" style={{ padding: "32px 28px", borderRadius: "var(--radius-lg)", border: "1px solid var(--line)" }}>
          <div style={{ marginBottom: 20 }}>
            <div style={{ fontSize: "1.8rem", marginBottom: 8 }}>🔒</div>
            <h2 style={{ fontSize: "1.35rem", fontWeight: 700, margin: 0 }}>Protect Your Financial Data</h2>
            <p style={{ color: "var(--ink-muted)", margin: "6px 0 0 0", fontSize: "0.90rem", lineHeight: 1.45 }}>
              Create a master password. This derives a local encryption key using PBKDF2/salt to protect your offline SQLite ledger and credentials.
            </p>
          </div>

          {authConfigured ? (
            <div style={{ padding: "16px", background: "var(--surface-muted)", border: "1px solid var(--line)", borderRadius: "var(--radius-md)", marginBottom: 24 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10, color: "var(--credit, #2f6d4f)", fontWeight: 600, fontSize: "0.92rem" }}>
                <span>✓</span>
                <span>Master password already configured for this device</span>
              </div>
              <div style={{ fontSize: "0.80rem", color: "var(--ink-muted)", marginTop: 4 }}>
                You can keep your existing protection password or enter a new one below.
              </div>
            </div>
          ) : null}

          <div style={{ display: "flex", flexDirection: "column", gap: 16, maxWidth: 440 }}>
            <div>
              <label style={{ display: "block", fontSize: "0.84rem", fontWeight: 600, marginBottom: 6 }}>
                {authConfigured ? "New Password (optional)" : "Create Master Password"}
              </label>
              <input
                type="password"
                className="input"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter a secure password…"
                style={{ width: "100%", padding: "10px 14px", fontSize: "0.95rem" }}
              />
            </div>

            {password.length > 0 && (
              <div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.75rem", marginBottom: 4, color: "var(--ink-muted)" }}>
                  <span>Password Strength</span>
                  <span>{passwordStrength >= 75 ? "Strong" : passwordStrength >= 50 ? "Moderate" : "Weak"}</span>
                </div>
                <div style={{ width: "100%", height: 4, background: "var(--line)", borderRadius: 2, overflow: "hidden" }}>
                  <div
                    style={{
                      width: `${passwordStrength}%`,
                      height: "100%",
                      background: passwordStrength >= 75 ? "var(--credit, #2f6d4f)" : passwordStrength >= 50 ? "var(--accent)" : "var(--danger)",
                      transition: "width 0.2s ease",
                    }}
                  />
                </div>
              </div>
            )}

            <div>
              <label style={{ display: "block", fontSize: "0.84rem", fontWeight: 600, marginBottom: 6 }}>
                Confirm Password
              </label>
              <input
                type="password"
                className="input"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="Re-enter password…"
                style={{ width: "100%", padding: "10px 14px", fontSize: "0.95rem" }}
              />
            </div>

            {authError && (
              <div style={{ padding: "10px 12px", background: "var(--debit-soft, rgba(165,51,59,0.08))", border: "1px solid var(--debit, #a5333b)", borderRadius: "var(--radius-sm)", color: "var(--debit, #a5333b)", fontSize: "0.84rem" }}>
                {authError}
              </div>
            )}

            <div style={{ padding: "12px 14px", background: "var(--surface-muted)", borderRadius: "var(--radius-sm)", fontSize: "0.78rem", color: "var(--ink-muted)", lineHeight: 1.4 }}>
              <strong>Local-First Encryption Notice:</strong> MyMonee does not store your password in plaintext or on the cloud. If you lose this password, encrypted secrets cannot be recovered.
            </div>
          </div>

          <div style={{ marginTop: 28, display: "flex", justifyContent: "flex-end" }}>
            <button
              className="btn primary"
              type="button"
              onClick={handleSavePassword}
              disabled={saving}
              style={{ padding: "10px 24px", fontWeight: 600 }}
            >
              {saving ? "Saving…" : "Continue to Regional Settings →"}
            </button>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* STEP 2: REGIONAL SETTINGS */}
      {/* ========================================================================= */}
      {step === 2 && (
        <div className="surface" style={{ padding: "32px 28px", borderRadius: "var(--radius-lg)", border: "1px solid var(--line)" }}>
          <div style={{ marginBottom: 22 }}>
            <div style={{ fontSize: "1.8rem", marginBottom: 8 }}>🌍</div>
            <h2 style={{ fontSize: "1.35rem", fontWeight: 700, margin: 0 }}>Regional Settings</h2>
            <p style={{ color: "var(--ink-muted)", margin: "6px 0 0 0", fontSize: "0.90rem" }}>
              Select your primary accounting currency and number formatting preference.
            </p>
          </div>

          <div style={{ marginBottom: 24 }}>
            <label style={{ display: "block", fontSize: "0.84rem", fontWeight: 600, marginBottom: 10 }}>
              Primary Currency
            </label>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 10 }}>
              {CURRENCIES.map((curr) => {
                const isSelected = currency === curr.code;
                return (
                  <div
                    key={curr.code}
                    onClick={() => setCurrency(curr.code)}
                    style={{
                      padding: "12px 14px",
                      border: `1.5px solid ${isSelected ? "var(--accent)" : "var(--line)"}`,
                      background: isSelected ? "var(--accent-soft)" : "var(--surface)",
                      borderRadius: "var(--radius-md)",
                      cursor: "pointer",
                      display: "flex",
                      alignItems: "center",
                      gap: 10,
                    }}
                  >
                    <span style={{ fontSize: "1.2rem", fontWeight: 700, color: isSelected ? "var(--accent)" : "var(--ink)" }}>
                      {curr.symbol}
                    </span>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: "0.88rem", color: isSelected ? "var(--accent)" : "var(--ink)" }}>
                        {curr.name}
                      </div>
                      <div style={{ fontSize: "0.74rem", color: "var(--ink-muted)" }}>{curr.code}</div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div style={{ marginBottom: 28, maxWidth: 440 }}>
            <label style={{ display: "block", fontSize: "0.84rem", fontWeight: 600, marginBottom: 8 }}>
              Number &amp; Date Locale
            </label>
            <select
              className="input"
              value={locale}
              onChange={(e) => setLocale(e.target.value)}
              style={{ width: "100%", padding: "10px 12px", fontSize: "0.90rem" }}
            >
              {LOCALES.map((loc) => (
                <option key={loc.code} value={loc.code}>
                  {loc.name}
                </option>
              ))}
            </select>
          </div>

          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <button className="btn quiet" type="button" onClick={() => setStep(1)}>
              ← Back
            </button>
            <button
              className="btn primary"
              type="button"
              onClick={handleSaveRegion}
              disabled={saving}
              style={{ padding: "10px 24px", fontWeight: 600 }}
            >
              {saving ? "Saving…" : "Continue to Financial Inbox →"}
            </button>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* STEP 3: CONNECT FINANCIAL INBOX (OPTIONAL) */}
      {/* ========================================================================= */}
      {step === 3 && (
        <div className="surface" style={{ padding: "32px 28px", borderRadius: "var(--radius-lg)", border: "1px solid var(--line)" }}>
          <div style={{ marginBottom: 22 }}>
            <div style={{ fontSize: "1.8rem", marginBottom: 8 }}>✉️</div>
            <h2 style={{ fontSize: "1.35rem", fontWeight: 700, margin: 0 }}>Connect Your Financial Inbox</h2>
            <p style={{ color: "var(--ink-muted)", margin: "6px 0 0 0", fontSize: "0.90rem", lineHeight: 1.45 }}>
              MyMonee can securely scan your Gmail for bank debits, credit card alerts, and UPI notifications.
              Connecting Gmail is entirely optional—you can also manage accounts manually or upload PDF statements.
            </p>
          </div>

          {/* Connection Status Card */}
          <div style={{ padding: "20px", background: "var(--surface-muted)", border: "1px solid var(--line)", borderRadius: "var(--radius-md)", marginBottom: 24 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <span style={{ fontSize: "1.6rem" }}>📬</span>
                <div>
                  <div style={{ fontWeight: 600, fontSize: "0.95rem" }}>
                    {gmailConnected ? "Gmail Inbox Connected" : "Read-Only Gmail Access"}
                  </div>
                  <div style={{ fontSize: "0.80rem", color: "var(--ink-muted)", marginTop: 2 }}>
                    {gmailConnected
                      ? "OAuth authorized · Ready to scan financial alerts"
                      : "Strict read-only scope (gmail.readonly). Emails never leave your machine."}
                  </div>
                </div>
              </div>
              <div>
                {gmailConnected ? (
                  <span className="badge ok" style={{ fontSize: "0.84rem", padding: "6px 12px" }}>
                    ✓ Connected
                  </span>
                ) : (
                  <button
                    type="button"
                    className="btn primary"
                    onClick={handleConnectGmail}
                    style={{ padding: "8px 18px", fontWeight: 600 }}
                  >
                    Connect Gmail
                  </button>
                )}
              </div>
            </div>
          </div>

          {/* Progressive Disclosure for Self-Hosters */}
          <div style={{ marginBottom: 24 }}>
            <button
              type="button"
              className="btn quiet"
              onClick={() => setShowAdvancedOAuth(!showAdvancedOAuth)}
              style={{ fontSize: "0.82rem", color: "var(--ink-muted)", padding: 0 }}
            >
              {showAdvancedOAuth ? "▲ Hide Advanced OAuth Configuration" : "⚙️ Advanced / Custom Google Cloud OAuth (Self-Hosted)"}
            </button>

            {showAdvancedOAuth && (
              <div style={{ marginTop: 14, padding: "16px", background: "var(--surface)", border: "1px solid var(--line)", borderRadius: "var(--radius-md)" }}>
                <div style={{ fontSize: "0.84rem", fontWeight: 600, marginBottom: 8 }}>
                  Custom Google OAuth Client
                </div>
                <div style={{ fontSize: "0.78rem", color: "var(--ink-muted)", marginBottom: 12, lineHeight: 1.4 }}>
                  If you are self-hosting on your own domain, configure your Google Cloud Console OAuth redirect URI to:
                  <code style={{ display: "block", marginTop: 4, padding: "6px 8px", background: "var(--surface-muted)", borderRadius: 4 }}>
                    {window.location.origin}/oauth/callback
                  </code>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  <input
                    type="text"
                    className="input"
                    placeholder="Google Client ID…"
                    value={oauthClientId}
                    onChange={(e) => setOauthClientId(e.target.value)}
                    style={{ width: "100%", padding: "8px 12px", fontSize: "0.85rem" }}
                  />
                  <input
                    type="password"
                    className="input"
                    placeholder="Google Client Secret…"
                    value={oauthClientSecret}
                    onChange={(e) => setOauthClientSecret(e.target.value)}
                    style={{ width: "100%", padding: "8px 12px", fontSize: "0.85rem" }}
                  />
                </div>
              </div>
            )}
          </div>

          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <button className="btn quiet" type="button" onClick={() => setStep(2)}>
              ← Back
            </button>
            <div style={{ display: "flex", gap: 10 }}>
              {!gmailConnected && (
                <button className="btn quiet" type="button" onClick={handleSkipGmail}>
                  I'll do this later (Skip)
                </button>
              )}
              <button
                className="btn primary"
                type="button"
                onClick={() => {
                  handleTriggerScan();
                  setStep(4);
                }}
                style={{ padding: "10px 24px", fontWeight: 600 }}
              >
                Continue to Discovery →
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* STEP 4: FINANCIAL DISCOVERY SCAN */}
      {/* ========================================================================= */}
      {step === 4 && (
        <div className="surface" style={{ padding: "32px 28px", borderRadius: "var(--radius-lg)", border: "1px solid var(--line)" }}>
          <div style={{ marginBottom: 22 }}>
            <div style={{ fontSize: "1.8rem", marginBottom: 8 }}>🔍</div>
            <h2 style={{ fontSize: "1.35rem", fontWeight: 700, margin: 0 }}>Financial Discovery</h2>
            <p style={{ color: "var(--ink-muted)", margin: "6px 0 0 0", fontSize: "0.90rem" }}>
              Surveying financial evidence to recognize your bank accounts, credit cards, and wallets.
            </p>
          </div>

          {scanLoading ? (
            <div style={{ padding: "40px 20px", textAlign: "center" }}>
              <div className="spinner" style={{ width: 28, height: 28, margin: "0 auto 12px" }} />
              <div style={{ color: "var(--ink-muted)", fontSize: "0.88rem" }}>Scanning financial institutions…</div>
            </div>
          ) : (
            <div style={{ marginBottom: 28 }}>
              <div style={{ fontSize: "11px", color: "var(--ink-muted)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 12 }}>
                Recognized Institutions &amp; Channels ({institutions.length})
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12 }}>
                {institutions.map((inst, idx) => (
                  <div
                    key={idx}
                    style={{
                      padding: "14px 16px",
                      background: "var(--surface-muted)",
                      border: "1px solid var(--line)",
                      borderRadius: "var(--radius-md)",
                      display: "flex",
                      alignItems: "center",
                      gap: 12,
                    }}
                  >
                    <span style={{ fontSize: "1.5rem" }}>{inst.icon}</span>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: "0.92rem" }}>{inst.name}</div>
                      <div style={{ fontSize: "0.75rem", color: "var(--ink-muted)", marginTop: 2 }}>
                        {inst.type === "CREDIT_CARD" ? "Credit Card" : inst.type === "WALLET" ? "Digital Wallet" : "Bank Account"}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <button className="btn quiet" type="button" onClick={() => setStep(3)}>
              ← Back
            </button>
            <button
              className="btn primary"
              type="button"
              onClick={() => setStep(5)}
              style={{ padding: "10px 24px", fontWeight: 600 }}
            >
              Configure Discovered Accounts →
            </button>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* STEP 5: CONFIGURE ACCOUNTS & RELATIONSHIPS */}
      {/* ========================================================================= */}
      {step === 5 && (
        <div className="surface" style={{ padding: "32px 28px", borderRadius: "var(--radius-lg)", border: "1px solid var(--line)" }}>
          <div style={{ marginBottom: 22 }}>
            <div style={{ fontSize: "1.8rem", marginBottom: 8 }}>🏦</div>
            <h2 style={{ fontSize: "1.35rem", fontWeight: 700, margin: 0 }}>Configure Accounts &amp; Relationships</h2>
            <p style={{ color: "var(--ink-muted)", margin: "6px 0 0 0", fontSize: "0.90rem", lineHeight: 1.45 }}>
              Confirm your accounts and map credit card settlement relationships to eliminate double-counting.
            </p>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 14, marginBottom: 24 }}>
            {accounts.map((acc, idx) => {
              const isCreditCard = acc.account_type === "credit_card";
              const bankOptions = accounts.filter((a, i) => i !== idx && a.account_type === "bank");

              return (
                <div
                  key={idx}
                  style={{
                    padding: "16px 18px",
                    background: "var(--surface)",
                    border: "1px solid var(--line)",
                    borderRadius: "var(--radius-md)",
                    display: "flex",
                    flexDirection: "column",
                    gap: 12,
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 10 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 10, flex: 1, minWidth: 200 }}>
                      <span style={{ fontSize: "1.3rem" }}>{isCreditCard ? "💳" : "🏦"}</span>
                      <input
                        type="text"
                        className="input"
                        value={acc.name}
                        onChange={(e) => {
                          const updated = [...accounts];
                          updated[idx].name = e.target.value;
                          setAccounts(updated);
                        }}
                        style={{ fontWeight: 600, fontSize: "0.92rem", padding: "6px 10px" }}
                      />
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <select
                        className="input"
                        value={acc.account_type}
                        onChange={(e) => {
                          const val = e.target.value as any;
                          const updated = [...accounts];
                          updated[idx].account_type = val;
                          updated[idx].is_asset = val !== "credit_card";
                          updated[idx].is_liability = val === "credit_card";
                          setAccounts(updated);
                        }}
                        style={{ padding: "6px 10px", fontSize: "0.82rem" }}
                      >
                        <option value="bank">Bank Account</option>
                        <option value="credit_card">Credit Card</option>
                        <option value="wallet">Wallet</option>
                        <option value="cash">Cash</option>
                      </select>
                      <button
                        type="button"
                        className="btn quiet"
                        onClick={() => {
                          setAccounts(accounts.filter((_, i) => i !== idx));
                        }}
                        style={{ color: "var(--danger)", padding: "4px 8px" }}
                        title="Remove Account"
                      >
                        ✕
                      </button>
                    </div>
                  </div>

                  {/* Relationship mapping for Credit Cards */}
                  {isCreditCard && bankOptions.length > 0 && (
                    <div style={{ padding: "10px 12px", background: "var(--surface-muted)", borderRadius: "var(--radius-sm)", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
                      <div style={{ fontSize: "0.80rem", color: "var(--ink-muted)" }}>
                        How do you pay this credit card bill?
                      </div>
                      <select
                        className="input"
                        value={acc.payment_account_id || ""}
                        onChange={(e) => {
                          const updated = [...accounts];
                          updated[idx].payment_account_id = e.target.value || null;
                          setAccounts(updated);
                        }}
                        style={{ padding: "4px 8px", fontSize: "0.80rem" }}
                      >
                        <option value="">(Select Payment Bank)</option>
                        {bankOptions.map((b) => (
                          <option key={b.name} value={b.name}>
                            Paid from {b.name}
                          </option>
                        ))}
                      </select>
                    </div>
                  )}
                </div>
              );
            })}

            <button
              type="button"
              className="btn quiet"
              onClick={() => {
                setAccounts([
                  ...accounts,
                  {
                    name: `Account ${accounts.length + 1}`,
                    account_type: "bank",
                    currency: currency,
                    is_asset: true,
                    is_liability: false,
                    opening_balance: 0,
                    auto_identify_bill_payments: true,
                  },
                ]);
              }}
              style={{ border: "1px dashed var(--line)", padding: "10px", textAlign: "center", borderRadius: "var(--radius-md)" }}
            >
              + Add Another Account
            </button>
          </div>

          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <button className="btn quiet" type="button" onClick={() => setStep(4)}>
              ← Back
            </button>
            <button
              className="btn primary"
              type="button"
              onClick={handleSaveAccounts}
              disabled={saving}
              style={{ padding: "10px 24px", fontWeight: 600 }}
            >
              {saving ? "Saving…" : "Continue to Historical Import →"}
            </button>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* STEP 6: HISTORICAL IMPORT & CALIBRATION COMPLETE */}
      {/* ========================================================================= */}
      {step === 6 && (
        <div className="surface" style={{ padding: "32px 28px", borderRadius: "var(--radius-lg)", border: "1px solid var(--line)" }}>
          {!calibrationDone ? (
            <div>
              <div style={{ marginBottom: 22 }}>
                <div style={{ fontSize: "1.8rem", marginBottom: 8 }}>⚡</div>
                <h2 style={{ fontSize: "1.35rem", fontWeight: 700, margin: 0 }}>Historical Import &amp; Calibration</h2>
                <p style={{ color: "var(--ink-muted)", margin: "6px 0 0 0", fontSize: "0.90rem", lineHeight: 1.45 }}>
                  Select how much financial history to ingest. More history gives MyMonee rich context for merchant rules and recurring obligations.
                </p>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 10, marginBottom: 24 }}>
                {[
                  { id: "3m", title: "Last 3 Months", desc: "Fastest setup" },
                  { id: "6m", title: "Last 6 Months", desc: "Recommended" },
                  { id: "1y", title: "Last 1 Year", desc: "Best for annual bills" },
                  { id: "2y", title: "Last 2 Years", desc: "Full archive" },
                ].map((item) => {
                  const isSelected = syncHorizon === item.id;
                  return (
                    <div
                      key={item.id}
                      onClick={() => setSyncHorizon(item.id as any)}
                      style={{
                        padding: "14px 16px",
                        border: `1.5px solid ${isSelected ? "var(--accent)" : "var(--line)"}`,
                        background: isSelected ? "var(--accent-soft)" : "var(--surface)",
                        borderRadius: "var(--radius-md)",
                        cursor: "pointer",
                        textAlign: "center",
                      }}
                    >
                      <div style={{ fontWeight: 600, fontSize: "0.90rem", color: isSelected ? "var(--accent)" : "var(--ink)" }}>
                        {item.title}
                      </div>
                      <div style={{ fontSize: "0.75rem", color: "var(--ink-muted)", marginTop: 2 }}>{item.desc}</div>
                    </div>
                  );
                })}
              </div>

              {isSyncing ? (
                <div style={{ padding: "30px 20px", background: "var(--surface-muted)", borderRadius: "var(--radius-md)", textAlign: "center", marginBottom: 20 }}>
                  <div className="spinner" style={{ width: 28, height: 28, margin: "0 auto 12px" }} />
                  <div style={{ fontWeight: 600, fontSize: "0.92rem" }}>Calibrating financial ledger…</div>
                  <div style={{ fontSize: "0.78rem", color: "var(--ink-muted)", marginTop: 4 }}>
                    Parsing alerts, reconciling transfers, and verifying double-entry equations.
                  </div>
                </div>
              ) : null}

              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <button className="btn quiet" type="button" onClick={() => setStep(5)} disabled={isSyncing}>
                  ← Back
                </button>
                <button
                  className="btn primary"
                  type="button"
                  onClick={handleStartImport}
                  disabled={isSyncing}
                  style={{ padding: "10px 24px", fontWeight: 600 }}
                >
                  {isSyncing ? "Calibrating…" : "Start Calibration & Launch →"}
                </button>
              </div>
            </div>
          ) : (
            /* Calibration Complete Bridge Screen */
            <div>
              <div style={{ textAlign: "center", marginBottom: 28 }}>
                <div style={{ fontSize: "3rem", marginBottom: 12 }}>🎉</div>
                <h2 style={{ fontSize: "1.6rem", fontWeight: 700, margin: 0 }}>You're Ready!</h2>
                <p style={{ color: "var(--ink-muted)", margin: "6px 0 0 0", fontSize: "0.95rem" }}>
                  MyMonee has established your local ledger and calibrated your financial workspace.
                </p>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12, marginBottom: 28 }}>
                <div style={{ padding: "16px", background: "var(--surface-muted)", border: "1px solid var(--line)", borderRadius: "var(--radius-md)", textAlign: "center" }}>
                  <div style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--accent)" }}>
                    {calibrationSummary.accounts_configured || accounts.length}
                  </div>
                  <div style={{ fontSize: "0.80rem", color: "var(--ink-muted)", marginTop: 2 }}>Accounts Configured</div>
                </div>

                <div style={{ padding: "16px", background: "var(--surface-muted)", border: "1px solid var(--line)", borderRadius: "var(--radius-md)", textAlign: "center" }}>
                  <div style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--ink)" }}>
                    {calibrationSummary.transactions_ingested}
                  </div>
                  <div style={{ fontSize: "0.80rem", color: "var(--ink-muted)", marginTop: 2 }}>Transactions Recorded</div>
                </div>

                <div style={{ padding: "16px", background: "var(--surface-muted)", border: "1px solid var(--line)", borderRadius: "var(--radius-md)", textAlign: "center" }}>
                  <div style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--credit, #2f6d4f)" }}>
                    {calibrationSummary.recurring_configured}
                  </div>
                  <div style={{ fontSize: "0.80rem", color: "var(--ink-muted)", marginTop: 2 }}>Recurring Obligations</div>
                </div>

                <div style={{ padding: "16px", background: "var(--surface-muted)", border: "1px solid var(--line)", borderRadius: "var(--radius-md)", textAlign: "center" }}>
                  <div style={{ fontSize: "1.5rem", fontWeight: 700, color: calibrationSummary.needs_review_count > 0 ? "var(--accent)" : "var(--ink-muted)" }}>
                    {calibrationSummary.needs_review_count}
                  </div>
                  <div style={{ fontSize: "0.80rem", color: "var(--ink-muted)", marginTop: 2 }}>Needs Review</div>
                </div>
              </div>

              <div style={{ display: "flex", justifyContent: "center", gap: 12, flexWrap: "wrap" }}>
                {calibrationSummary.needs_review_count > 0 ? (
                  <button
                    type="button"
                    className="btn primary"
                    onClick={() => navigate("/review")}
                    style={{ padding: "12px 28px", fontWeight: 600, fontSize: "0.95rem" }}
                  >
                    Review Transactions ({calibrationSummary.needs_review_count}) →
                  </button>
                ) : null}
                <button
                  type="button"
                  className={calibrationSummary.needs_review_count > 0 ? "btn quiet" : "btn primary"}
                  onClick={() => navigate("/")}
                  style={{ padding: "12px 28px", fontWeight: 600, fontSize: "0.95rem" }}
                >
                  Open Dashboard →
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
