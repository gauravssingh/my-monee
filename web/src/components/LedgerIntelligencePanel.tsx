import { useEffect, useState } from "react";
import { api } from "../api";
import { formatMoney } from "../format";

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
  const [isExpanded, setIsExpanded] = useState<boolean>(false);
  const [actioningId, setActioningId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"anomalies" | "duplicates">("anomalies");

  const loadData = () => {
    setLoading(true);
    Promise.all([
      api.getDuplicateCandidates(90).catch(() => []),
      api.getSpendingAnomalies(60).catch(() => []),
    ])
      .then(([dups, anoms]) => {
        setDuplicates(dups);
        setAnomalies(anoms);
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadData();
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
    <div
      style={{
        marginBottom: 20,
        background: "var(--surface)",
        border: "1px solid var(--line)",
        borderRadius: "var(--radius-lg)",
        padding: isExpanded ? "16px 20px" : "12px 18px",
        boxShadow: "0 2px 8px rgba(0,0,0,0.03)",
        transition: "all 0.2s ease-in-out",
      }}
    >
      {/* Header bar (always visible, clickable to toggle) */}
      <div
        onClick={() => setIsExpanded((prev) => !prev)}
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          cursor: "pointer",
          userSelect: "none",
          gap: 12,
          flexWrap: "wrap",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
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
              }}
            >
              {totalAlerts} Alert{totalAlerts !== 1 ? "s" : ""}
            </span>
          )}
          {!isExpanded && totalAlerts > 0 && (
            <span style={{ fontSize: "0.80rem", color: "var(--ink-muted)" }}>
              ({anomalies.length} spending surge{anomalies.length !== 1 ? "s" : ""} • {duplicates.length} duplicate candidate{duplicates.length !== 1 ? "s" : ""})
            </span>
          )}
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          {isExpanded && (
            /* Tab switcher when expanded */
            <div
              style={{ display: "flex", gap: 4 }}
              onClick={(e) => e.stopPropagation()}
            >
              <button
                type="button"
                className={`btn quiet ${activeTab === "anomalies" ? "active" : ""}`}
                onClick={() => setActiveTab("anomalies")}
                style={{
                  fontSize: "0.78rem",
                  padding: "4px 10px",
                  fontWeight: 600,
                  background: activeTab === "anomalies" ? "var(--accent-soft)" : "transparent",
                  color: activeTab === "anomalies" ? "var(--accent)" : "var(--ink-muted)",
                  borderRadius: "var(--radius)",
                }}
              >
                Spending Surges ({anomalies.length})
              </button>
              <button
                type="button"
                className={`btn quiet ${activeTab === "duplicates" ? "active" : ""}`}
                onClick={() => setActiveTab("duplicates")}
                style={{
                  fontSize: "0.78rem",
                  padding: "4px 10px",
                  fontWeight: 600,
                  background: activeTab === "duplicates" ? "var(--accent-soft)" : "transparent",
                  color: activeTab === "duplicates" ? "var(--accent)" : "var(--ink-muted)",
                  borderRadius: "var(--radius)",
                }}
              >
                Duplicates Queue ({duplicates.length})
              </button>
            </div>
          )}

          <button
            type="button"
            className="btn quiet"
            style={{
              fontSize: "0.80rem",
              padding: "4px 8px",
              color: "var(--ink-muted)",
              display: "flex",
              alignItems: "center",
              gap: 4,
            }}
          >
            <span>{isExpanded ? "Collapse" : "View"}</span>
            <span style={{ fontSize: "0.9rem" }}>{isExpanded ? "▴" : "▾"}</span>
          </button>
        </div>
      </div>

      {/* Expandable Content Body */}
      {isExpanded && (
        <div style={{ marginTop: 14, borderTop: "1px solid var(--line)", paddingTop: 14 }}>
          {loading ? (
            <div style={{ padding: "16px 0", color: "var(--ink-muted)", fontSize: "0.85rem" }}>
              Scanning ledger signals…
            </div>
          ) : activeTab === "anomalies" ? (
            anomalies.length === 0 ? (
              <div style={{ padding: "12px 0", color: "var(--ink-muted)", fontSize: "0.85rem" }}>
                ✓ No spending spikes or subscription price hikes detected in the last 60 days.
              </div>
            ) : (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 10 }}>
                {anomalies.map((a) => (
                  <div
                    key={a.id}
                    style={{
                      padding: "12px 14px",
                      background: "var(--surface-muted)",
                      border: "1px solid var(--line)",
                      borderRadius: "var(--radius-md)",
                      display: "flex",
                      flexDirection: "column",
                      justifyContent: "space-between",
                      gap: 8,
                    }}
                  >
                    <div>
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
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
                        <span style={{ fontSize: "0.75rem", color: "var(--ink-muted)" }}>
                          {new Date(a.date).toLocaleDateString("en-IN", { month: "short", day: "numeric" })}
                        </span>
                      </div>
                      <div style={{ fontWeight: 600, fontSize: "0.90rem", color: "var(--ink)", marginBottom: 2 }}>
                        {a.title}
                      </div>
                      <div style={{ fontSize: "0.80rem", color: "var(--ink-muted)", lineHeight: 1.35 }}>
                        {a.description}
                      </div>
                    </div>

                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 4 }}>
                      <span style={{ fontWeight: 700, fontFamily: "var(--font-mono, monospace)", fontSize: "0.95rem" }}>
                        {formatMoney(a.amount)}
                      </span>
                      {a.transaction_id && onTransactionClick && (
                        <button
                          type="button"
                          className="btn quiet"
                          onClick={(e) => {
                            e.stopPropagation();
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
            <div style={{ padding: "12px 0", color: "var(--ink-muted)", fontSize: "0.85rem" }}>
              ✓ No multi-provider duplicate transactions detected in the last 90 days.
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {duplicates.map((d) => (
                <div
                  key={`${d.primary_id}-${d.duplicate_id}`}
                  style={{
                    padding: "14px 16px",
                    background: "var(--surface-muted)",
                    border: "1px solid var(--line)",
                    borderRadius: "var(--radius-md)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    flexWrap: "wrap",
                    gap: 12,
                  }}
                >
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                      <span style={{ fontWeight: 700, fontSize: "0.95rem", color: "var(--ink)" }}>
                        {d.primary_merchant || "Unknown Merchant"}
                      </span>
                      <span className="badge warn" style={{ fontSize: "0.70rem" }}>
                        {Math.round(d.confidence * 100)}% Confidence Duplicate
                      </span>
                      <span style={{ fontWeight: 700, fontFamily: "var(--font-mono, monospace)", fontSize: "0.95rem", marginLeft: 4 }}>
                        {formatMoney(d.amount)}
                      </span>
                    </div>
                    <div style={{ fontSize: "0.80rem", color: "var(--ink-muted)", lineHeight: 1.35 }}>
                      {d.reason}
                    </div>
                    <div style={{ fontSize: "0.75rem", color: "var(--ink-muted)", marginTop: 4 }}>
                      Sources: <strong>{d.primary_source}</strong> vs <strong>{d.duplicate_source}</strong>
                    </div>
                  </div>

                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <button
                      type="button"
                      className="btn quiet"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDismissDuplicate(d.duplicate_id);
                      }}
                      style={{ fontSize: "0.80rem", padding: "6px 12px" }}
                    >
                      Dismiss / Keep Both
                    </button>
                    <button
                      type="button"
                      className="btn primary"
                      disabled={actioningId === d.duplicate_id}
                      onClick={(e) => {
                        e.stopPropagation();
                        void handleMergeDuplicate(d.primary_id, d.duplicate_id);
                      }}
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
      )}
    </div>
  );
}
