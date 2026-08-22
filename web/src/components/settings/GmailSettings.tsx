import { useRef, useState } from "react";
import { createPortal } from "react-dom";
import { type GmailStatus, type IngestionResult, type SystemStatus, api } from "../../api";
import { formatDateTime } from "../../format";

interface GmailSettingsProps {
  status: SystemStatus;
  gmail: GmailStatus;
  loading?: boolean;
  onRefresh: () => Promise<void>;
  onShowToast: (msg: string, type?: "success" | "error") => void;
}

export default function GmailSettings({
  status,
  gmail,
  loading = false,
  onRefresh,
  onShowToast,
}: GmailSettingsProps) {
  const [parsedCreds, setParsedCreds] = useState<Record<string, any> | null>(null);
  const [lastRun, setLastRun] = useState<IngestionResult | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [validating, setValidating] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const isValidating = loading || validating;
  const isBusy = busy !== null || isValidating;

  async function connectGmail() {
    setBusy("connect");
    try {
      const started = await api.gmailAuthStart();
      window.location.href = started.authorization_url;
    } catch (err) {
      onShowToast(err instanceof Error ? err.message : "Failed to start OAuth", "error");
      setBusy(null);
    }
  }

  async function verifyConnection() {
    setValidating(true);
    try {
      await onRefresh();
      onShowToast("Gmail connection verified", "success");
    } catch (err) {
      onShowToast(err instanceof Error ? err.message : "Validation failed", "error");
    } finally {
      setValidating(false);
    }
  }

  async function disconnectGmail() {
    setBusy("disconnect");
    try {
      await api.gmailDisconnect();
      onShowToast("Gmail disconnected. Keychain tokens cleared.", "success");
      await onRefresh();
    } catch (err) {
      onShowToast(err instanceof Error ? err.message : "Disconnect failed", "error");
    } finally {
      setBusy(null);
    }
  }

  async function syncGmail(fullYear: boolean) {
    setBusy(fullYear ? "sync2026" : "sync");
    try {
      const result = await api.gmailSync({
        fullYear,
        afterDate: fullYear ? "2026/01/01" : undefined,
        maxMessages: 2000,
      });
      setLastRun(result);
      onShowToast(
        `Sync ${result.status}: discovered ${result.emails_discovered}, extracted ${result.transactions_extracted}, duplicates ${result.transactions_duplicated}`,
        result.status === "error" ? "error" : "success"
      );
      await onRefresh();
    } catch (err) {
      onShowToast(err instanceof Error ? err.message : "Sync failed", "error");
    } finally {
      setBusy(null);
    }
  }

  function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      try {
        const text = ev.target?.result as string;
        const parsed = JSON.parse(text) as Record<string, any>;
        setParsedCreds(parsed);
      } catch {
        onShowToast("Invalid JSON file. Please ensure it is a valid Google OAuth client JSON.", "error");
        setParsedCreds(null);
      }
    };
    reader.readAsText(file);
  }

  async function saveCredentials() {
    if (!parsedCreds) return;
    setBusy("creds");
    try {
      const result = await api.installCredentials(parsedCreds);
      onShowToast(`OAuth client saved to ${result.credentials_file}`, "success");
      setParsedCreds(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      await onRefresh();
    } catch (err) {
      onShowToast(err instanceof Error ? err.message : "Failed to save credentials", "error");
    } finally {
      setBusy(null);
    }
  }

  function cancelCreds() {
    setParsedCreds(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  return (
    <div className="settings-section-container">
      <div className="settings-section-header">
        <h2>Gmail Integration</h2>
        <p className="lead">
          Connect your Google account to ingest financial notification emails and PDF credit card statements.
        </p>
      </div>

      {/* Connection Status Overview Card */}
      <div className="settings-card">
        <div className="settings-card-topbar">
          <div className="settings-status-header">
            <span className="settings-status-title">Connection Status</span>
            {isValidating ? (
              <span className="status-badge-pending">
                <span className="spinner-dot" style={{ fontSize: "0.72rem" }}>◌</span> Validating…
              </span>
            ) : gmail.connected ? (
              <span className="status-badge-healthy">● Connected</span>
            ) : (
              <span className="status-badge-muted">○ Disconnected</span>
            )}
          </div>
        </div>

        <div className="settings-meta-grid">
          <div className="settings-meta-item">
            <span className="meta-label">Last Sync</span>
            <span className="meta-value">{formatDateTime(status.gmail.last_sync_at)}</span>
          </div>
          <div className="settings-meta-item">
            <span className="meta-label">Sync Lookback</span>
            <span className="meta-value">{gmail.sync_after_date ?? `${gmail.initial_lookback_days} days`}</span>
          </div>
          <div className="settings-meta-item">
            <span className="meta-label">Batch Limit</span>
            <span className="meta-value">{gmail.max_messages_per_sync} emails / sync</span>
          </div>
          <div className="settings-meta-item">
            <span className="meta-label">OAuth Client</span>
            <span className="meta-value">
              {isValidating ? "Validating…" : gmail.credentials_file_present ? "Configured" : "Missing credentials.json"}
            </span>
          </div>
        </div>

        {/* Action Controls */}
        <div className="settings-actions-row">
          {isValidating ? (
            <div className="settings-validating-hint">
              <span className="spinner-dot">◌</span>
              <span>Validating Gmail connection and credentials…</span>
            </div>
          ) : !gmail.connected ? (
            <div className="gmail-actions-container">
              <button
                className="btn primary"
                type="button"
                disabled={isBusy || !gmail.credentials_file_present}
                onClick={() => void connectGmail()}
              >
                {busy === "connect" ? "Opening Google…" : "Connect Gmail"}
              </button>

              {!gmail.credentials_file_present && (
                <span className="metric-hint" style={{ fontSize: "0.82rem" }}>
                  Please import a Google OAuth <code>credentials.json</code> below first.
                </span>
              )}
            </div>
          ) : (
            <div className="gmail-actions-container connected">
              <button
                className="btn primary"
                type="button"
                disabled={isBusy}
                onClick={() => void syncGmail(false)}
              >
                {busy === "sync" ? "Syncing…" : "Incremental Sync"}
              </button>
              <button
                className="btn"
                type="button"
                disabled={isBusy}
                onClick={() => void syncGmail(true)}
              >
                {busy === "sync2026" ? "Syncing 2026…" : "Sync 2026 Dataset"}
              </button>
              <button
                className="btn quiet"
                type="button"
                disabled={isBusy}
                onClick={() => void verifyConnection()}
                title="Verify and refresh connection status"
              >
                Verify Connection
              </button>
              <button
                className="btn quiet"
                type="button"
                disabled={isBusy}
                onClick={() => void disconnectGmail()}
                style={{ color: "var(--danger)" }}
              >
                {busy === "disconnect" ? "Disconnecting…" : "Disconnect"}
              </button>
            </div>
          )}
        </div>

        {/* Sync Summary if available */}
        {lastRun && (
          <div className="settings-sync-feedback">
            <div className="feedback-status">
              <strong>Last Sync:</strong> {lastRun.status} · Discovered {lastRun.emails_discovered} emails · Extracted {lastRun.transactions_extracted} transactions · {lastRun.transactions_duplicated} duplicates
              {lastRun.error_summary && <span className="feedback-err"> · {lastRun.error_summary}</span>}
            </div>
          </div>
        )}
      </div>

      {/* OAuth Client File Upload Section */}
      <div className="settings-card oauth-upload-card">
        <div className="oauth-card-header">
          <div className="oauth-title-group">
            <div className="settings-row-label">Google OAuth Credentials</div>
            {gmail.credentials_file_present ? (
              <span className="status-badge-healthy">● Configured</span>
            ) : (
              <span className="status-badge-muted">○ Missing</span>
            )}
          </div>
          <div className="settings-row-desc">
            Import <code>credentials.json</code> generated from your Google Cloud Console Desktop application.
          </div>
        </div>
        <div className="oauth-upload-action">
          <input
            type="file"
            accept=".json"
            ref={fileInputRef}
            onChange={handleFileSelect}
            id="oauth-file-input"
            style={{ display: "none" }}
          />
          <label htmlFor="oauth-file-input" className="btn oauth-upload-btn">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="17 8 12 3 7 8" />
              <line x1="12" y1="3" x2="12" y2="15" />
            </svg>
            <span>{gmail.credentials_file_present ? "Replace credentials.json" : "Import credentials.json"}</span>
          </label>
        </div>
      </div>

      {/* Expandable Advanced / Developer Details */}
      <details className="settings-details-panel">
        <summary className="settings-details-summary">
          <span>Advanced / Developer Details</span>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="summary-chevron">
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </summary>

        <div className="settings-details-body">
          <div className="settings-row">
            <div className="settings-row-info">
              <div className="settings-row-label">Credentials Path</div>
              <div className="settings-row-desc">Location on Mac storage where client secret is kept.</div>
            </div>
            <div className="settings-row-value">
              <div className="mono-copy-group">
                <span className="mono">{gmail.credentials_file}</span>
                <button
                  type="button"
                  className="copy-btn"
                  onClick={() => void navigator.clipboard.writeText(gmail.credentials_file)}
                >
                  Copy
                </button>
              </div>
            </div>
          </div>

          <div className="settings-row">
            <div className="settings-row-info">
              <div className="settings-row-label">Redirect URI</div>
              <div className="settings-row-desc">Loopback callback URI for OAuth loopback server.</div>
            </div>
            <div className="settings-row-value">
              <div className="mono-copy-group">
                <span className="mono">{gmail.redirect_uri}</span>
                <button
                  type="button"
                  className="copy-btn"
                  onClick={() => void navigator.clipboard.writeText(gmail.redirect_uri)}
                >
                  Copy
                </button>
              </div>
            </div>
          </div>

          {gmail.scopes && gmail.scopes.length > 0 && (
            <div className="settings-row">
              <div className="settings-row-info">
                <div className="settings-row-label">Requested Scopes</div>
                <div className="settings-row-desc">Read-only permissions requested during Google login.</div>
              </div>
              <div className="settings-row-value">
                <div className="tags-cluster">
                  {gmail.scopes.map((s) => (
                    <span key={s} className="sub-chip mono" style={{ fontSize: "0.75rem" }}>{s}</span>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      </details>

      {/* Confirmation Modal when file selected */}
      {parsedCreds && createPortal(
        <div className="modal-backdrop">
          <div className="modal-panel" role="dialog" aria-modal="true" style={{ width: "min(760px, 95vw)" }}>
            <header className="modal-header">
              <div>
                <h2>Confirm OAuth Credentials</h2>
                <p className="lead">Review the imported client configuration before writing to local keychain storage.</p>
              </div>
              <div className="modal-actions">
                <button type="button" className="btn icon-btn" onClick={cancelCreds} aria-label="Close modal">
                  <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M18 6 6 18" />
                    <path d="m6 6 12 12" />
                  </svg>
                </button>
              </div>
            </header>

            <div className="modal-body" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <div className="table-wrap" style={{ border: "1px solid var(--line)", borderRadius: "var(--radius)", overflow: "auto" }}>
                <table style={{ minWidth: "100%" }}>
                  <thead>
                    <tr>
                      <th style={{ width: "30%" }}>Configuration Key</th>
                      <th>Value</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(parsedCreds.installed || parsedCreds.web || parsedCreds).map(([k, v]) => (
                      <tr key={k}>
                        <td className="mono">{k}</td>
                        <td className="mono metric-hint" style={{ wordBreak: "break-all", whiteSpace: "pre-wrap" }}>
                          {typeof v === "object" ? JSON.stringify(v, null, 2) : String(v)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <footer className="modal-footer">
              <button
                className="btn quiet"
                type="button"
                disabled={isBusy}
                onClick={cancelCreds}
              >
                Cancel
              </button>
              <button
                className="btn primary"
                type="button"
                disabled={isBusy}
                onClick={() => void saveCredentials()}
              >
                {busy === "creds" ? "Importing…" : "Confirm & Save"}
              </button>
            </footer>
          </div>
        </div>,
        document.body
      )}
    </div>
  );
}
