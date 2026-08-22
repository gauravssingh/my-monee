import { SystemStatus } from "../../api";

interface GeneralSettingsProps {
  status: SystemStatus;
}

export default function GeneralSettings({ status }: GeneralSettingsProps) {
  return (
    <div className="settings-section-container">
      <div className="settings-section-header">
        <h2>General Preferences</h2>
        <p className="lead">
          Core localization, accounting currency, and application display preferences.
        </p>
      </div>

      <div className="settings-card">
        <div className="settings-row">
          <div className="settings-row-info">
            <div className="settings-row-label">Base Currency</div>
            <div className="settings-row-desc">Default currency used for financial analysis and aggregations.</div>
          </div>
          <div className="settings-row-value">
            <span className="badge-pill">{status.app.currency || "INR"} (₹)</span>
          </div>
        </div>

        <div className="settings-row">
          <div className="settings-row-info">
            <div className="settings-row-label">Number Formatting</div>
            <div className="settings-row-desc">Standard Indian numbering system with Lakhs (L) and Crores (Cr).</div>
          </div>
          <div className="settings-row-value">
            <span className="mono">en-IN (e.g. ₹1,50,000)</span>
          </div>
        </div>

        <div className="settings-row">
          <div className="settings-row-info">
            <div className="settings-row-label">Date Format</div>
            <div className="settings-row-desc">Chronological formatting used across transactions and statements.</div>
          </div>
          <div className="settings-row-value">
            <span className="mono">DD MMM YYYY (e.g. 19 Aug 2026)</span>
          </div>
        </div>

        <div className="settings-row">
          <div className="settings-row-info">
            <div className="settings-row-label">UPI Handles Monitored</div>
            <div className="settings-row-desc">Handles used to detect self-transfers and bank movement.</div>
          </div>
          <div className="settings-row-value">
            {status.app.upi_handles && status.app.upi_handles.length > 0 ? (
              <div className="tags-cluster">
                {status.app.upi_handles.map((h) => (
                  <span key={h} className="sub-chip mono">{h.startsWith("@") ? h : `@${h}`}</span>
                ))}
              </div>
            ) : (
              <span className="metric-hint">Configured via accounts and providers</span>
            )}
          </div>
        </div>

        <div className="settings-row">
          <div className="settings-row-info">
            <div className="settings-row-label">Ledger Architecture</div>
            <div className="settings-row-desc">Durable local SQLite database with privacy-first offline storage.</div>
          </div>
          <div className="settings-row-value">
            <span className="status-badge-healthy">● Local-First</span>
          </div>
        </div>
      </div>
    </div>
  );
}
