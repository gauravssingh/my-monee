import { SystemStatus } from "../../api";
import { useTheme, type Theme } from "../../hooks/useTheme";
import SegmentedControl from "../common/SegmentedControl";

interface GeneralSettingsProps {
  status: SystemStatus;
}

export default function GeneralSettings({ status }: GeneralSettingsProps) {
  const { theme, setTheme } = useTheme();

  return (
    <div className="settings-section-container">
      <div className="settings-section-header">
        <h2>General Preferences</h2>
        <p className="lead">
          Core localization, visual theme, accounting currency, and application display preferences.
        </p>
      </div>

      <div className="settings-card">
        {/* Appearance / Theme Selector */}
        <div className="settings-row">
          <div className="settings-row-info">
            <div className="settings-row-label">Appearance & Theme</div>
            <div className="settings-row-desc">
              Select your visual preference or automatically sync with macOS system mode.
            </div>
          </div>
          <div className="settings-row-value">
            <SegmentedControl<Theme>
              value={theme}
              onChange={setTheme}
              size="sm"
              options={[
                { value: "system", label: "💻 System" },
                { value: "light", label: "☀️ Light" },
                { value: "dark", label: "🌙 Dark" },
              ]}
            />
          </div>
        </div>

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
