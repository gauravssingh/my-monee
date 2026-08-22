import { SystemStatus } from "../../api";

interface AISettingsProps {
  status: SystemStatus;
}

export default function AISettings({ status }: AISettingsProps) {
  const fallbackChain =
    status.app.ai_fallback_models && status.app.ai_fallback_models.length > 0
      ? status.app.ai_fallback_models.join(" → ")
      : `${status.app.ai_model || "gemini-3.7-flash"} → gemini-3.5-flash-lite → gemini-3.1-flash-lite`;

  return (
    <div className="settings-section-container">
      <div className="settings-section-header">
        <h2>AI Intelligence</h2>
        <p className="lead">
          Configure optional AI-assisted transaction normalization, category suggestions, and summary generation.
        </p>
      </div>

      {/* AI Status Overview */}
      <div className="settings-card">
        <div className="settings-card-topbar">
          <div className="settings-status-header">
            <span className="settings-status-title">AI Engine Status</span>
            {status.app.ai_enabled ? (
              <span className="status-badge-healthy">● Enabled</span>
            ) : (
              <span className="status-badge-muted">○ Disabled</span>
            )}
          </div>
        </div>

        <div className="settings-meta-grid">
          <div className="settings-meta-item">
            <span className="meta-label">AI Features</span>
            <span className="meta-value">
              {status.app.ai_enabled ? (
                <span style={{ color: "var(--credit)", fontWeight: 600 }}>● Enabled</span>
              ) : (
                <span style={{ color: "var(--ink-muted)" }}>○ Off</span>
              )}
            </span>
          </div>
          <div className="settings-meta-item">
            <span className="meta-label">External AI Access</span>
            <span className="meta-value">
              {status.app.allow_external_ai ? (
                <span style={{ color: "var(--credit)", fontWeight: 600 }}>● Allowed</span>
              ) : (
                <span style={{ color: "var(--warn)", fontWeight: 600 }}>○ Restricted</span>
              )}
            </span>
          </div>
          <div className="settings-meta-item">
            <span className="meta-label">Provider</span>
            <span className="meta-value">{status.app.ai_provider || "Gemini"}</span>
          </div>
          <div className="settings-meta-item">
            <span className="meta-label">Primary Model</span>
            <span className="meta-value mono">{status.app.ai_model || "gemini-3.7-flash"}</span>
          </div>
        </div>
      </div>

      {/* Privacy Notice Banner */}
      <div className="settings-notice-banner">
        <div className="notice-icon">✦</div>
        <div className="notice-content">
          <strong>Privacy &amp; Local-First Assurance</strong>
          <p>
            MyMonee processes all financial statements and deterministic classification rules locally on this Mac.
            External AI is only invoked for unresolved merchant classifications when explicitly permitted in your configuration.
          </p>
        </div>
      </div>

      {/* Advanced AI Configuration */}
      <div className="settings-card">
        <div className="settings-section-header" style={{ marginBottom: 12 }}>
          <h3 style={{ margin: "0 0 4px", fontSize: "1rem" }}>Advanced Configuration</h3>
          <p className="lead" style={{ margin: 0, fontSize: "0.82rem" }}>
            Runtime parameters managed via <code>config/local.yaml</code> and environment variables.
          </p>
        </div>

        <div className="settings-row">
          <div className="settings-row-info">
            <div className="settings-row-label">Model Fallback Chain</div>
            <div className="settings-row-desc">Automatic failover sequence if primary model encounters rate limits.</div>
          </div>
          <div className="settings-row-value">
            <span className="mono" style={{ fontSize: "0.82rem" }}>{fallbackChain}</span>
          </div>
        </div>

        <div className="settings-row">
          <div className="settings-row-info">
            <div className="settings-row-label">API Key Configuration</div>
            <div className="settings-row-desc">Configured via <code>GEMINI_API_KEY</code> in your environment.</div>
          </div>
          <div className="settings-row-value">
            <span className="badge-pill">Never Stored in Database</span>
          </div>
        </div>

        <div className="settings-row">
          <div className="settings-row-info">
            <div className="settings-row-label">Classification Hierarchy</div>
            <div className="settings-row-desc">Order of classification evaluation.</div>
          </div>
          <div className="settings-row-value">
            <span className="mono" style={{ fontSize: "0.82rem" }}>
              User Rules → Merchant Dictionary → Heuristics → AI (Optional)
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
