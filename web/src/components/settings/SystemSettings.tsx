import { SystemStatus } from "../../api";

interface SystemSettingsProps {
  status: SystemStatus;
}

export default function SystemSettings({ status }: SystemSettingsProps) {
  return (
    <div className="settings-section-container">
      <div className="settings-section-header">
        <h2>System &amp; Diagnostics</h2>
        <p className="lead">
          Operational health status, background task scheduler, and local server runtime information.
        </p>
      </div>

      {/* Health Overview */}
      <div className="settings-card">
        <div className="settings-card-topbar">
          <span className="settings-status-title">System Health</span>
          <span className="status-badge-healthy">● All Systems Operational</span>
        </div>

        <div className="settings-meta-grid">
          <div className="settings-meta-item">
            <span className="meta-label">SQLite Database</span>
            <span className="meta-value" style={{ color: "var(--credit)", fontWeight: 600 }}>
              ● Healthy
            </span>
          </div>
          <div className="settings-meta-item">
            <span className="meta-label">Gmail Integration</span>
            <span className="meta-value">
              {status.gmail.connected ? (
                <span style={{ color: "var(--credit)", fontWeight: 600 }}>● Connected</span>
              ) : (
                <span style={{ color: "var(--ink-muted)" }}>○ Disconnected</span>
              )}
            </span>
          </div>
          <div className="settings-meta-item">
            <span className="meta-label">Background Scheduler</span>
            <span className="meta-value">
              {status.app.scheduler_enabled ? (
                <span style={{ color: "var(--credit)", fontWeight: 600 }}>● Running</span>
              ) : (
                <span style={{ color: "var(--ink-muted)" }}>○ Stopped</span>
              )}
            </span>
          </div>
          <div className="settings-meta-item">
            <span className="meta-label">AI Engine</span>
            <span className="meta-value">
              {status.app.ai_enabled ? (
                <span style={{ color: "var(--credit)", fontWeight: 600 }}>● Available</span>
              ) : (
                <span style={{ color: "var(--ink-muted)" }}>○ Disabled</span>
              )}
            </span>
          </div>
        </div>
      </div>

      {/* Runtime Details */}
      <div className="settings-card">
        <div className="settings-section-header" style={{ marginBottom: 12 }}>
          <h3 style={{ margin: "0 0 4px", fontSize: "1rem" }}>Runtime Details</h3>
          <p className="lead" style={{ margin: 0, fontSize: "0.82rem" }}>
            Local daemon server and process configuration.
          </p>
        </div>

        <div className="settings-row">
          <div className="settings-row-info">
            <div className="settings-row-label">Application Name</div>
            <div className="settings-row-desc">Registered application package.</div>
          </div>
          <div className="settings-row-value">
            <span className="mono">{status.app.name}</span>
          </div>
        </div>

        <div className="settings-row">
          <div className="settings-row-info">
            <div className="settings-row-label">Local Server Endpoint</div>
            <div className="settings-row-desc">FastAPI loopback server bind address.</div>
          </div>
          <div className="settings-row-value">
            <span className="mono">http://{status.app.host}:{status.app.port}</span>
          </div>
        </div>

        <div className="settings-row">
          <div className="settings-row-info">
            <div className="settings-row-label">Operating Environment</div>
            <div className="settings-row-desc">Platform and launchd daemon manager.</div>
          </div>
          <div className="settings-row-value">
            <span className="mono">macOS / launchd background service</span>
          </div>
        </div>
      </div>
    </div>
  );
}
