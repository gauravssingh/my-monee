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
        marginBottom: 24,
        background: "var(--surface)",
        border: "1px solid var(--line)",
        borderRadius: "var(--radius-lg)",
        padding: "18px 20px",
        boxShadow: "0 2px 8px rgba(0,0,0,0.03)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14, flexWrap: "wrap", gap: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: "1.2rem" }}>⚡</span>
          <h3 style={{ margin: 0, fontSize: "1.05rem", fontWeight: 700 }}>
            Ledger Intelligence &amp; Anomaly Signals
          </h3>
          {totalAlerts > 0 && (
            <span className="badge warn" style={{ fontSize: "0.75rem", padding: "2px 7px" }}>
              {totalAlerts} New
            </span>
          )}
        </div>

        {/* Tab switcher */}
        <div style={{ display: "flex", gap: 6 }}>
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
            }}
          >
            Duplicates Queue ({duplicates.length})
          </button>
        </div>
      </div>

      {loading ? (
        <div style={{ padding: "16px 0", color: "var(--ink-muted)", fontSize: "0.85rem" }}>
          Scanning ledger signals…
        </div>
      ) : activeTab === "anomalies" ? (
        anomalies.length === 0 ? (
          <div style={{ padding: "16px 0", color: "var(--ink-muted)", fontSize: "0.85rem" }}>
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
                      onClick={() => onTransactionClick(a.transaction_id!)}
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
        <div style={{ padding: "16px 0", color: "var(--ink-muted)", fontSize: "0.85rem" }}>
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
  );
}
