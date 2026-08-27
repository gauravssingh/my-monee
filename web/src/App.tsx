import { Component, useEffect, useState, type ErrorInfo, type ReactNode } from "react";
import { Navigate, NavLink, Route, Routes } from "react-router-dom";
import DataIssuesPage from "./pages/DataIssuesPage";
import OverviewPage from "./pages/OverviewPage";
import SettingsPage from "./pages/SettingsPage";
import TransactionsPage from "./pages/TransactionsPage";
import MerchantsPage from "./pages/MerchantsPage";
import RecurringPage from "./pages/RecurringPage";
import AccountsPage from "./pages/AccountsPage";
import CategoryAnalyticsPage from "./pages/CategoryAnalyticsPage";
import CreditCardStatementsPage from "./pages/CreditCardStatementsPage";
import OnboardingPage from "./pages/OnboardingPage";
import LockScreen from "./components/LockScreen";
import { api } from "./api";

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

export default function App() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [authLoading, setAuthLoading] = useState(true);
  const [authConfigured, setAuthConfigured] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);

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
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <NavLink to="/" style={{ display: "flex", alignItems: "center", gap: "10px", textDecoration: "none", color: "inherit" }}>
            <img
              src="/logo.png"
              alt="MyMonee Logo"
              style={{
                width: 36,
                height: 36,
                borderRadius: 8,
                objectFit: "contain",
                boxShadow: "0 1px 3px rgba(0,0,0,0.08)",
                flexShrink: 0,
              }}
            />
            <div className="brand-mark">
              MyMonee <span className="brand-tagline">.. my finances</span>
            </div>
          </NavLink>
        </div>

        {/* Desktop Navigation */}
        <nav className="nav desktop-nav">
          <NavLink to="/" end>
            Overview
          </NavLink>
          <div
            className={`nav-dropdown ${dropdownOpen ? "open" : ""}`}
            onMouseEnter={() => setDropdownOpen(true)}
            onMouseLeave={() => setDropdownOpen(false)}
          >
            <button
              type="button"
              className="nav-dropdown-toggle"
              onClick={(e) => {
                e.preventDefault();
                setDropdownOpen((prev) => !prev);
              }}
              style={{
                background: "none",
                border: "none",
                padding: "4px 0",
                font: "inherit",
                cursor: "pointer",
                display: "inline-flex",
                alignItems: "center",
                gap: 4,
              }}
            >
              Transactions ▾
            </button>
            <div className="nav-dropdown-content" onClick={() => setDropdownOpen(false)}>
              <NavLink to="/transactions">Classified</NavLink>
              <NavLink to="/review">Needs Review</NavLink>
              <NavLink to="/data-issues">Data Issues</NavLink>
              <NavLink to="/recurring">Recurring and Subscriptions</NavLink>
            </div>
          </div>
          <NavLink to="/categories">Categories</NavLink>
          <NavLink to="/accounts">Accounts</NavLink>
          <NavLink to="/merchants">Merchants</NavLink>
          <NavLink
            to="/settings"
            title="Settings"
            aria-label="Settings"
            style={{
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              padding: "4px 8px",
              lineHeight: 1,
            }}
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
              <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" />
              <circle cx="12" cy="12" r="3" />
            </svg>
          </NavLink>
        </nav>

        {/* Mobile Navigation Controls */}
        <div className="mobile-nav-controls">
          <NavLink
            to="/settings"
            title="Settings"
            aria-label="Settings"
            className="btn icon-btn"
            style={{ width: 38, height: 38, display: "inline-flex", alignItems: "center", justifyContent: "center" }}
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/></svg>
          </NavLink>
          <button
            type="button"
            className="mobile-nav-toggle"
            onClick={() => setMobileMenuOpen(true)}
            aria-label="Open mobile menu"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="4" x2="20" y1="12" y2="12"/><line x1="4" x2="20" y1="6" y2="6"/><line x1="4" x2="20" y1="18" y2="18"/></svg>
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
                <strong style={{ fontSize: "1.1rem", fontFamily: "var(--font-display)" }}>MyMonee</strong>
              </div>
              <button
                type="button"
                className="btn icon-btn"
                onClick={() => setMobileMenuOpen(false)}
                aria-label="Close menu"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
              </button>
            </div>
            <nav className="mobile-drawer-nav">
              <NavLink to="/" end onClick={() => setMobileMenuOpen(false)}>
                Overview
              </NavLink>
              <NavLink to="/categories" onClick={() => setMobileMenuOpen(false)}>
                Categories Deep Dive
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
              {authConfigured && (
                <button
                  type="button"
                  onClick={() => {
                    setMobileMenuOpen(false);
                    handleLogout();
                  }}
                  className="btn quiet"
                  style={{ marginTop: 12, textAlign: "left", width: "100%", padding: "10px 12px", color: "var(--danger)" }}
                >
                  🔒 Lock Session
                </button>
              )}
            </nav>
          </div>
        </>
      )}

      <ErrorBoundary>
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
      </ErrorBoundary>
    </div>
  );
}
