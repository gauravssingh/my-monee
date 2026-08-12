import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import { createPortal } from "react-dom";
import {
  api,
  type CategoryTree,
  type GmailStatus,
  type IngestionResult,
  type SystemStatus,
} from "../api";
import { formatDateTime } from "../format";
import { useConfirm } from "../hooks/useConfirm";

function CategoryDeleteButton({
  disabled,
  onConfirm,
}: {
  disabled: boolean;
  onConfirm: () => void;
}) {
  const { armed, trigger } = useConfirm(onConfirm);
  return (
    <button
      type="button"
      className={`category-delete-button${armed ? " armed" : ""}`}
      disabled={disabled}
      onClick={trigger}
      aria-label={armed ? "Confirm delete category" : "Delete category"}
      title={armed ? "Click again to confirm deletion" : "Delete category"}
    >
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M3 6h18" />
        <path d="M8 6V4h8v2" />
        <path d="M19 6l-1 14H6L5 6" />
        <path d="M10 11v5M14 11v5" />
      </svg>
    </button>
  );
}

function SubCategoryChip({
  name,
  disabled,
  onConfirm,
}: {
  name: string;
  disabled: boolean;
  onConfirm: () => void;
}) {
  const { armed, trigger } = useConfirm(onConfirm);
  return (
    <span className="sub-chip">
      {name}
      <button
        type="button"
        className={`sub-chip-x${armed ? " armed" : ""}`}
        title={armed ? `Click again to remove ${name}` : `Remove ${name}`}
        disabled={disabled}
        onClick={trigger}
      >
        ×
      </button>
    </span>
  );
}

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
  const [categories, setCategories] = useState<CategoryTree[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [lastRun, setLastRun] = useState<IngestionResult | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [parsedCreds, setParsedCreds] = useState<Record<string, any> | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const settingsStackRef = useRef<HTMLDivElement>(null);
  const [settingsStackHeight, setSettingsStackHeight] = useState<number>();
  const [newCategory, setNewCategory] = useState("");
  const [subdrafts, setSubdrafts] = useState<Record<string, string>>({});

  const refresh = useCallback(async () => {
    const [system, gmailStatus, cats] = await Promise.all([
      api.system(),
      api.gmailStatus(),
      api.categories(),
    ]);
    setStatus(system);
    setGmail(gmailStatus);
    setCategories(cats.items);
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



  async function addCategory() {
    if (!newCategory.trim()) return;
    setBusy("cat");
    setError(null);
    try {
      await api.createCategory(newCategory.trim());
      setNewCategory("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add category");
    } finally {
      setBusy(null);
    }
  }

  async function removeCategory(id: string) {
    setBusy(`del-cat-${id}`);
    setError(null);
    try {
      await api.deleteCategory(id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete category");
    } finally {
      setBusy(null);
    }
  }

  async function addSubcategory(categoryId: string) {
    const name = (subdrafts[categoryId] || "").trim();
    if (!name) return;
    setBusy(`sub-${categoryId}`);
    setError(null);
    try {
      await api.createSubcategory(categoryId, name);
      setSubdrafts((prev) => ({ ...prev, [categoryId]: "" }));
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add subcategory");
    } finally {
      setBusy(null);
    }
  }

  async function removeSubcategory(id: string) {
    setBusy(`del-sub-${id}`);
    setError(null);
    try {
      await api.deleteSubcategory(id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete subcategory");
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
                <div className="modal-panel" role="dialog" aria-modal="true" style={{ width: "min(1200px, 95vw)", display: "flex", flexDirection: "column", padding: 24, gap: 16 }}>
                  <h3 style={{ margin: 0 }}>Confirm OAuth Configuration</h3>
                  <div className="table-wrap" style={{ border: "1px solid var(--line)", borderRadius: 4, overflow: "auto" }}>
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
                  <div className="toolbar" style={{ justifyContent: "flex-end", marginTop: 8 }}>
                    <button
                      className="btn"
                      type="button"
                      disabled={busy !== null}
                      onClick={cancelCreds}
                    >
                      Cancel
                    </button>
                    <button
                      className="btn primary"
                      type="button"
                      disabled={busy !== null}
                      onClick={() => void saveCredentials()}
                    >
                      {busy === "creds" ? "Importing…" : "Confirm & Import"}
                    </button>
                  </div>
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
        </div>

        <section className="panel section settings-categories">
          <h2>Categories</h2>
          <p className="lead">
            Master list for auto-classification and review. Seeded defaults can be extended; custom
            categories can be removed if unused.
          </p>

          <div className="toolbar">
            <input
              className="input"
              placeholder="New category name"
              value={newCategory}
              onChange={(e) => setNewCategory(e.target.value)}
            />
            <button
              className="btn primary"
              type="button"
              disabled={busy !== null || !newCategory.trim()}
              onClick={() => void addCategory()}
            >
              {busy === "cat" ? "Adding…" : "Add category"}
            </button>
          </div>

          <div className="category-admin">
            {categories.map((cat) => (
              <div className="category-admin-item" key={cat.id}>
                <div className="category-admin-head">
                  <div>
                    <strong>{cat.name}</strong>
                    <span className="metric-hint">
                      {" "}
                      · {cat.subcategories.length} sub · {cat.transaction_count} txs
                      {cat.is_system ? " · system" : ""}
                    </span>
                  </div>
                  {!cat.is_system && (
                    <CategoryDeleteButton
                      disabled={busy !== null}
                      onConfirm={() => void removeCategory(cat.id)}
                    />
                  )}
                </div>
                <div className="category-admin-subs">
                  {cat.subcategories.map((sub) => (
                    <SubCategoryChip
                      key={sub.id}
                      name={sub.name}
                      disabled={busy !== null}
                      onConfirm={() => void removeSubcategory(sub.id)}
                    />
                  ))}
                </div>
                <div className="toolbar" style={{ marginTop: 8, marginBottom: 0 }}>
                  <input
                    className="input"
                    placeholder="Add subcategory"
                    value={subdrafts[cat.id] || ""}
                    onChange={(e) =>
                      setSubdrafts((prev) => ({ ...prev, [cat.id]: e.target.value }))
                    }
                  />
                  <button
                    className="btn"
                    type="button"
                    disabled={busy !== null || !(subdrafts[cat.id] || "").trim()}
                    onClick={() => void addSubcategory(cat.id)}
                  >
                    Add
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>

      </div>
    </>
  );
}
