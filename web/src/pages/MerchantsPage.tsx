import { useEffect, useMemo, useState } from "react";
import { api, type Merchant } from "../api";
import { formatMoney } from "../format";
import MerchantDetailsModal from "../components/MerchantDetailsModal";
import { useToast } from "../hooks/useToast";

export default function MerchantsPage() {
  const [merchants, setMerchants] = useState<Merchant[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const { showToast } = useToast();

  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [canonicalName, setCanonicalName] = useState("");
  const [mergeLoading, setMergeLoading] = useState(false);
  const [detailsMerchant, setDetailsMerchant] = useState<{ id: string; name: string } | null>(null);

  const fetchMerchants = () => {
    setLoading(true);
    api.getMerchants()
      .then((data) => setMerchants(data.items))
      .catch((err: Error) => showToast(err.message, "error"))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchMerchants();
  }, []);

  const toggleSelect = (id: string) => {
    const next = new Set(selectedIds);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    setSelectedIds(next);
  };

  const handleMerge = () => {
    if (selectedIds.size < 2 && merchants.find((m) => selectedIds.has(m.id))?.display_name === canonicalName) {
      showToast("Select at least 2 merchants to merge, or a different canonical name.", "error");
      return;
    }
    if (!canonicalName.trim()) {
      showToast("Please provide a canonical name.", "error");
      return;
    }

    setMergeLoading(true);
    api.mergeMerchants(Array.from(selectedIds), canonicalName)
      .then(() => {
        setSelectedIds(new Set());
        setCanonicalName("");
        fetchMerchants();
        showToast("Merchants successfully merged!", "success");
      })
      .catch((err: Error) => showToast("Failed to merge: " + err.message, "error"))
      .finally(() => setMergeLoading(false));
  };

  const filteredMerchants = useMemo(() => {
    const q = searchQuery.toLowerCase().trim();
    if (!q) return merchants;
    return merchants.filter(
      (m) =>
        m.display_name.toLowerCase().includes(q) ||
        (m.canonical_name && m.canonical_name.toLowerCase().includes(q)) ||
        m.aliases.some((a) => a.toLowerCase().includes(q))
    );
  }, [merchants, searchQuery]);

  const totalSpendOverall = useMemo(
    () => merchants.reduce((sum, m) => sum + (m.total_spent || 0), 0),
    [merchants]
  );
  const totalSpendLast30d = useMemo(
    () => merchants.reduce((sum, m) => sum + (m.spent_last_30d || 0), 0),
    [merchants]
  );

  if (loading && merchants.length === 0) return <div className="empty">Loading merchants...</div>;

  return (
    <>
      <header className="page-header">
        <div>
          <h1 className="page-title">Merchants</h1>
          <p className="lead">Manage normalized merchants, aliases, and track spending history.</p>
        </div>
      </header>

      {/* Summary KPI Cards */}
      <section className="metrics" style={{ marginBottom: 24, display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "16px" }}>
        <article className="panel metric" style={{ padding: "16px" }}>
          <div className="metric-label" style={{ fontSize: "0.8125rem", color: "var(--ink-muted)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "6px" }}>
            Tracked Merchants
          </div>
          <div className="metric-value" style={{ fontSize: "1.6rem", fontWeight: 600 }}>
            {merchants.length}
          </div>
          <div className="metric-hint" style={{ fontSize: "0.8125rem", color: "var(--ink-muted)", marginTop: "4px" }}>
            Total unique entities
          </div>
        </article>

        <article className="panel metric" style={{ padding: "16px" }}>
          <div className="metric-label" style={{ fontSize: "0.8125rem", color: "var(--ink-muted)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "6px" }}>
            Last 30 Days Spend
          </div>
          <div className="metric-value" style={{ fontSize: "1.6rem", fontWeight: 600, color: "var(--ink)" }}>
            {formatMoney(totalSpendLast30d, "INR")}
          </div>
          <div className="metric-hint" style={{ fontSize: "0.8125rem", color: "var(--ink-muted)", marginTop: "4px" }}>
            Past 30 days debit total
          </div>
        </article>

        <article className="panel metric" style={{ padding: "16px" }}>
          <div className="metric-label" style={{ fontSize: "0.8125rem", color: "var(--ink-muted)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "6px" }}>
            Overall Spend
          </div>
          <div className="metric-value" style={{ fontSize: "1.6rem", fontWeight: 600, color: "var(--ink)" }}>
            {formatMoney(totalSpendOverall, "INR")}
          </div>
          <div className="metric-hint" style={{ fontSize: "0.8125rem", color: "var(--ink-muted)", marginTop: "4px" }}>
            Lifetime recorded volume
          </div>
        </article>
      </section>

      {selectedIds.size > 0 && (
        <div className="review-action-bar" role="region" aria-label="Merge merchants">
          <div>Selected <strong>{selectedIds.size}</strong> merchants to merge.</div>
          <div className="review-action-buttons">
            <input 
              type="text" 
              placeholder="Canonical Name (e.g. Amazon)" 
              value={canonicalName}
              onChange={(e) => setCanonicalName(e.target.value)}
              className="input"
              style={{ minWidth: 220 }}
            />
            <button className="btn primary" onClick={handleMerge} disabled={mergeLoading || !canonicalName.trim()}>
              {mergeLoading ? "Merging…" : "Merge Selected"}
            </button>
            <button className="btn quiet" onClick={() => { setSelectedIds(new Set()); setCanonicalName(""); }}>
              Clear
            </button>
          </div>
        </div>
      )}

      <div className="section table-wrap">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
          <h2 style={{ margin: 0 }}>Merchant Registry</h2>
          <input
            className="input"
            style={{ maxWidth: 300, fontSize: "0.875rem", padding: "6px 12px" }}
            placeholder="Search merchants or aliases…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        <table style={{ marginTop: 8 }}>
          <thead>
            <tr>
              <th className="col-check" />
              <th>Merchant</th>
              <th>Canonical Name</th>
              <th>Aliases</th>
              <th style={{ textAlign: "right" }}>Last 30 Days</th>
              <th style={{ textAlign: "right" }}>Overall Spent</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {filteredMerchants.map((m) => {
              const last30 = m.spent_last_30d ?? 0;
              const overall = m.total_spent ?? 0;
              return (
                <tr
                  key={m.id}
                  className={`tx-row selectable ${selectedIds.has(m.id) ? "tx-selected" : ""}`}
                  onClick={() => toggleSelect(m.id)}
                >
                  <td className="col-check" onClick={(e) => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      checked={selectedIds.has(m.id)}
                      onChange={() => toggleSelect(m.id)}
                      aria-label={`Select ${m.display_name}`}
                    />
                  </td>
                  <td>
                    <div style={{ fontWeight: 600, color: "var(--ink)" }}>{m.display_name}</div>
                    <div style={{ fontSize: "0.75rem", color: "var(--ink-muted)", marginTop: 2 }}>
                      {m.transaction_count ?? 0} transactions
                    </div>
                  </td>
                  <td style={{ color: "var(--accent, #0c6e5c)", fontWeight: 600 }}>
                    {m.canonical_name || "—"}
                  </td>
                  <td style={{ color: "var(--ink-muted)", fontSize: "0.8125rem", maxWidth: 220 }}>
                    {m.aliases.length > 0 ? (
                      <span title={m.aliases.join(", ")}>
                        {m.aliases.length > 2
                          ? `${m.aliases.slice(0, 2).join(", ")} +${m.aliases.length - 2} more`
                          : m.aliases.join(", ")}
                      </span>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td style={{ textAlign: "right", whiteSpace: "nowrap", fontSize: "0.875rem" }}>
                    {last30 > 0 ? (
                      <span style={{ fontWeight: 500, color: "var(--ink)" }}>
                        {formatMoney(last30, "INR")}
                      </span>
                    ) : (
                      <span style={{ color: "var(--ink-muted)" }}>—</span>
                    )}
                  </td>
                  <td style={{ textAlign: "right", whiteSpace: "nowrap", fontSize: "0.9375rem", fontWeight: 600, color: "var(--ink)" }}>
                    {overall > 0 ? formatMoney(overall, "INR") : "₹0"}
                  </td>
                  <td className="row-actions">
                    <button 
                      className="btn icon-action" 
                      title="View details & receipts"
                      aria-label={`View details for ${m.display_name}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        setDetailsMerchant({ id: m.id, name: m.display_name });
                      }}
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/></svg>
                    </button>
                  </td>
                </tr>
              );
            })}
            {filteredMerchants.length === 0 && (
              <tr><td colSpan={7} className="empty">No merchants match your filter.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <MerchantDetailsModal
        merchantId={detailsMerchant?.id || null}
        merchantName={detailsMerchant?.name || ""}
        onClose={() => setDetailsMerchant(null)}
      />
    </>
  );
}
