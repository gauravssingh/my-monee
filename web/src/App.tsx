import { Component, type ErrorInfo, type ReactNode } from "react";
import { Navigate, NavLink, Route, Routes } from "react-router-dom";
import DataIssuesPage from "./pages/DataIssuesPage";
import OverviewPage from "./pages/OverviewPage";
import SettingsPage from "./pages/SettingsPage";
import TransactionsPage from "./pages/TransactionsPage";
import MerchantsPage from "./pages/MerchantsPage";
import RecurringPage from "./pages/RecurringPage";
import AccountsPage from "./pages/AccountsPage";

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
  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark">
            MyMonee <span className="brand-tagline">.. my finances</span>
          </div>
        </div>
        <nav className="nav">
          <NavLink to="/" end>
            Overview
          </NavLink>
          <div className="nav-dropdown">
            <NavLink to="/transactions" className="nav-dropdown-toggle">Transactions ▾</NavLink>
            <div className="nav-dropdown-content">
              <NavLink to="/transactions">All Transactions</NavLink>
              <NavLink to="/review">Needs Review</NavLink>
              <NavLink to="/data-issues">Data Issues</NavLink>
              <NavLink to="/recurring">Recurring and Subscriptions</NavLink>
            </div>
          </div>
          <NavLink to="/accounts">Accounts</NavLink>
          <NavLink to="/merchants">Merchants</NavLink>
          <NavLink to="/settings">Settings</NavLink>
        </nav>
      </header>

      <ErrorBoundary>
        <Routes>
          <Route path="/" element={<OverviewPage />} />
          <Route path="/transactions" element={<TransactionsPage />} />
          <Route path="/recurring" element={<RecurringPage />} />
          <Route path="/merchants" element={<MerchantsPage />} />
          <Route path="/review" element={<TransactionsPage needsReview />} />
          <Route path="/data-issues" element={<DataIssuesPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/accounts" element={<AccountsPage />} />
          <Route path="/system" element={<Navigate to="/settings" replace />} />
        </Routes>
      </ErrorBoundary>
    </div>
  );
}
