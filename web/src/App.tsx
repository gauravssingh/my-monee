import { Component, lazy, Suspense, useEffect, useState, type ErrorInfo, type ReactNode } from "react";
import { Navigate, NavLink, Route, Routes } from "react-router-dom";
import LockScreen from "./components/LockScreen";
import { api } from "./api";
import { useToast } from "./hooks/useToast";

const OverviewPage = lazy(() => import("./pages/OverviewPage"));
const TransactionsPage = lazy(() => import("./pages/TransactionsPage"));
const CategoryAnalyticsPage = lazy(() => import("./pages/CategoryAnalyticsPage"));
const RecurringPage = lazy(() => import("./pages/RecurringPage"));
const MerchantsPage = lazy(() => import("./pages/MerchantsPage"));
const DataIssuesPage = lazy(() => import("./pages/DataIssuesPage"));
const AccountsPage = lazy(() => import("./pages/AccountsPage"));
const CreditCardStatementsPage = lazy(() => import("./pages/CreditCardStatementsPage"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));
const OnboardingPage = lazy(() => import("./pages/OnboardingPage"));

class ErrorBoundary extends Component<{ children: ReactNode }, { hasError: boolean; error: Error | null }> {
  constructor(props: { children: ReactNode }) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("Uncaught render error:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: "40px 24px", maxWidth: "600px", margin: "0 auto", textAlign: "center" }}>
          <h2 style={{ color: "var(--danger)" }}>Something went wrong loading this view.</h2>
          <p style={{ color: "var(--ink-muted)", marginTop: "8px", fontSize: "0.9rem" }}>
            {this.state.error?.message || "An unexpected rendering error occurred."}
          </p>
          <button
            className="btn primary"
            style={{ marginTop: "16px" }}
            onClick={() => window.location.reload()}
          >
            Reload Page
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

interface SyncNavButtonProps {
  syncing: boolean;
  onSync: () => void;
  className?: string;
}

function SyncNavButton({ syncing, onSync, className = "" }: SyncNavButtonProps) {
  return (
    <button
      type="button"
      className={`topbar-sync-btn ${className}`.trim()}
      title="Incremental Sync"
      aria-label="Incremental Sync"
      disabled={syncing}
      onClick={onSync}
    >
      <svg
        xmlns="http://www.w3.org/2000/svg"
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
        className={syncing ? "spin" : ""}
        style={{ transformOrigin: "center" }}
      >
        <polyline points="23 4 23 10 17 10" />
        <polyline points="1 20 1 14 7 14" />
        <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
      </svg>
    </button>
  );
}

export default function App() {
  const { showToast } = useToast();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [authLoading, setAuthLoading] = useState(true);
  const [authConfigured, setAuthConfigured] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);
  const [syncing, setSyncing] = useState(false);

  const handleIncrementalSync = async () => {
    if (syncing) return;
    setSyncing(true);
    try {
      const result = await api.gmailSync({ fullYear: false, maxMessages: 2000 });
      if (result.status === "error") {
        showToast(result.error_summary || "Sync encountered errors", "error");
      } else if (result.emails_discovered === 0 && result.transactions_extracted === 0) {
        showToast("Sync complete: No new transaction emails found", "success");
      } else {
        const extractedMsg = `${result.transactions_extracted} new transaction${result.transactions_extracted === 1 ? "" : "s"}`;
        showToast(
          `Sync complete: ${extractedMsg} (${result.emails_discovered} scanned, ${result.transactions_duplicated} duplicates)`,
          "success"
        );
      }
      window.dispatchEvent(new CustomEvent("mymonee:sync-completed", { detail: result }));
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Sync failed", "error");
    } finally {
      setSyncing(false);
    }
  };

  useEffect(() => {
    api.authStatus()
      .then((res) => {
        setAuthConfigured(res.configured);
        setAuthenticated(res.authenticated);
      })
      .catch((err) => {
        console.error("Failed to check auth status:", err);
        // Default to authenticated if auth api unavailable
        setAuthenticated(true);
      })
      .finally(() => {
        setAuthLoading(false);
      });
  }, []);

  const handleLogout = async () => {
    try {
      await api.authLogout();
    } catch {
      // ignore
    }
    localStorage.removeItem("mymonee_auth_token");
    setAuthenticated(false);
  };

  if (authLoading) {
    return (
      <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "var(--bg)" }}>
        <div style={{ color: "var(--ink-muted)", fontSize: "0.9rem" }}>Loading MyMonee…</div>
      </div>
    );
  }

  if (!authenticated) {
    return (
      <LockScreen
        configured={authConfigured}
        onAuthenticated={() => {
          setAuthConfigured(true);
          setAuthenticated(true);
        }}
      />
    );
  }

  return (
    <div className="app-layout">
      {/* Desktop Persistent Navigation Rail */}
      <aside className="app-sidebar" aria-label="Main Navigation">
        <div className="sidebar-header">
          <NavLink to="/" className="sidebar-brand">
            <img
              src="/logo.png"
              alt="MyMonee Logo"
              className="sidebar-brand-logo"
            />
            <div className="sidebar-brand-text">
              <div className="sidebar-brand-title">MyMonee</div>
              <span className="sidebar-brand-tagline">.. my finances</span>
            </div>
          </NavLink>
        </div>

        <nav className="sidebar-nav">
          <div className="sidebar-section-title">Workspace</div>
          <NavLink to="/" end className="sidebar-nav-item">
            <svg className="sidebar-nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <rect width="7" height="9" x="3" y="3" rx="1" />
              <rect width="7" height="5" x="14" y="3" rx="1" />
              <rect width="7" height="9" x="14" y="12" rx="1" />
              <rect width="7" height="5" x="3" y="16" rx="1" />
            </svg>
            <span>Overview</span>
          </NavLink>
          <NavLink to="/transactions" className="sidebar-nav-item">
            <svg className="sidebar-nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1V2l-2 1-2-1-2 1-2-1-2 1-2-1-2 1-2-1-2 1Z" />
              <line x1="8" y1="8" x2="16" y2="8" />
              <line x1="8" y1="12" x2="16" y2="12" />
              <line x1="8" y1="16" x2="12" y2="16" />
            </svg>
            <span>Classified</span>
          </NavLink>
          <NavLink to="/review" className="sidebar-nav-item">
            <svg className="sidebar-nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
              <line x1="12" y1="9" x2="12" y2="13" />
              <line x1="12" y1="17" x2="12.01" y2="17" />
            </svg>
            <span>Needs Review</span>
          </NavLink>
          <NavLink to="/data-issues" className="sidebar-nav-item">
            <svg className="sidebar-nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z" />
              <line x1="4" y1="22" x2="4" y2="15" />
            </svg>
            <span>Data Issues</span>
          </NavLink>

          <div className="sidebar-section-title">Analysis</div>
          <NavLink to="/categories" className="sidebar-nav-item">
            <svg className="sidebar-nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M21.21 15.89A10 10 0 1 1 8 2.83" />
              <path d="M22 12A10 10 0 0 0 12 2v10z" />
            </svg>
            <span>Categories Deep Dive</span>
          </NavLink>
          <NavLink to="/recurring" className="sidebar-nav-item">
            <svg className="sidebar-nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="m17 2 4 4-4 4" />
              <path d="M3 11v-1a4 4 0 0 1 4-4h14" />
              <path d="m7 22-4-4 4-4" />
              <path d="M21 13v1a4 4 0 0 1-4 4H3" />
            </svg>
            <span>Recurring &amp; Subs</span>
          </NavLink>

          <div className="sidebar-section-title">Management</div>
          <NavLink to="/accounts" className="sidebar-nav-item">
            <svg className="sidebar-nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <rect width="20" height="14" x="2" y="5" rx="2" />
              <line x1="2" y1="10" x2="22" y2="10" />
            </svg>
            <span>Accounts</span>
          </NavLink>
          <NavLink to="/merchants" className="sidebar-nav-item">
            <svg className="sidebar-nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="m2 7 4.41-4.41A2 2 0 0 1 7.83 2h8.34a2 2 0 0 1 1.42.59L22 7" />
              <path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8" />
              <path d="M15 22v-4a2 2 0 0 0-2-2h-2a2 2 0 0 0-2 2v4" />
              <path d="M2 7h20" />
            </svg>
            <span>Merchants</span>
          </NavLink>
          <NavLink to="/settings" className="sidebar-nav-item">
            <svg className="sidebar-nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" />
              <circle cx="12" cy="12" r="3" />
            </svg>
            <span>Settings</span>
          </NavLink>
        </nav>

        <div className="sidebar-footer">
          <button
            type="button"
            className="sidebar-action-btn"
            disabled={syncing}
            onClick={() => void handleIncrementalSync()}
            title="Incremental Gmail Sync"
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
              className={`sidebar-nav-icon ${syncing ? "spin" : ""}`}
              aria-hidden="true"
            >
              <polyline points="23 4 23 10 17 10" />
              <polyline points="1 20 1 14 7 14" />
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
            </svg>
            <span>{syncing ? "Syncing Gmail…" : "Sync Gmail"}</span>
          </button>
          {authConfigured && (
            <button
              type="button"
              className="sidebar-action-btn danger-action"
              onClick={() => void handleLogout()}
              title="Lock Current Session"
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
                className="sidebar-nav-icon"
                aria-hidden="true"
              >
                <rect width="18" height="11" x="3" y="11" rx="2" ry="2" />
                <path d="M7 11V7a5 5 0 0 1 10 0v4" />
              </svg>
              <span>Lock Session</span>
            </button>
          )}
        </div>
      </aside>

      {/* Main Viewport */}
      <div className="app-main-viewport">
        {/* Mobile Topbar (< 1024px) */}
        <header className="mobile-topbar">
          <NavLink to="/" className="mobile-brand">
            <img
              src="/logo.png"
              alt="MyMonee"
              style={{
                width: 30,
                height: 30,
                borderRadius: 6,
                objectFit: "contain",
                flexShrink: 0,
              }}
            />
            <span className="mobile-brand-title">MyMonee</span>
          </NavLink>

          <div className="mobile-topbar-controls">
            <SyncNavButton
              syncing={syncing}
              onSync={() => void handleIncrementalSync()}
              className="btn icon-btn"
            />
            <NavLink
              to="/settings"
              title="Settings"
              aria-label="Settings"
              className="btn icon-btn"
              style={{ width: 36, height: 36, display: "inline-flex", alignItems: "center", justifyContent: "center" }}
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" /><circle cx="12" cy="12" r="3" /></svg>
            </NavLink>
            <button
              type="button"
              className="mobile-nav-toggle btn icon-btn"
              onClick={() => setMobileMenuOpen(true)}
              aria-label="Open mobile menu"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><line x1="4" x2="20" y1="12" y2="12" /><line x1="4" x2="20" y1="6" y2="6" /><line x1="4" x2="20" y1="18" y2="18" /></svg>
            </button>
          </div>
        </header>

        {/* Mobile Drawer */}
        {mobileMenuOpen && (
          <>
            <div className="mobile-drawer-backdrop" onClick={() => setMobileMenuOpen(false)} />
            <div className="mobile-drawer" role="dialog" aria-modal="true" aria-label="Mobile navigation">
              <div className="mobile-drawer-header">
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <img src="/logo.png" alt="MyMonee" style={{ width: 28, height: 28, borderRadius: 6 }} />
                  <strong style={{ fontSize: "1.1rem", fontFamily: "var(--font-body)", fontWeight: 750 }}>MyMonee</strong>
                </div>
                <button
                  type="button"
                  className="btn icon-btn"
                  onClick={() => setMobileMenuOpen(false)}
                  aria-label="Close menu"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M18 6 6 18" /><path d="m6 6 12 12" /></svg>
                </button>
              </div>
              <nav className="mobile-drawer-nav">
                <NavLink to="/" end onClick={() => setMobileMenuOpen(false)}>
                  Overview
                </NavLink>
                <div className="mobile-drawer-section-title">Transactions</div>
                <NavLink to="/transactions" className="mobile-drawer-sublink" onClick={() => setMobileMenuOpen(false)}>
                  Classified
                </NavLink>
                <NavLink to="/review" className="mobile-drawer-sublink" onClick={() => setMobileMenuOpen(false)}>
                  Needs Review
                </NavLink>
                <NavLink to="/data-issues" className="mobile-drawer-sublink" onClick={() => setMobileMenuOpen(false)}>
                  Data Issues
                </NavLink>
                <div className="mobile-drawer-section-title">Analysis</div>
                <NavLink to="/categories" onClick={() => setMobileMenuOpen(false)}>
                  Categories Deep Dive
                </NavLink>
                <NavLink to="/recurring" className="mobile-drawer-sublink" onClick={() => setMobileMenuOpen(false)}>
                  Recurring &amp; Subscriptions
                </NavLink>
                <div className="mobile-drawer-section-title">Management</div>
                <NavLink to="/accounts" onClick={() => setMobileMenuOpen(false)}>
                  Accounts
                </NavLink>
                <NavLink to="/merchants" onClick={() => setMobileMenuOpen(false)}>
                  Merchants
                </NavLink>
                <NavLink to="/settings" onClick={() => setMobileMenuOpen(false)}>
                  Settings
                </NavLink>
              </nav>
              <div className="mobile-drawer-footer">
                <button
                  type="button"
                  onClick={() => {
                    setMobileMenuOpen(false);
                    void handleLogout();
                  }}
                  className="mobile-drawer-lock-btn"
                  title="Lock Session"
                >
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    width="18"
                    height="18"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                  >
                    <rect width="18" height="11" x="3" y="11" rx="2" ry="2" />
                    <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                  </svg>
                  <span>Lock Session</span>
                </button>
              </div>
            </div>
          </>
        )}

        <main className="app-main-content">
          <ErrorBoundary>
            <Suspense fallback={<div style={{ padding: "48px 24px", textAlign: "center", color: "var(--ink-muted)", fontSize: "0.9rem" }}>Loading view…</div>}>
              <Routes>
                <Route path="/" element={<OverviewPage />} />
                <Route path="/categories" element={<CategoryAnalyticsPage />} />
                <Route path="/analytics/category/:categoryId?" element={<CategoryAnalyticsPage />} />
                <Route path="/analytics" element={<Navigate to="/categories" replace />} />
                <Route path="/transactions" element={<TransactionsPage />} />
                <Route path="/recurring" element={<RecurringPage />} />
                <Route path="/merchants" element={<MerchantsPage />} />
                <Route path="/review" element={<TransactionsPage needsReview />} />
                <Route path="/data-issues" element={<DataIssuesPage />} />
                <Route path="/issues" element={<Navigate to="/data-issues" replace />} />
                <Route path="/onboarding" element={<OnboardingPage />} />
                <Route path="/settings" element={<SettingsPage />} />
                <Route path="/accounts" element={<AccountsPage />} />
                <Route path="/statements" element={<CreditCardStatementsPage />} />
                <Route path="/system" element={<Navigate to="/settings" replace />} />
              </Routes>
            </Suspense>
          </ErrorBoundary>
        </main>
      </div>
    </div>
  );
}
