import { useEffect, useState } from "react";
import { api, SystemStatus } from "../../api";

interface DataStorageSettingsProps {
  status: SystemStatus;
  onShowToast: (msg: string, type?: "success" | "error") => void;
}

interface DBHealth {
  healthy: boolean;
  integrity_ok: boolean;
  foreign_keys_ok: boolean;
  database_size_bytes: number;
  wal_size_bytes: number;
  total_disk_bytes: number;
  page_count: number;
  page_size: number;
  freelist_pages: number;
  fragmentation_pct: number;
  table_metrics: Record<string, number>;
}

interface BackupItem {
  filename: string;
  path: string;
  size_bytes: number;
  created_at: string;
  integrity_verified: boolean;
  note?: string | null;
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
}

export default function DataStorageSettings({ status, onShowToast }: DataStorageSettingsProps) {
  const [health, setHealth] = useState<DBHealth | null>(null);
  const [backups, setBackups] = useState<BackupItem[]>([]);
  const [loadingBackups, setLoadingBackups] = useState(true);
  const [vacuuming, setVacuuming] = useState(false);
  const [creatingBackup, setCreatingBackup] = useState(false);
  const [restoringFilename, setRestoringFilename] = useState<string | null>(null);
  const [confirmRestore, setConfirmRestore] = useState<string | null>(null);

  const loadData = () => {
    setLoadingBackups(true);
    api.dbHealth()
      .then(setHealth)
      .catch((err) => console.error("Failed to load DB health:", err));

    api.listBackups()
      .then(setBackups)
      .catch((err) => console.error("Failed to list backups:", err))
      .finally(() => setLoadingBackups(false));
  };

  useEffect(() => {
    loadData();
  }, []);

  function copyText(text: string, label: string) {
    void navigator.clipboard.writeText(text);
    onShowToast(`${label} copied to clipboard`, "success");
  }

  const handleVacuum = async () => {
    setVacuuming(true);
    try {
      const res = await api.dbVacuum();
      setHealth(res.health);
      onShowToast(
        `Database optimized successfully! Reclaimed ${formatBytes(res.reclaimed_bytes)} disk space.`,
        "success"
      );
    } catch (err: any) {
      onShowToast(`Optimization failed: ${err.message || "Unknown error"}`, "error");
    } finally {
      setVacuuming(false);
    }
  };

  const handleCreateBackup = async () => {
    setCreatingBackup(true);
    try {
      await api.createBackup("Manual snapshot");
      onShowToast("Backup snapshot created and verified successfully!", "success");
      const updated = await api.listBackups();
      setBackups(updated);
    } catch (err: any) {
      onShowToast(`Failed to create backup: ${err.message || "Unknown error"}`, "error");
    } finally {
      setCreatingBackup(false);
    }
  };

  const handleRestore = async (filename: string) => {
    setRestoringFilename(filename);
    try {
      const res = await api.restoreBackup(filename);
      onShowToast(
        `Ledger restored from ${filename}! (Pre-restore safety snapshot created: ${res.safety_backup || "verified"})`,
        "success"
      );
      setConfirmRestore(null);
      loadData();
    } catch (err: any) {
      onShowToast(`Restore failed: ${err.message || "Unknown error"}`, "error");
    } finally {
      setRestoringFilename(null);
    }
  };

  const handleDeleteBackup = async (filename: string) => {
    if (!window.confirm(`Delete backup snapshot "${filename}"?`)) return;
    try {
      await api.deleteBackup(filename);
      onShowToast("Backup snapshot deleted.", "success");
      setBackups((prev) => prev.filter((b) => b.filename !== filename));
    } catch (err: any) {
      onShowToast(`Failed to delete backup: ${err.message || "Unknown error"}`, "error");
    }
  };

  return (
    <div className="settings-section-container">
      <div className="settings-section-header">
        <h2>Data, Storage &amp; Backups</h2>
        <p className="lead">
          Manage your durable SQLite database, create point-in-time backup snapshots, inspect database health, and export ledger archives.
        </p>
      </div>

      {/* 1. Database Health & Diagnostics */}
      <div className="settings-card">
        <div className="settings-card-topbar">
          <span className="settings-status-title">SQLite Database Health &amp; Storage</span>
          <span className={`badge ${health?.healthy ? "ok" : "warn"}`}>
            {health?.healthy ? "● Verified & Healthy" : "● Integrity Warning"}
          </span>
        </div>

        <div className="settings-meta-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 14 }}>
          <div className="settings-meta-item">
            <span className="meta-label">Total Disk Footprint</span>
            <span className="meta-value" style={{ fontSize: "1.2rem", fontWeight: 700 }}>
              {health ? formatBytes(health.total_disk_bytes) : "—"}
            </span>
            <span style={{ fontSize: "0.75rem", color: "var(--ink-muted)", marginTop: 2 }}>
              DB: {health ? formatBytes(health.database_size_bytes) : "—"} · WAL: {health ? formatBytes(health.wal_size_bytes) : "—"}
            </span>
          </div>

          <div className="settings-meta-item">
            <span className="meta-label">Integrity Status</span>
            <span className="meta-value" style={{ color: health?.integrity_ok ? "var(--credit)" : "var(--danger)" }}>
              {health?.integrity_ok ? "PRAGMA ok" : "Check Failed"}
            </span>
            <span style={{ fontSize: "0.75rem", color: "var(--ink-muted)", marginTop: 2 }}>
              Foreign Keys: {health?.foreign_keys_ok ? "Valid" : "Violations"}
            </span>
          </div>

          <div className="settings-meta-item">
            <span className="meta-label">Database Pages</span>
            <span className="meta-value">
              {health?.page_count.toLocaleString() || 0} pages
            </span>
            <span style={{ fontSize: "0.75rem", color: "var(--ink-muted)", marginTop: 2 }}>
              Free Pages: {health?.freelist_pages || 0} ({health?.fragmentation_pct || 0}% fragmentation)
            </span>
          </div>

          <div className="settings-meta-item">
            <span className="meta-label">Transactions &amp; Records</span>
            <span className="meta-value" style={{ fontSize: "1.2rem", fontWeight: 700 }}>
              {health?.table_metrics.transactions?.toLocaleString() || status.database.transaction_count.toLocaleString()}
            </span>
            <span style={{ fontSize: "0.75rem", color: "var(--ink-muted)", marginTop: 2 }}>
              Emails: {health?.table_metrics.emails || status.database.email_count} · Rules: {health?.table_metrics.rules || 0}
            </span>
          </div>
        </div>

        {/* Vacuum Action Bar */}
        <div style={{ marginTop: 18, paddingTop: 16, borderTop: "1px solid var(--line)", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 10 }}>
          <div style={{ fontSize: "0.84rem", color: "var(--ink-muted)" }}>
            Perform a WAL checkpoint, reclaim free pages, and optimize B-Tree indexes.
          </div>
          <button
            type="button"
            className="btn quiet"
            disabled={vacuuming}
            onClick={() => void handleVacuum()}
            style={{ fontWeight: 600, display: "inline-flex", alignItems: "center", gap: 6 }}
          >
            <span>🧹</span>
            <span>{vacuuming ? "Vacuuming…" : "Vacuum & Optimize DB"}</span>
          </button>
        </div>
      </div>

      {/* 2. Automated Point-in-Time Backup Snapshots */}
      <div className="settings-card">
        <div className="settings-card-topbar">
          <span className="settings-status-title">Point-in-Time Backup Snapshots</span>
          <button
            type="button"
            className="btn primary"
            disabled={creatingBackup}
            onClick={() => void handleCreateBackup()}
            style={{ height: 34, padding: "0 14px", fontSize: "0.85rem", fontWeight: 600, display: "inline-flex", alignItems: "center", gap: 6 }}
          >
            <span>📸</span>
            <span>{creatingBackup ? "Creating Snapshot…" : "Create Backup Now"}</span>
          </button>
        </div>

        <p style={{ color: "var(--ink-muted)", fontSize: "0.86rem", margin: "0 0 16px 0" }}>
          Consistent online SQLite snapshots created safely without locking active database writes.
        </p>

        {loadingBackups ? (
          <div style={{ padding: 20, textAlign: "center", color: "var(--ink-muted)" }}>Loading backup snapshots…</div>
        ) : backups.length === 0 ? (
          <div style={{ padding: 24, textAlign: "center", background: "var(--surface-muted)", borderRadius: "var(--radius-sm)", color: "var(--ink-muted)", fontSize: "0.88rem" }}>
            No backup snapshots yet. Click <strong>"Create Backup Now"</strong> above to generate your first point-in-time snapshot.
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8, maxHeight: 380, overflowY: "auto" }}>
            {backups.map((b) => (
              <div
                key={b.filename}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "12px 14px",
                  background: "var(--surface)",
                  border: "1px solid var(--line)",
                  borderRadius: "var(--radius-sm)",
                  flexWrap: "wrap",
                  gap: 10,
                }}
              >
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontWeight: 600, fontSize: "0.90rem", fontFamily: "var(--font-mono, monospace)" }}>
                      {b.filename}
                    </span>
                    <span className="badge ok" style={{ fontSize: "0.70rem" }}>Verified</span>
                  </div>
                  <div style={{ fontSize: "0.78rem", color: "var(--ink-muted)", marginTop: 2 }}>
                    {new Date(b.created_at).toLocaleString()} · {formatBytes(b.size_bytes)} {b.note ? `· ${b.note}` : ""}
                  </div>
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <a
                    href={`/api/system/backups/download/${encodeURIComponent(b.filename)}`}
                    className="btn quiet"
                    download={b.filename}
                    style={{ textDecoration: "none", fontSize: "0.80rem", padding: "5px 10px", height: "auto" }}
                    title="Download .db snapshot"
                  >
                    ⬇ Download
                  </a>
                  <button
                    type="button"
                    className="btn quiet"
                    onClick={() => setConfirmRestore(b.filename)}
                    style={{ fontSize: "0.80rem", padding: "5px 10px", height: "auto", color: "var(--accent)" }}
                    title="Restore ledger to this point in time"
                  >
                    ↺ Restore
                  </button>
                  <button
                    type="button"
                    className="btn quiet"
                    onClick={() => void handleDeleteBackup(b.filename)}
                    style={{ fontSize: "0.80rem", padding: "5px 10px", height: "auto", color: "var(--danger)" }}
                    title="Delete snapshot"
                  >
                    🗑
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Confirmation Modal for Restore */}
      {confirmRestore && (
        <div className="modal-backdrop" style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000, padding: 16 }}>
          <div className="surface" style={{ maxWidth: 480, width: "100%", padding: 24, borderRadius: "var(--radius-md)", border: "1px solid var(--line)" }}>
            <h3 style={{ margin: "0 0 10px 0", color: "var(--danger)" }}>
              ⚠️ Restore Ledger Snapshot?
            </h3>
            <p style={{ fontSize: "0.88rem", color: "var(--ink)", lineHeight: 1.5, margin: "0 0 14px 0" }}>
              Are you sure you want to restore the ledger from <strong>{confirmRestore}</strong>?
            </p>
            <p style={{ fontSize: "0.82rem", color: "var(--ink-muted)", margin: "0 0 20px 0" }}>
              A pre-restore safety snapshot of your current database will be generated automatically before restoring.
            </p>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
              <button
                type="button"
                className="btn quiet"
                disabled={Boolean(restoringFilename)}
                onClick={() => setConfirmRestore(null)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn primary"
                disabled={Boolean(restoringFilename)}
                onClick={() => void handleRestore(confirmRestore)}
                style={{ background: "var(--danger)" }}
              >
                {restoringFilename ? "Restoring Ledger…" : "Confirm & Restore"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 3. Portability & JSON Export */}
      <div className="settings-card">
        <div className="settings-section-header" style={{ marginBottom: 12 }}>
          <h3 style={{ margin: "0 0 4px", fontSize: "1rem" }}>Data Portability &amp; JSON Export</h3>
          <p className="lead" style={{ margin: 0, fontSize: "0.82rem" }}>
            Export all accounts, transactions, classification rules, categories, and settings as a portable JSON archive.
          </p>
        </div>

        <div className="settings-row">
          <div className="settings-row-info">
            <div className="settings-row-label">Export Full Archive</div>
            <div className="settings-row-desc">Generates a clean JSON export bundle for backup or migration.</div>
          </div>
          <div className="settings-row-value">
            <a
              href="/api/system/export-bundle"
              className="btn quiet"
              download="mymonee_ledger_export.json"
              style={{ textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 6, fontWeight: 600 }}
            >
              <span>📦</span>
              <span>Export JSON Bundle</span>
            </a>
          </div>
        </div>
      </div>

      {/* 4. Filesystem Paths */}
      <div className="settings-card">
        <div className="settings-section-header" style={{ marginBottom: 12 }}>
          <h3 style={{ margin: "0 0 4px", fontSize: "1rem" }}>Storage Locations</h3>
          <p className="lead" style={{ margin: 0, fontSize: "0.82rem" }}>
            Local filesystem paths on this Mac.
          </p>
        </div>

        <div className="settings-row">
          <div className="settings-row-info">
            <div className="settings-row-label">Data Directory</div>
            <div className="settings-row-desc">Application data and backup snapshots folder.</div>
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
    </div>
  );
}
