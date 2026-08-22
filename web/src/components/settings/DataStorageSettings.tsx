import { SystemStatus } from "../../api";

interface DataStorageSettingsProps {
  status: SystemStatus;
  onShowToast: (msg: string, type?: "success" | "error") => void;
}

export default function DataStorageSettings({ status, onShowToast }: DataStorageSettingsProps) {
  function copyText(text: string, label: string) {
    void navigator.clipboard.writeText(text);
    onShowToast(`${label} copied to clipboard`, "success");
  }

  return (
    <div className="settings-section-container">
      <div className="settings-section-header">
        <h2>Data &amp; Storage</h2>
        <p className="lead">
          Inspect where this Mac keeps your durable SQLite ledger, imported email records, and statement files.
        </p>
      </div>

      {/* Database Statistics */}
      <div className="settings-card">
        <div className="settings-card-topbar">
          <span className="settings-status-title">Ledger Storage Metrics</span>
          <span className="status-badge-healthy">● SQLite Active</span>
        </div>

        <div className="settings-meta-grid">
          <div className="settings-meta-item">
            <span className="meta-label">Transactions Stored</span>
            <span className="meta-value" style={{ fontSize: "1.2rem", fontWeight: 700 }}>
              {status.database.transaction_count.toLocaleString()}
            </span>
          </div>
          <div className="settings-meta-item">
            <span className="meta-label">Emails Indexed</span>
            <span className="meta-value" style={{ fontSize: "1.2rem", fontWeight: 700 }}>
              {status.database.email_count.toLocaleString()}
            </span>
          </div>
          <div className="settings-meta-item">
            <span className="meta-label">Database Format</span>
            <span className="meta-value">SQLite 3 (WAL Mode)</span>
          </div>
          <div className="settings-meta-item">
            <span className="meta-label">Cloud Backup</span>
            <span className="meta-value">Local Only (No Cloud DB)</span>
          </div>
        </div>
      </div>

      {/* Filesystem Paths */}
      <div className="settings-card">
        <div className="settings-section-header" style={{ marginBottom: 12 }}>
          <h3 style={{ margin: "0 0 4px", fontSize: "1rem" }}>Storage Locations</h3>
          <p className="lead" style={{ margin: 0, fontSize: "0.82rem" }}>
            Local paths on this macOS filesystem.
          </p>
        </div>

        <div className="settings-row">
          <div className="settings-row-info">
            <div className="settings-row-label">Data Directory</div>
            <div className="settings-row-desc">Application data and cached attachments folder.</div>
          </div>
          <div className="settings-row-value">
            <div className="mono-copy-group">
              <span className="mono">{status.app.data_dir}</span>
              <button
                type="button"
                className="copy-btn"
                onClick={() => copyText(status.app.data_dir, "Data directory path")}
              >
                Copy
              </button>
            </div>
          </div>
        </div>

        <div className="settings-row">
          <div className="settings-row-info">
            <div className="settings-row-label">Database File</div>
            <div className="settings-row-desc">Primary SQLite database ledger file path.</div>
          </div>
          <div className="settings-row-value">
            <div className="mono-copy-group">
              <span className="mono">{status.app.database_path}</span>
              <button
                type="button"
                className="copy-btn"
                onClick={() => copyText(status.app.database_path, "Database path")}
              >
                Copy
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Local-First Principles */}
      <div className="settings-notice-banner">
        <div className="notice-icon">▣</div>
        <div className="notice-content">
          <strong>Local-First Architecture</strong>
          <p>
            SQLite is the single source of truth for your financial data. No transaction records or personal details
            are synced to external cloud databases. You can easily back up your ledger by copying the SQLite database file.
          </p>
        </div>
      </div>
    </div>
  );
}
