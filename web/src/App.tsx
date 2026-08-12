import { Navigate, NavLink, Route, Routes } from "react-router-dom";
import DataIssuesPage from "./pages/DataIssuesPage";
import OverviewPage from "./pages/OverviewPage";
import SettingsPage from "./pages/SettingsPage";
import TransactionsPage from "./pages/TransactionsPage";

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
          <NavLink to="/transactions">Transactions</NavLink>
          <NavLink to="/review">Needs Review</NavLink>
          <NavLink to="/data-issues">Data Issues</NavLink>
          <NavLink to="/settings">Settings</NavLink>
        </nav>
      </header>

      <Routes>
        <Route path="/" element={<OverviewPage />} />
        <Route path="/transactions" element={<TransactionsPage />} />
        <Route path="/review" element={<TransactionsPage needsReview />} />
        <Route path="/data-issues" element={<DataIssuesPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/system" element={<Navigate to="/settings" replace />} />
      </Routes>
    </div>
  );
}
