import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api } from "../api";
import { formatMoney } from "../format";
import { useBackdropClose, useModalChrome } from "../hooks/useModalChrome";

interface DuplicateItem {
  primary_id: string;
  duplicate_id: string;
  confidence: number;
  reason: string;
  amount: number;
  currency: string;
  primary_merchant?: string | null;
  duplicate_merchant?: string | null;
  primary_date: string;
  duplicate_date: string;
  primary_source: string;
  duplicate_source: string;
  time_diff_seconds: number;
}

interface AnomalyItem {
  id: string;
  anomaly_type: string;
  severity: "high" | "medium" | "low";
  title: string;
  description: string;
  amount: number;
  currency: string;
  transaction_id?: string | null;
  date: string;
  merchant?: string | null;
  category?: string | null;
  metadata: Record<string, any>;
}

interface LedgerIntelligencePanelProps {
  onShowToast?: (msg: string, type?: "success" | "error") => void;
  onTransactionClick?: (txId: string) => void;
}

export default function LedgerIntelligencePanel({
  onShowToast,
  onTransactionClick,
}: LedgerIntelligencePanelProps) {
  const [duplicates, setDuplicates] = useState<DuplicateItem[]>([]);
  const [anomalies, setAnomalies] = useState<AnomalyItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [actioningId, setActioningId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"anomalies" | "duplicates">("anomalies");

  const panelRef = useRef<HTMLDivElement>(null);
  const titleId = useId();

  useModalChrome(isModalOpen, () => setIsModalOpen(false), panelRef);
  const handleBackdropClick = useBackdropClose(isModalOpen, () => setIsModalOpen(false));

  const loadData = () => {
    setLoading(true);
    Promise.all([
      api.getDuplicateCandidates(90).catch(() => []),
      api.getSpendingAnomalies(60).catch(() => []),
    ])
      .then(([dups, anoms]) => {
        setDuplicates(dups);
        setAnomalies(anoms);
        if (anoms.length === 0 && dups.length > 0) {
          setActiveTab("duplicates");
        }
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadData();
  }, []);

  useEffect(() => {
    const handleSync = () => {
      loadData();
    };
    window.addEventListener("mymonee:sync-completed", handleSync);
    return () => window.removeEventListener("mymonee:sync-completed", handleSync);
  }, []);

  const handleMergeDuplicate = async (primaryId: string, duplicateId: string) => {
    setActioningId(duplicateId);
    try {
      await api.mergeDuplicate(primaryId, duplicateId);
      onShowToast?.("Duplicate transaction merged and excluded from spending.", "success");
      setDuplicates((prev) => prev.filter((d) => d.duplicate_id !== duplicateId));
    } catch (err: any) {
      onShowToast?.(`Merge failed: ${err.message || "Unknown error"}`, "error");
    } finally {
      setActioningId(null);
    }
  };

  const handleDismissDuplicate = (duplicateId: string) => {
    setDuplicates((prev) => prev.filter((d) => d.duplicate_id !== duplicateId));
    onShowToast?.("Duplicate candidate dismissed.", "success");
  };

  const totalAlerts = anomalies.length + duplicates.length;

  if (!loading && totalAlerts === 0) {
    return null; // Clean state: don't clutter UI when all clean
  }

  return (
    <>
      {/* Banner trigger bar on page */}
      <div
        onClick={() => setIsModalOpen(true)}
        role="button"
        tabIndex={0}
        aria-haspopup="dialog"
        aria-expanded={isModalOpen}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setIsModalOpen(true);
          }
        }}
        style={{
          marginBottom: 20,
          background: "var(--surface)",
          border: "1px solid var(--line)",
          borderRadius: "var(--radius-lg)",
          padding: "12px 18px",
          boxShadow: "0 2px 8px rgba(0,0,0,0.03)",
          cursor: "pointer",
          userSelect: "none",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
          flexWrap: "wrap",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", minWidth: 0 }}>
          <span style={{ fontSize: "1.15rem" }}>⚡</span>
          <h3 style={{ margin: 0, fontSize: "0.98rem", fontWeight: 700, color: "var(--ink)" }}>
            Ledger Intelligence &amp; Anomaly Signals
          </h3>
          {totalAlerts > 0 && (
            <span
              className="badge warn"
              style={{
                fontSize: "0.72rem",
                padding: "2px 8px",
                fontWeight: 600,
                borderRadius: 12,
                whiteSpace: "nowrap",
              }}
            >
              {totalAlerts} Alert{totalAlerts !== 1 ? "s" : ""}
            </span>
          )}
          {totalAlerts > 0 && (
            <span style={{ fontSize: "0.80rem", color: "var(--ink-muted)", whiteSpace: "nowrap" }}>
              ({anomalies.length} spending surge{anomalies.length !== 1 ? "s" : ""} • {duplicates.length} duplicate candidate{duplicates.length !== 1 ? "s" : ""})
            </span>
          )}
        </div>

        <button
          type="button"
          className="btn quiet"
          onClick={(e) => {
            e.stopPropagation();
            setIsModalOpen(true);
          }}
          style={{
            fontSize: "0.80rem",
            padding: "4px 10px",
            color: "var(--ink-muted)",
            display: "inline-flex",
            alignItems: "center",
            gap: 4,
            fontWeight: 600,
          }}
        >
          <span>View Alerts</span>
          <span style={{ fontSize: "0.9rem" }}>→</span>
        </button>
      </div>

      {/* Ledger Intelligence Modal */}
      {isModalOpen &&
        createPortal(
          <div className="modal-backdrop" onClick={handleBackdropClick} role="presentation">
            <div
              ref={panelRef}
              className="modal-panel"
              role="dialog"
              aria-modal="true"
              aria-labelledby={titleId}
              style={{
                width: "min(760px, 100%)",
                maxHeight: "min(88vh, 850px)",
                display: "flex",
                flexDirection: "column",
              }}
            >
              <div
                className="sheet-handle"
                onClick={() => setIsModalOpen(false)}
                aria-label="Dismiss sheet"
              />

              <header className="modal-header">
                <div style={{ minWidth: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                    <span style={{ fontSize: "1.1rem" }}>⚡</span>
                    <h2 id={titleId} style={{ margin: 0, fontSize: "1.15rem" }}>
                      Ledger Intelligence
                    </h2>
                    {totalAlerts > 0 && (
                      <span
                        className="badge warn"
                        style={{
                          fontSize: "0.72rem",
                          padding: "2px 8px",
                          fontWeight: 600,
                          borderRadius: 12,
                        }}
                      >
                        {totalAlerts} Alert{totalAlerts !== 1 ? "s" : ""}
                      </span>
                    )}
                  </div>
                  <p className="lead" style={{ margin: "4px 0 0", fontSize: "0.82rem" }}>
                    Automated anomaly detection, duplicate spending candidates, and ledger signals.
                  </p>
                </div>
                <button
                  type="button"
                  className="btn icon-btn quiet"
                  onClick={() => setIsModalOpen(false)}
                  aria-label="Close modal"
                  style={{ fontSize: "1.1rem", lineHeight: 1, padding: "4px 8px" }}
                >
                  ✕
                </button>
              </header>

              {/* Tab Navigation */}
              <div
                style={{
                  display: "flex",
                  gap: 8,
                  padding: "10px 20px",
                  borderBottom: "1px solid var(--line)",
                  background: "var(--surface)",
                  overflowX: "auto",
                  flexShrink: 0,
                }}
              >
                <button
                  type="button"
                  className={`btn quiet ${activeTab === "anomalies" ? "active" : ""}`}
                  onClick={() => setActiveTab("anomalies")}
                  style={{
                    fontSize: "0.80rem",
                    padding: "5px 12px",
                    fontWeight: 600,
                    background: activeTab === "anomalies" ? "var(--accent-soft)" : "transparent",
                    color: activeTab === "anomalies" ? "var(--accent)" : "var(--ink-muted)",
                    borderRadius: "var(--radius)",
                    whiteSpace: "nowrap",
                  }}
                >
                  Spending Surges ({anomalies.length})
                </button>
                <button
                  type="button"
                  className={`btn quiet ${activeTab === "duplicates" ? "active" : ""}`}
                  onClick={() => setActiveTab("duplicates")}
                  style={{
                    fontSize: "0.80rem",
                    padding: "5px 12px",
                    fontWeight: 600,
                    background: activeTab === "duplicates" ? "var(--accent-soft)" : "transparent",
                    color: activeTab === "duplicates" ? "var(--accent)" : "var(--ink-muted)",
                    borderRadius: "var(--radius)",
                    whiteSpace: "nowrap",
                  }}
                >
                  Duplicates Queue ({duplicates.length})
                </button>
              </div>

              {/* Scrollable Content Body */}
              <div
                className="modal-body"
                style={{
                  padding: "16px 20px",
                  overflowY: "auto",
                  flex: 1,
                  minHeight: 0,
                  WebkitOverflowScrolling: "touch",
                }}
              >
                {loading ? (
                  <div style={{ padding: "24px 0", textAlign: "center", color: "var(--ink-muted)", fontSize: "0.85rem" }}>
                    Scanning ledger signals…
                  </div>
                ) : activeTab === "anomalies" ? (
                  anomalies.length === 0 ? (
                    <div style={{ padding: "24px 0", textAlign: "center", color: "var(--ink-muted)", fontSize: "0.85rem" }}>
                      ✓ No spending spikes or subscription price hikes detected in the last 60 days.
                    </div>
                  ) : (
                    <div
                      style={{
                        display: "grid",
                        gridTemplateColumns: "repeat(auto-fit, minmax(min(280px, 100%), 1fr))",
                        gap: 12,
                      }}
                    >
                      {anomalies.map((a) => (
                        <div
                          key={a.id}
                          style={{
                            padding: "14px 16px",
                            background: "var(--surface-muted)",
                            border: "1px solid var(--line)",
                            borderRadius: "var(--radius-md)",
                            display: "flex",
                            flexDirection: "column",
                            justifyContent: "space-between",
                            gap: 10,
                            minWidth: 0,
                            boxSizing: "border-box",
                          }}
                        >
                          <div style={{ minWidth: 0 }}>
                            <div
                              style={{
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "space-between",
                                gap: 8,
                                marginBottom: 6,
                                flexWrap: "wrap",
                              }}
                            >
                              <span
                                style={{
                                  fontSize: "0.72rem",
                                  fontWeight: 700,
                                  textTransform: "uppercase",
                                  color: a.severity === "high" ? "var(--danger)" : "var(--warn)",
                                }}
                              >
                                {a.anomaly_type.replace(/_/g, " ")}
                              </span>
                              <span style={{ fontSize: "0.75rem", color: "var(--ink-muted)", whiteSpace: "nowrap" }}>
                                {new Date(a.date).toLocaleDateString("en-IN", { month: "short", day: "numeric" })}
                              </span>
                            </div>
                            <div
                              style={{
                                fontWeight: 600,
                                fontSize: "0.92rem",
                                color: "var(--ink)",
                                marginBottom: 4,
                                wordBreak: "break-word",
                              }}
                            >
                              {a.title}
                            </div>
                            <div
                              style={{
                                fontSize: "0.80rem",
                                color: "var(--ink-muted)",
                                lineHeight: 1.4,
                                wordBreak: "break-word",
                              }}
                            >
                              {a.description}
                            </div>
                          </div>

                          <div
                            style={{
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "space-between",
                              gap: 8,
                              marginTop: 4,
                              flexWrap: "wrap",
                            }}
                          >
                            <span
                              style={{
                                fontWeight: 700,
                                fontFamily: "var(--font-mono, monospace)",
                                fontSize: "0.95rem",
                              }}
                            >
                              {formatMoney(a.amount)}
                            </span>
                            {a.transaction_id && onTransactionClick && (
                              <button
                                type="button"
                                className="btn quiet"
                                onClick={() => {
                                  setIsModalOpen(false);
                                  onTransactionClick(a.transaction_id!);
                                }}
                                style={{ fontSize: "0.75rem", padding: "3px 8px" }}
                              >
                                Inspect Tx →
                              </button>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )
                ) : duplicates.length === 0 ? (
                  <div style={{ padding: "24px 0", textAlign: "center", color: "var(--ink-muted)", fontSize: "0.85rem" }}>
                    ✓ No multi-provider duplicate transactions detected in the last 90 days.
                  </div>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                    {duplicates.map((d) => (
                      <div
                        key={`${d.primary_id}-${d.duplicate_id}`}
                        style={{
                          padding: "14px 16px",
                          background: "var(--surface-muted)",
                          border: "1px solid var(--line)",
                          borderRadius: "var(--radius-md)",
                          display: "flex",
                          flexDirection: "column",
                          gap: 12,
                          minWidth: 0,
                          boxSizing: "border-box",
                        }}
                      >
                        <div style={{ minWidth: 0 }}>
                          <div
                            style={{
                              display: "flex",
                              alignItems: "center",
                              gap: 8,
                              flexWrap: "wrap",
                              marginBottom: 6,
                            }}
                          >
                            <span
                              style={{
                                fontWeight: 700,
                                fontSize: "0.95rem",
                                color: "var(--ink)",
                                wordBreak: "break-word",
                              }}
                            >
                              {d.primary_merchant || "Unknown Merchant"}
                            </span>
                            <span className="badge warn" style={{ fontSize: "0.70rem", whiteSpace: "nowrap" }}>
                              {Math.round(d.confidence * 100)}% Match
                            </span>
                            <span
                              style={{
                                fontWeight: 700,
                                fontFamily: "var(--font-mono, monospace)",
                                fontSize: "0.95rem",
                                marginLeft: "auto",
                              }}
                            >
                              {formatMoney(d.amount)}
                            </span>
                          </div>
                          <div
                            style={{
                              fontSize: "0.82rem",
                              color: "var(--ink-muted)",
                              lineHeight: 1.4,
                              wordBreak: "break-word",
                            }}
                          >
                            {d.reason}
                          </div>
                          <div
                            style={{
                              fontSize: "0.75rem",
                              color: "var(--ink-muted)",
                              marginTop: 6,
                              wordBreak: "break-word",
                            }}
                          >
                            Sources: <strong>{d.primary_source}</strong> vs{" "}
                            <strong>{d.duplicate_source}</strong>
                          </div>
                        </div>

                        <div
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: 8,
                            flexWrap: "wrap",
                            justifyContent: "flex-end",
                          }}
                        >
                          <button
                            type="button"
                            className="btn quiet"
                            onClick={() => handleDismissDuplicate(d.duplicate_id)}
                            style={{ fontSize: "0.80rem", padding: "6px 12px" }}
                          >
                            Dismiss / Keep Both
                          </button>
                          <button
                            type="button"
                            className="btn primary"
                            disabled={actioningId === d.duplicate_id}
                            onClick={() => void handleMergeDuplicate(d.primary_id, d.duplicate_id)}
                            style={{ fontSize: "0.80rem", padding: "6px 14px", fontWeight: 600 }}
                          >
                            {actioningId === d.duplicate_id ? "Merging…" : "Merge as Duplicate"}
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Modal Footer */}
              <footer
                className="modal-footer"
                style={{
                  padding: "12px 20px",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  flexShrink: 0,
                }}
              >
                <span style={{ fontSize: "0.78rem", color: "var(--ink-muted)" }}>
                  {activeTab === "anomalies"
                    ? `${anomalies.length} surge signal${anomalies.length !== 1 ? "s" : ""} in past 60 days`
                    : `${duplicates.length} duplicate candidate${duplicates.length !== 1 ? "s" : ""} in past 90 days`}
                </span>
                <button
                  type="button"
                  className="btn quiet"
                  onClick={() => setIsModalOpen(false)}
                  style={{ fontSize: "0.82rem", padding: "6px 14px" }}
                >
                  Done
                </button>
              </footer>
            </div>
          </div>,
          document.body
        )}
    </>
  );
}
