import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import { createPortal } from "react-dom";
import {
  api,
  type GmailStatus,
  type IngestionResult,
  type SystemStatus,
} from "../api";
import { formatDateTime } from "../format";
import CategoriesPage from "./CategoriesPage";



function StatusRows({ rows }: { rows: Array<[string, string, boolean?]> }) {
  return (
    <div className="status-grid">
      {rows.map(([key, value, mono]) => (
        <div className="status-row" key={key}>
          <div className="status-key">{key}</div>
          {mono ? (
            <div className="status-value">
              <div className="mono">{value}</div>
              <button
                type="button"
                className="copy-btn"
                onClick={() => void navigator.clipboard.writeText(value)}
              >
                Copy
              </button>
            </div>
          ) : (
            <div>{value}</div>
          )}
        </div>
      ))}
    </div>
  );
}

export default function SettingsPage() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [gmail, setGmail] = useState<GmailStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [lastRun, setLastRun] = useState<IngestionResult | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [parsedCreds, setParsedCreds] = useState<Record<string, any> | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const settingsStackRef = useRef<HTMLDivElement>(null);
  const [settingsStackHeight, setSettingsStackHeight] = useState<number>();

  const refresh = useCallback(async () => {
    const [system, gmailStatus] = await Promise.all([
      api.system(),
      api.gmailStatus(),
    ]);
    setStatus(system);
    setGmail(gmailStatus);
  }, []);

  useEffect(() => {
    refresh().catch((err: Error) => setError(err.message));
  }, [refresh]);

  useEffect(() => {
    const stack = settingsStackRef.current;
    if (!stack) return;

    const updateHeight = () => setSettingsStackHeight(stack.getBoundingClientRect().height);
    updateHeight();
    const observer = new ResizeObserver(updateHeight);
    observer.observe(stack);
    return () => observer.disconnect();
  }, [status, gmail]);

  async function saveCredentials() {
    if (!parsedCreds) return;
    setBusy("creds");
    setError(null);
    setNotice(null);
    try {
      const result = await api.installCredentials(parsedCreds);
      setNotice(`OAuth client saved to ${result.credentials_file}`);
      setParsedCreds(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save credentials");
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
        setError(null);
      } catch (err) {
        setError("Invalid JSON file. Please ensure it is a valid Google OAuth client JSON.");
        setParsedCreds(null);
      }
    };
    reader.readAsText(file);
  }

  function cancelCreds() {
    setParsedCreds(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
    setError(null);
  }

  async function connectGmail() {
    setBusy("connect");
    setError(null);
    setNotice(null);
    try {
      const started = await api.gmailAuthStart();
      window.location.href = started.authorization_url;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start OAuth");
      setBusy(null);
    }
  }

  async function disconnectGmail() {
    setBusy("disconnect");
    setError(null);
    try {
      await api.gmailDisconnect();
      setNotice("Gmail disconnected. Keychain tokens cleared.");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Disconnect failed");
    } finally {
      setBusy(null);
    }
  }

  async function syncGmail(fullYear: boolean) {
    setBusy(fullYear ? "sync2026" : "sync");
    setError(null);
    setNotice(null);
    try {
      const result = await api.gmailSync({
        fullYear,
        afterDate: fullYear ? "2026/01/01" : undefined,
        maxMessages: 2000,
      });
      setLastRun(result);
      setNotice(
        `Sync ${result.status}: discovered ${result.emails_discovered}, extracted ${result.transactions_extracted}, duplicates ${result.transactions_duplicated}, errors ${result.parsing_errors}`,
      );
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sync failed");
    } finally {
      setBusy(null);
    }
  }

  if (error && !status) return <p className="error">Could not load settings: {error}</p>;
  if (!status || !gmail) return <p className="empty">Loading settings…</p>;

  return (
    <>
      <header className="settings-intro">
        <h1 className="settings-title">Settings</h1>
        <p className="lead">
          Configure Gmail, manage the category master list used for classification, and inspect local
          runtime health.
        </p>
        {error && <p className="error">{error}</p>}
        {notice && createPortal(
          <div className="toast">
            <span>{notice}</span>
            <button className="toast-close" onClick={() => setNotice(null)} aria-label="Dismiss">&times;</button>
          </div>,
          document.body
        )}
      </header>

      <div
        className="settings-grid"
        style={
          settingsStackHeight
            ? ({ "--settings-stack-height": `${settingsStackHeight}px` } as CSSProperties)
            : undefined
        }
      >
        <div className="settings-stack" ref={settingsStackRef}>
          <section className="panel section">
          <h2>Gmail</h2>

          <div style={{ marginBottom: 12 }}>
            <div style={{ marginBottom: 10 }}>
              <input 
                type="file" 
                accept=".json" 
                ref={fileInputRef}
                onChange={handleFileSelect}
                style={{ display: parsedCreds ? "none" : "block" }}
              />
            </div>

            {parsedCreds && createPortal(
              <div className="modal-backdrop">
                <div className="modal-panel" role="dialog" aria-modal="true" style={{ width: "min(800px, 95vw)" }}>
                  <header className="modal-header" style={{ padding: "24px 32px", borderBottom: "1px solid var(--line)", alignItems: "flex-start" }}>
                    <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
                      <div style={{ width: 44, height: 44, borderRadius: "50%", background: "var(--accent-soft)", color: "var(--accent)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                        <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
                      </div>
                      <div>
                        <h2 style={{ margin: 0, fontSize: "1.25rem", fontWeight: 700, color: "var(--ink)" }}>Confirm OAuth Configuration</h2>
                        <p style={{ margin: "4px 0 0 0", color: "var(--ink-muted)", fontSize: "0.875rem" }}>Review the imported credentials before saving.</p>
                      </div>
                    </div>
                    <div className="modal-actions" style={{ alignSelf: "flex-start", marginTop: 4 }}>
                      <button type="button" className="btn icon-btn" onClick={cancelCreds} aria-label="Close modal">
                        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
                      </button>
                    </div>
                  </header>
                  <div className="modal-body" style={{ display: "flex", flexDirection: "column", gap: 24, padding: "32px" }}>
                    <div className="table-wrap" style={{ border: "1px solid var(--line)", borderRadius: 8, overflow: "auto" }}>
                    <table style={{ minWidth: "100%" }}>
                      <thead>
                        <tr>
                          <th style={{ width: "30%" }}>Key</th>
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
                  <footer style={{ padding: "20px 32px", borderTop: "1px solid var(--line)", background: "var(--surface)", display: "flex", justifyContent: "flex-end", alignItems: "center", borderRadius: "0 0 8px 8px" }}>
                    <div className="toolbar" style={{ justifyContent: "flex-end" }}>
                      <button
                        className="btn quiet"
                        type="button"
                        disabled={busy !== null}
                        onClick={cancelCreds}
                        style={{ padding: "10px 20px" }}
                      >
                        Cancel
                      </button>
                      <button
                        className="btn primary"
                        type="button"
                        disabled={busy !== null}
                        onClick={() => void saveCredentials()}
                        style={{ padding: "10px 24px" }}
                      >
                        {busy === "creds" ? "Importing…" : "Confirm & Import"}
                      </button>
                    </div>
                  </footer>
                </div>
              </div>,
              document.body
            )}
          </div>

          <div className="toolbar">
            {!gmail.connected ? (
              <button
                className="btn primary"
                type="button"
                disabled={busy !== null || !gmail.credentials_file_present}
                onClick={() => void connectGmail()}
              >
                {busy === "connect" ? "Opening Google…" : "Connect Gmail"}
              </button>
            ) : (
              <>
                <button
                  className="btn primary"
                  type="button"
                  disabled={busy !== null}
                  onClick={() => void syncGmail(false)}
                >
                  {busy === "sync" ? "Syncing…" : "Incremental sync"}
                </button>
                <button
                  className="btn"
                  type="button"
                  disabled={busy !== null}
                  onClick={() => void syncGmail(true)}
                >
                  {busy === "sync2026" ? "Syncing 2026…" : "Sync 2026 dataset"}
                </button>
                <button
                  className="btn"
                  type="button"
                  disabled={busy !== null}
                  onClick={() => void disconnectGmail()}
                >
                  Disconnect
                </button>
              </>
            )}

          </div>

          <StatusRows
            rows={[
              ["Connected", status.gmail.connected ? "Yes" : "No"],
              ["Last sync", formatDateTime(status.gmail.last_sync_at)],
              ["Sync from", gmail.sync_after_date ?? `${gmail.initial_lookback_days} days`],
              ["OAuth client", gmail.credentials_file_present ? "Found" : "Missing"],
              ["Credentials path", gmail.credentials_file, true],
              ["Redirect URI", gmail.redirect_uri, true],
            ]}
          />
          {lastRun && (
            <p className="metric-hint" style={{ marginTop: 12 }}>
              Last run: {lastRun.status} · discovered {lastRun.emails_discovered} · extracted{" "}
              {lastRun.transactions_extracted}
              {lastRun.error_summary ? ` · ${lastRun.error_summary}` : ""}
            </p>
          )}
          </section>

          <section className="panel section">
            <h2>Data &amp; storage</h2>
            <p className="lead">Where this Mac keeps the SQLite database and app files.</p>
            <StatusRows
              rows={[
                ["Data directory", status.app.data_dir, true],
                ["Database", status.app.database_path, true],
                ["Transactions", String(status.database.transaction_count)],
                ["Emails indexed", String(status.database.email_count)],
              ]}
            />
          </section>

          <CategoriesPage />
        </div>
      </div>
    </>
  );
}
