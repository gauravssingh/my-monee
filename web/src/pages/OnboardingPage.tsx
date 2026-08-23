import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { formatMoney } from "../format";
import AccountBrandLogo from "../components/common/AccountBrandLogo";
import { getAccountBrandInfo } from "../utils/accountDisplay";

type DiscoveredData = {
  accounts: Array<{
    id: string;
    name: string;
    account_type: string;
    card_last4?: string | null;
    account_number_masked?: string | null;
    is_asset: boolean;
    is_liability: boolean;
  }>;
  income_sources: Array<{
    name: string;
    amount: number;
    currency: string;
    account?: string | null;
    last_date?: string | null;
    expected_day: number;
  }>;
  recurring: Array<{
    id?: string | null;
    name: string;
    expected_amount: number;
    frequency: string;
    expected_day: number;
    status: string;
  }>;
};

export default function OnboardingPage() {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [discovered, setDiscovered] = useState<DiscoveredData | null>(null);
  const [gmailConnected, setGmailConnected] = useState<boolean | null>(null);

  // Form State
  const [salaryName, setSalaryName] = useState("Salary");
  const [salaryAmount, setSalaryAmount] = useState<number>(0);
  const [salaryDay, setSalaryDay] = useState<number>(1);
  const [payCyclePreset, setPayCyclePreset] = useState<"end" | "first" | "custom">("first");
  const [selectedRecurring, setSelectedRecurring] = useState<Record<string, boolean>>({});

  // Auto-reconciliation options on step 5
  const [enableRefundPairing, setEnableRefundPairing] = useState(true);
  const [enableTransferMatching, setEnableTransferMatching] = useState(true);

  useEffect(() => {
    Promise.all([
      api.onboardingDiscover(),
      api.gmailStatus().catch(() => ({ connected: false })),
    ])
      .then(([disc, gStatus]) => {
        setDiscovered(disc);
        setGmailConnected(Boolean((gStatus as any)?.connected));

        if (disc.income_sources.length > 0) {
          const topIncome = disc.income_sources[0];
          setSalaryName(topIncome.name || "Primary Salary");
          setSalaryAmount(topIncome.amount || 0);
          const expDay = topIncome.expected_day || 1;
          setSalaryDay(expDay);
          if (expDay >= 28) setPayCyclePreset("end");
          else if (expDay === 1) setPayCyclePreset("first");
          else setPayCyclePreset("custom");
        }

        const initialRecMap: Record<string, boolean> = {};
        disc.recurring.forEach((r) => {
          initialRecMap[r.name] = true;
        });
        setSelectedRecurring(initialRecMap);
      })
      .catch((err) => {
        console.error("Failed to load onboarding discovery:", err);
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);

  const totalCommitted = useMemo(() => {
    if (!discovered) return 0;
    return discovered.recurring
      .filter((r) => selectedRecurring[r.name])
      .reduce((sum, r) => sum + (r.expected_amount || 0), 0);
  }, [discovered, selectedRecurring]);

  const freeCashFlow = Math.max(0, salaryAmount - totalCommitted);
  const savingsRate = salaryAmount > 0 ? Math.round((freeCashFlow / salaryAmount) * 100) : 0;

  const handlePayCyclePreset = (preset: "end" | "first" | "custom") => {
    setPayCyclePreset(preset);
    if (preset === "end") setSalaryDay(31);
    else if (preset === "first") setSalaryDay(1);
  };

  const handleComplete = async () => {
    setSaving(true);
    try {
      const activeRecurring = (discovered?.recurring || [])
        .filter((r) => selectedRecurring[r.name])
        .map((r) => ({
          name: r.name,
          expected_amount: r.expected_amount,
          frequency: r.frequency,
          expected_day: r.expected_day,
        }));

      await api.completeOnboarding({
        primary_salary: salaryAmount > 0 ? {
          name: salaryName,
          expected_amount: salaryAmount,
          frequency: "monthly",
        } : null,
        recurring_items: activeRecurring,
      });

      navigate("/");
    } catch (err) {
      console.error("Failed to complete onboarding:", err);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div style={{ minHeight: "80vh", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 12 }}>
        <div className="spinner" style={{ width: 32, height: 32, border: "3px solid var(--line)", borderTopColor: "var(--accent)", borderRadius: "50%" }} />
        <div style={{ color: "var(--ink-muted)", fontSize: "0.95rem" }}>Calibrating your financial workspace…</div>
      </div>
    );
  }

  const steps = [
    { num: 1, title: "Welcome & Sources", subtitle: "Privacy & Ingestion" },
    { num: 2, title: "Accounts & Cards", subtitle: "Assets & Liabilities" },
    { num: 3, title: "Income & Pay Cycle", subtitle: "Cash Inflow" },
    { num: 4, title: "Fixed Obligations", subtitle: "Bills & Subscriptions" },
    { num: 5, title: "Ready & Launch", subtitle: "Financial Blueprint" },
  ];

  const currentStepInfo = steps.find((s) => s.num === step) || steps[0];

  const assetAccounts = (discovered?.accounts || []).filter((a) => a.is_asset);
  const liabilityAccounts = (discovered?.accounts || []).filter((a) => a.is_liability);

  return (
    <div style={{ maxWidth: 840, margin: "16px auto 60px", padding: "0 16px min(40px, env(safe-area-inset-bottom, 40px))" }}>
      {/* Top Utility Bar with Exit Wizard Button */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 18 }}>
        <div style={{ fontSize: "0.85rem", color: "var(--ink-muted)", fontWeight: 600 }}>
          MyMonee Setup Wizard
        </div>
        <button
          type="button"
          onClick={() => navigate("/")}
          className="btn quiet"
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            fontSize: "0.82rem",
            color: "var(--ink-muted)",
            padding: "6px 10px",
            borderRadius: "var(--radius-sm)",
          }}
          title="Exit setup and return to dashboard"
        >
          <span style={{ fontSize: "1.1rem", lineHeight: 1 }}>✕</span>
          <span>Exit Wizard</span>
        </button>
      </div>

      {/* Sleek Connected Stepper Navigation */}
      <div style={{ marginBottom: 28 }}>
        {/* Desktop Stepper */}
        <div className="wizard-desktop-steps" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", position: "relative" }}>
          {/* Connecting Line Track */}
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
                transition: "width 0.3s cubic-bezier(0.16, 1, 0.3, 1)",
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
                  userSelect: "none",
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
                    fontSize: "0.90rem",
                    transition: "all 0.2s ease",
                    background: isCurrent
                      ? "var(--accent)"
                      : isCompleted
                      ? "var(--surface)"
                      : "var(--surface)",
                    color: isCurrent
                      ? "#fff"
                      : isCompleted
                      ? "var(--credit, #2f6d4f)"
                      : "var(--ink-muted)",
                    border: `2px solid ${isCurrent ? "var(--accent)" : isCompleted ? "var(--credit, #2f6d4f)" : "var(--line)"}`,
                    boxShadow: isCurrent ? "0 0 0 4px var(--accent-soft)" : "none",
                  }}
                >
                  {isCompleted ? "✓" : s.num}
                </div>
                <span
                  style={{
                    marginTop: 8,
                    fontSize: "0.82rem",
                    fontWeight: isCurrent ? 700 : 500,
                    color: isCurrent ? "var(--ink)" : "var(--ink-muted)",
                    textAlign: "center",
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
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: "0.86rem", fontWeight: 600, color: "var(--ink)", marginBottom: 8 }}>
            <span>Step {step} of 5</span>
            <span style={{ color: "var(--accent)" }}>{currentStepInfo.title}</span>
          </div>
          <div style={{ width: "100%", height: 6, background: "var(--surface-muted, rgba(0,0,0,0.06))", borderRadius: 3, overflow: "hidden" }}>
            <div
              style={{
                width: `${(step / 5) * 100}%`,
                height: "100%",
                background: "var(--accent)",
                borderRadius: 3,
                transition: "width 0.3s ease",
              }}
            />
          </div>
        </div>
      </div>

      {/* STEP 1: Welcome & Sources */}
      {step === 1 && (
        <div className="surface" style={{ padding: "28px 24px", borderRadius: "var(--radius-lg)", border: "1px solid var(--line)", boxShadow: "0 2px 8px rgba(0,0,0,0.04)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 20 }}>
            <img
              src="/logo.png"
              alt="MyMonee"
              style={{ width: 48, height: 48, borderRadius: 12, boxShadow: "0 2px 6px rgba(0,0,0,0.1)", flexShrink: 0 }}
            />
            <div>
              <h2 style={{ fontSize: "1.35rem", fontWeight: 700, margin: 0 }}>
                Welcome to MyMonee
              </h2>
              <p style={{ color: "var(--ink-muted)", margin: "4px 0 0 0", fontSize: "0.90rem" }}>
                Your private, local-first double-entry financial assistant.
              </p>
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12, margin: "20px 0" }}>
            <div style={{ padding: "14px 16px", background: "var(--surface-muted)", border: "1px solid var(--line)", borderRadius: "var(--radius-md)" }}>
              <div style={{ fontSize: "1.2rem", marginBottom: 4 }}>🔒</div>
              <div style={{ fontWeight: 600, fontSize: "0.90rem", marginBottom: 2 }}>100% Local-First</div>
              <div style={{ fontSize: "0.80rem", color: "var(--ink-muted)", lineHeight: 1.4 }}>
                SQLite ledger stored directly on your Mac. No cloud database, zero telemetry.
              </div>
            </div>

            <div style={{ padding: "14px 16px", background: "var(--surface-muted)", border: "1px solid var(--line)", borderRadius: "var(--radius-md)" }}>
              <div style={{ fontSize: "1.2rem", marginBottom: 4 }}>⚡</div>
              <div style={{ fontWeight: 600, fontSize: "0.90rem", marginBottom: 2 }}>Learns From You</div>
              <div style={{ fontSize: "0.80rem", color: "var(--ink-muted)", lineHeight: 1.4 }}>
                Categorize once in Needs Review and MyMonee persists deterministic rules forever.
              </div>
            </div>

            <div style={{ padding: "14px 16px", background: "var(--surface-muted)", border: "1px solid var(--line)", borderRadius: "var(--radius-md)" }}>
              <div style={{ fontSize: "1.2rem", marginBottom: 4 }}>⚖️</div>
              <div style={{ fontWeight: 600, fontSize: "0.90rem", marginBottom: 2 }}>Reconciliation Truth</div>
              <div style={{ fontSize: "0.80rem", color: "var(--ink-muted)", lineHeight: 1.4 }}>
                Pairs refunds and cross-account card payments to prevent double-counting.
              </div>
            </div>
          </div>

          {/* Sources Status Card with clean header placement for Connected pill */}
          <div style={{ padding: "16px 18px", background: "var(--surface)", border: "1px solid var(--line)", borderRadius: "var(--radius-md)", marginBottom: 24 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
              <div style={{ fontSize: "11px", color: "var(--ink-muted)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em" }}>
                Evidence Sources Status
              </div>
              <span className={`badge ${gmailConnected ? "ok" : "muted"}`} style={{ fontSize: "0.78rem", padding: "3px 8px", fontWeight: 600, whiteSpace: "nowrap", flexShrink: 0, display: "inline-flex", alignItems: "center", gap: 4 }}>
                {gmailConnected ? "✓ Connected" : "Ready"}
              </span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <span style={{ fontSize: "1.4rem", flexShrink: 0 }}>✉️</span>
              <div>
                <div style={{ fontWeight: 600, fontSize: "0.92rem" }}>Gmail Notification Emails</div>
                <div style={{ fontSize: "0.80rem", color: "var(--ink-muted)", marginTop: 2, lineHeight: 1.35 }}>
                  {gmailConnected
                    ? "OAuth connection verified · Ready to ingest debit/credit alerts"
                    : "Local connection ready"}
                </div>
              </div>
            </div>
          </div>

          <div className="wizard-footer-nav" style={{ justifyContent: "flex-end" }}>
            <button
              className="btn primary"
              type="button"
              onClick={() => setStep(2)}
              style={{ height: 42, padding: "0 24px", fontSize: "0.92rem", fontWeight: 600, width: "100%", maxWidth: 280 }}
            >
              Get Started: Review Accounts →
            </button>
          </div>
        </div>
      )}

      {/* STEP 2: Accounts & Cards Discovery */}
      {step === 2 && (
        <div className="surface" style={{ padding: "28px 24px", borderRadius: "var(--radius-lg)", border: "1px solid var(--line)", boxShadow: "0 2px 8px rgba(0,0,0,0.04)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
            <div>
              <h2 style={{ fontSize: "1.3rem", fontWeight: 700, margin: 0 }}>
                Discovered Accounts &amp; Cards
              </h2>
              <p style={{ color: "var(--ink-muted)", margin: "4px 0 0 0", fontSize: "0.88rem" }}>
                Review detected financial accounts. Full names and masked account identifiers are shown.
              </p>
            </div>
            <span className="badge muted" style={{ fontSize: "0.82rem", padding: "4px 10px", flexShrink: 0 }}>
              {discovered?.accounts.length || 0} Accounts Total
            </span>
          </div>

          {/* Group 1: Bank, Cash & Wallets */}
          <div style={{ marginTop: 20 }}>
            <div style={{ fontSize: "11px", color: "var(--ink-muted)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 10, display: "flex", alignItems: "center", gap: 6 }}>
              <span>🏦</span>
              <span>Bank, Cash &amp; Wallets ({assetAccounts.length})</span>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 10 }}>
              {assetAccounts.map((acc) => {
                const { brand } = getAccountBrandInfo(acc.name, acc.account_type, acc.card_last4, acc.account_number_masked);
                return (
                  <div
                    key={acc.id}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 12,
                      padding: "12px 14px",
                      background: "var(--surface)",
                      border: "1px solid var(--line)",
                      borderRadius: "var(--radius-md)",
                    }}
                  >
                    <AccountBrandLogo brand={brand} size={30} />
                    <div style={{ minWidth: 0, flex: "1 1 auto" }}>
                      <div style={{ fontWeight: 600, fontSize: "0.92rem", color: "var(--ink)", wordBreak: "break-word" }}>
                        {acc.name}
                      </div>
                      <div style={{ fontSize: "0.78rem", color: "var(--ink-muted)", marginTop: 2 }}>
                        {acc.account_number_masked ? `Acct ${acc.account_number_masked}` : acc.account_type}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Group 2: Credit Cards & Lines */}
          <div style={{ marginTop: 24 }}>
            <div style={{ fontSize: "11px", color: "var(--ink-muted)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 10, display: "flex", alignItems: "center", gap: 6 }}>
              <span>💳</span>
              <span>Credit Cards &amp; Lines ({liabilityAccounts.length})</span>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 10 }}>
              {liabilityAccounts.map((acc) => {
                const { brand } = getAccountBrandInfo(acc.name, acc.account_type, acc.card_last4, acc.account_number_masked);
                return (
                  <div
                    key={acc.id}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 12,
                      padding: "12px 14px",
                      background: "var(--surface)",
                      border: "1px solid var(--line)",
                      borderRadius: "var(--radius-md)",
                    }}
                  >
                    <AccountBrandLogo brand={brand} size={30} />
                    <div style={{ minWidth: 0, flex: "1 1 auto" }}>
                      <div style={{ fontWeight: 600, fontSize: "0.92rem", color: "var(--ink)", wordBreak: "break-word" }}>
                        {acc.name}
                      </div>
                      <div style={{ fontSize: "0.78rem", color: "var(--ink-muted)", marginTop: 2 }}>
                        {acc.card_last4 ? `Card ending in ${acc.card_last4}` : "Credit Card"}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="wizard-footer-nav">
            <button className="btn quiet" type="button" onClick={() => setStep(1)} style={{ height: 42, padding: "0 16px", flexShrink: 0 }}>
              ← Back
            </button>
            <button
              className="btn primary"
              type="button"
              onClick={() => setStep(3)}
              style={{ height: 42, padding: "0 18px", fontWeight: 600, fontSize: "0.90rem", flex: "1 1 auto", display: "inline-flex", alignItems: "center", justifyContent: "center", whiteSpace: "nowrap" }}
            >
              <span>Continue</span>
              <span className="hide-mobile">: Income &amp; Salary</span>
              <span> →</span>
            </button>
          </div>
        </div>
      )}

      {/* STEP 3: Income & Pay Cycle Setup */}
      {step === 3 && (
        <div className="surface" style={{ padding: "28px 24px", borderRadius: "var(--radius-lg)", border: "1px solid var(--line)", boxShadow: "0 2px 8px rgba(0,0,0,0.04)" }}>
          <h2 style={{ fontSize: "1.3rem", fontWeight: 700, margin: 0 }}>
            Income &amp; Pay-Cycle Attribution
          </h2>
          <p style={{ color: "var(--ink-muted)", margin: "4px 0 20px 0", fontSize: "0.88rem" }}>
            Configure your monthly salary baseline to accurately measure discretionary spending and savings rates.
          </p>

          {/* Discovered Salary Prompt */}
          {discovered && discovered.income_sources.length > 0 && (
            <div style={{ padding: "14px 16px", background: "rgba(47, 109, 79, 0.06)", border: "1px solid var(--credit, #2f6d4f)", borderRadius: "var(--radius-md)", marginBottom: 22, display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 10 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span style={{ fontSize: "1.3rem" }}>💰</span>
                <div>
                  <div style={{ fontWeight: 600, fontSize: "0.92rem", color: "var(--ink)" }}>
                    Discovered Deposit: {discovered.income_sources[0].name}
                  </div>
                  <div style={{ fontSize: "0.80rem", color: "var(--ink-muted)" }}>
                    {formatMoney(discovered.income_sources[0].amount)} received around day {discovered.income_sources[0].expected_day}
                  </div>
                </div>
              </div>
              <button
                type="button"
                className="btn quiet"
                onClick={() => {
                  setSalaryName(discovered.income_sources[0].name);
                  setSalaryAmount(discovered.income_sources[0].amount);
                  setSalaryDay(discovered.income_sources[0].expected_day);
                }}
                style={{ fontSize: "0.82rem", fontWeight: 600, color: "var(--credit, #2f6d4f)" }}
              >
                Use Discovered Values
              </button>
            </div>
          )}

          <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
            <div>
              <label style={{ display: "block", fontSize: "0.84rem", fontWeight: 600, marginBottom: 6 }}>
                Primary Income / Employer Name
              </label>
              <input
                type="text"
                className="input"
                value={salaryName}
                onChange={(e) => setSalaryName(e.target.value)}
                style={{ width: "100%", padding: "10px 14px", fontSize: "0.95rem", boxSizing: "border-box" }}
              />
            </div>

            <div>
              <label style={{ display: "block", fontSize: "0.84rem", fontWeight: 600, marginBottom: 6 }}>
                Expected Monthly Take-Home (₹)
              </label>
              <div style={{ position: "relative" }}>
                <span style={{ position: "absolute", left: 14, top: 12, fontWeight: 700, color: "var(--ink-muted)", fontSize: "1.05rem" }}>₹</span>
                <input
                  type="number"
                  className="input"
                  value={salaryAmount || ""}
                  onChange={(e) => setSalaryAmount(parseFloat(e.target.value) || 0)}
                  placeholder="e.g. 280000"
                  style={{ width: "100%", padding: "10px 14px 10px 32px", fontSize: "1.15rem", fontWeight: 700, fontFamily: "var(--font-mono, monospace)", boxSizing: "border-box" }}
                />
              </div>
              {salaryAmount > 0 && (
                <div style={{ fontSize: "0.80rem", color: "var(--ink-muted)", marginTop: 4 }}>
                  Annualized Estimate: ≈ {formatMoney(salaryAmount * 12)} / year
                </div>
              )}
            </div>

            {/* Pay Cycle Presets */}
            <div>
              <label style={{ display: "block", fontSize: "0.84rem", fontWeight: 600, marginBottom: 8 }}>
                Expected Payday Cycle
              </label>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 10 }}>
                <div
                  onClick={() => handlePayCyclePreset("first")}
                  style={{
                    padding: "12px",
                    border: `1.5px solid ${payCyclePreset === "first" ? "var(--accent)" : "var(--line)"}`,
                    background: payCyclePreset === "first" ? "var(--accent-soft)" : "var(--surface)",
                    borderRadius: "var(--radius-md)",
                    cursor: "pointer",
                    textAlign: "center",
                  }}
                >
                  <div style={{ fontWeight: 600, fontSize: "0.90rem" }}>1st of Month</div>
                  <div style={{ fontSize: "0.78rem", color: "var(--ink-muted)", marginTop: 2 }}>Start of Calendar Month</div>
                </div>

                <div
                  onClick={() => handlePayCyclePreset("end")}
                  style={{
                    padding: "12px",
                    border: `1.5px solid ${payCyclePreset === "end" ? "var(--accent)" : "var(--line)"}`,
                    background: payCyclePreset === "end" ? "var(--accent-soft)" : "var(--surface)",
                    borderRadius: "var(--radius-md)",
                    cursor: "pointer",
                    textAlign: "center",
                  }}
                >
                  <div style={{ fontWeight: 600, fontSize: "0.90rem" }}>End of Month</div>
                  <div style={{ fontSize: "0.78rem", color: "var(--ink-muted)", marginTop: 2 }}>Last Day (30th/31st)</div>
                </div>

                <div
                  onClick={() => handlePayCyclePreset("custom")}
                  style={{
                    padding: "12px",
                    border: `1.5px solid ${payCyclePreset === "custom" ? "var(--accent)" : "var(--line)"}`,
                    background: payCyclePreset === "custom" ? "var(--accent-soft)" : "var(--surface)",
                    borderRadius: "var(--radius-md)",
                    cursor: "pointer",
                    textAlign: "center",
                  }}
                >
                  <div style={{ fontWeight: 600, fontSize: "0.90rem" }}>Custom Day</div>
                  <div style={{ fontSize: "0.78rem", color: "var(--ink-muted)", marginTop: 2 }}>Specific Day ({salaryDay})</div>
                </div>
              </div>

              {payCyclePreset === "custom" && (
                <div style={{ marginTop: 12 }}>
                  <label style={{ display: "block", fontSize: "0.80rem", color: "var(--ink-muted)", marginBottom: 4 }}>
                    Day of month (1 to 31)
                  </label>
                  <input
                    type="number"
                    min={1}
                    max={31}
                    className="input"
                    value={salaryDay}
                    onChange={(e) => setSalaryDay(parseInt(e.target.value) || 1)}
                    style={{ width: 140, padding: "8px 12px" }}
                  />
                </div>
              )}
            </div>
          </div>

          <div className="wizard-footer-nav">
            <button className="btn quiet" type="button" onClick={() => setStep(2)} style={{ height: 42, padding: "0 16px", flexShrink: 0 }}>
              ← Back
            </button>
            <button
              className="btn primary"
              type="button"
              onClick={() => setStep(4)}
              style={{ height: 42, padding: "0 18px", fontWeight: 600, fontSize: "0.90rem", flex: "1 1 auto", display: "inline-flex", alignItems: "center", justifyContent: "center", whiteSpace: "nowrap" }}
            >
              <span>Continue</span>
              <span className="hide-mobile">: Fixed Obligations</span>
              <span> →</span>
            </button>
          </div>
        </div>
      )}

      {/* STEP 4: Fixed Obligations & Subscriptions */}
      {step === 4 && (
        <div className="surface" style={{ padding: "28px 24px", borderRadius: "var(--radius-lg)", border: "1px solid var(--line)", boxShadow: "0 2px 8px rgba(0,0,0,0.04)" }}>
          <div style={{ marginBottom: 18 }}>
            <h2 style={{ fontSize: "1.3rem", fontWeight: 700, margin: 0 }}>
              Fixed Bills &amp; Subscriptions
            </h2>
            <p style={{ color: "var(--ink-muted)", margin: "4px 0 0 0", fontSize: "0.88rem" }}>
              Select recurring obligations to track committed monthly outflows automatically.
            </p>
          </div>

          {/* Dedicated Prominent Total Committed Callout Card */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "14px 18px",
              background: "var(--surface-muted)",
              border: "1px solid var(--line)",
              borderRadius: "var(--radius-md)",
              marginBottom: 20,
              flexWrap: "wrap",
              gap: 10,
            }}
          >
            <div>
              <div style={{ fontSize: "11px", color: "var(--ink-muted)", textTransform: "uppercase", fontWeight: 600, letterSpacing: "0.05em" }}>
                Total Committed Monthly Outflow
              </div>
              <div style={{ fontSize: "0.80rem", color: "var(--ink-muted)", marginTop: 2 }}>
                {Object.values(selectedRecurring).filter(Boolean).length} of {discovered?.recurring.length || 0} obligations selected
              </div>
            </div>
            <div style={{ fontSize: "1.35rem", fontWeight: 700, color: "var(--debit, #a5333b)", fontFamily: "var(--font-mono, monospace)" }}>
              {formatMoney(totalCommitted)} / mo
            </div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {discovered?.recurring.map((rec) => {
              const active = selectedRecurring[rec.name] ?? false;
              const isLoan = rec.name.toLowerCase().includes("loan") || rec.name.toLowerCase().includes("emi");
              const isMaintenance = rec.name.toLowerCase().includes("maintenance") || rec.name.toLowerCase().includes("rent");

              return (
                <label
                  key={rec.name}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    padding: "14px 16px",
                    background: active ? "var(--surface)" : "var(--surface-muted, rgba(0,0,0,0.01))",
                    border: `1.5px solid ${active ? "var(--accent)" : "var(--line)"}`,
                    borderRadius: "var(--radius-md)",
                    cursor: "pointer",
                    transition: "all 0.15s ease",
                    boxShadow: active ? "0 1px 4px rgba(75, 46, 88, 0.08)" : "none",
                    gap: 12,
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 0, flex: "1 1 auto" }}>
                    <input
                      type="checkbox"
                      checked={active}
                      onChange={(e) => {
                        setSelectedRecurring((prev) => ({ ...prev, [rec.name]: e.target.checked }));
                      }}
                      style={{ accentColor: "var(--accent)", width: 18, height: 18, flexShrink: 0 }}
                    />
                    <div style={{ minWidth: 0, flex: "1 1 auto" }}>
                      <div style={{ fontWeight: 600, fontSize: "0.92rem", color: "var(--ink)", wordBreak: "break-word" }}>
                        {rec.name}
                      </div>
                      <div style={{ fontSize: "0.78rem", color: "var(--ink-muted)", marginTop: 2, display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                        <span>{rec.frequency} · Due on day {rec.expected_day}</span>
                        <span className="badge muted" style={{ fontSize: "0.68rem", padding: "2px 6px" }}>
                          {isLoan ? "Loan / EMI" : isMaintenance ? "Living / Housing" : "Subscription"}
                        </span>
                      </div>
                    </div>
                  </div>
                  <span style={{ fontWeight: 700, fontFamily: "var(--font-mono, monospace)", fontSize: "0.95rem", color: "var(--ink)", flexShrink: 0, marginLeft: 8 }}>
                    {formatMoney(rec.expected_amount)}
                  </span>
                </label>
              );
            })}
          </div>

          <div className="wizard-footer-nav">
            <button className="btn quiet" type="button" onClick={() => setStep(3)} style={{ height: 42, padding: "0 16px", flexShrink: 0 }}>
              ← Back
            </button>
            <button
              className="btn primary"
              type="button"
              onClick={() => setStep(5)}
              style={{ height: 42, padding: "0 18px", fontWeight: 600, fontSize: "0.90rem", flex: "1 1 auto", display: "inline-flex", alignItems: "center", justifyContent: "center", whiteSpace: "nowrap" }}
            >
              <span>Continue</span>
              <span className="hide-mobile">: Review Blueprint</span>
              <span> →</span>
            </button>
          </div>
        </div>
      )}

      {/* STEP 5: Ready & Launch (Financial Blueprint) */}
      {step === 5 && (
        <div className="surface" style={{ padding: "28px 24px", borderRadius: "var(--radius-lg)", border: "1px solid var(--line)", boxShadow: "0 2px 8px rgba(0,0,0,0.04)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 18 }}>
            <span style={{ fontSize: "2rem", flexShrink: 0 }}>🚀</span>
            <div>
              <h2 style={{ fontSize: "1.35rem", fontWeight: 700, margin: 0 }}>
                Financial Blueprint Calibrated
              </h2>
              <p style={{ color: "var(--ink-muted)", margin: "4px 0 0 0", fontSize: "0.88rem" }}>
                Here is your monthly cash flow model and ledger configuration summary.
              </p>
            </div>
          </div>

          {/* 3 KPI Cashflow Cards */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 14, margin: "20px 0" }}>
            <div style={{ padding: "16px 18px", background: "var(--surface)", border: "1px solid var(--line)", borderRadius: "var(--radius-md)" }}>
              <div style={{ fontSize: "11px", color: "var(--ink-muted)", textTransform: "uppercase", fontWeight: 600 }}>Expected Inflow</div>
              <div style={{ fontSize: "1.45rem", fontWeight: 700, marginTop: 4, color: "var(--credit, #2f6d4f)", fontFamily: "var(--font-mono, monospace)" }}>
                +{formatMoney(salaryAmount)}
              </div>
              <div style={{ fontSize: "0.78rem", color: "var(--ink-muted)", marginTop: 2 }}>{salaryName}</div>
            </div>

            <div style={{ padding: "16px 18px", background: "var(--surface)", border: "1px solid var(--line)", borderRadius: "var(--radius-md)" }}>
              <div style={{ fontSize: "11px", color: "var(--ink-muted)", textTransform: "uppercase", fontWeight: 600 }}>Fixed Commitments</div>
              <div style={{ fontSize: "1.45rem", fontWeight: 700, marginTop: 4, color: "var(--debit, #a5333b)", fontFamily: "var(--font-mono, monospace)" }}>
                −{formatMoney(totalCommitted)}
              </div>
              <div style={{ fontSize: "0.78rem", color: "var(--ink-muted)", marginTop: 2 }}>
                {Object.values(selectedRecurring).filter(Boolean).length} tracked obligations
              </div>
            </div>

            <div style={{ padding: "16px 18px", background: "var(--surface)", border: "1px solid var(--line)", borderRadius: "var(--radius-md)" }}>
              <div style={{ fontSize: "11px", color: "var(--ink-muted)", textTransform: "uppercase", fontWeight: 600 }}>Free Cash Flow</div>
              <div style={{ fontSize: "1.45rem", fontWeight: 700, marginTop: 4, color: "var(--info, #2d5b88)", fontFamily: "var(--font-mono, monospace)" }}>
                {formatMoney(freeCashFlow)}
              </div>
              <div style={{ fontSize: "0.78rem", color: "var(--credit, #2f6d4f)", marginTop: 2, fontWeight: 600 }}>
                {savingsRate}% discretionary / savings potential
              </div>
            </div>
          </div>

          {/* Engine Calibration Checklist with Rich Readability & Explanations */}
          <div style={{ padding: "18px 20px", background: "var(--surface-muted)", border: "1px solid var(--line)", borderRadius: "var(--radius-md)", marginBottom: 28 }}>
            <div style={{ fontSize: "11px", color: "var(--ink-muted)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 14 }}>
              Ledger Intelligence Engines
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <label
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  gap: 14,
                  padding: "14px 16px",
                  background: enableRefundPairing ? "var(--surface)" : "transparent",
                  border: `1.5px solid ${enableRefundPairing ? "var(--accent)" : "var(--line)"}`,
                  borderRadius: "var(--radius-md)",
                  cursor: "pointer",
                  transition: "all 0.15s ease",
                }}
              >
                <input
                  type="checkbox"
                  checked={enableRefundPairing}
                  onChange={(e) => setEnableRefundPairing(e.target.checked)}
                  style={{ accentColor: "var(--accent)", width: 18, height: 18, marginTop: 2, flexShrink: 0 }}
                />
                <div>
                  <div style={{ fontWeight: 600, fontSize: "0.94rem", color: "var(--ink)" }}>
                    Refund &amp; Reversal Pairing
                  </div>
                  <div style={{ fontSize: "0.84rem", color: "var(--ink-muted)", marginTop: 2, lineHeight: 1.4 }}>
                    Automatically link merchant credit refunds directly to original debit transactions, ensuring gross spending and income are not artificially inflated.
                  </div>
                </div>
              </label>

              <label
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  gap: 14,
                  padding: "14px 16px",
                  background: enableTransferMatching ? "var(--surface)" : "transparent",
                  border: `1.5px solid ${enableTransferMatching ? "var(--accent)" : "var(--line)"}`,
                  borderRadius: "var(--radius-md)",
                  cursor: "pointer",
                  transition: "all 0.15s ease",
                }}
              >
                <input
                  type="checkbox"
                  checked={enableTransferMatching}
                  onChange={(e) => setEnableTransferMatching(e.target.checked)}
                  style={{ accentColor: "var(--accent)", width: 18, height: 18, marginTop: 2, flexShrink: 0 }}
                />
                <div>
                  <div style={{ fontWeight: 600, fontSize: "0.94rem", color: "var(--ink)" }}>
                    Cross-Account &amp; Credit Card Transfer Matching
                  </div>
                  <div style={{ fontSize: "0.84rem", color: "var(--ink-muted)", marginTop: 2, lineHeight: 1.4 }}>
                    Match bank account bill payments with credit card ledger settlements so debt payments are categorized as transfers rather than duplicate expenses.
                  </div>
                </div>
              </label>
            </div>
          </div>

          <div className="wizard-footer-nav">
            <button className="btn quiet" type="button" onClick={() => setStep(4)} disabled={saving} style={{ height: 42, padding: "0 16px", flexShrink: 0 }}>
              ← Back
            </button>
            <button
              className="btn primary"
              type="button"
              disabled={saving}
              onClick={() => void handleComplete()}
              style={{
                height: 44,
                padding: "0 18px",
                fontWeight: 700,
                fontSize: "0.92rem",
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 6,
                flex: "1 1 auto",
                boxShadow: "0 2px 8px var(--accent-soft)",
                whiteSpace: "nowrap",
              }}
            >
              <span>{saving ? "Calibrating…" : (
                <>
                  <span>Complete Setup</span>
                  <span className="hide-mobile"> &amp; Launch Dashboard</span>
                  <span> →</span>
                </>
              )}</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
