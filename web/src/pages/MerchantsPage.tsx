import { useEffect, useState } from "react";
import { api, type Merchant } from "../api";
import MerchantDetailsModal from "../components/MerchantDetailsModal";
import { useToast } from "../hooks/useToast";

export default function MerchantsPage() {
  const [merchants, setMerchants] = useState<Merchant[]>([]);
  const [loading, setLoading] = useState(true);
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

  if (loading && merchants.length === 0) return <div className="empty">Loading merchants...</div>;

  return (
    <>
      <header className="page-header">
        <div>
          <h1>Merchant Intelligence</h1>
          <p className="lead">Clean up your data by merging aliases into canonical merchants.</p>
        </div>
      </header>
      
      {selectedIds.size > 0 && (
        <div className="review-action-bar">
          <div>Selected {selectedIds.size} merchants to merge.</div>
          <div className="review-action-buttons">
            <input 
              type="text" 
              placeholder="Canonical Name (e.g. Amazon)" 
              value={canonicalName}
              onChange={(e) => setCanonicalName(e.target.value)}
              className="input"
              style={{ minWidth: 200 }}
            />
            <button className="btn primary" onClick={handleMerge} disabled={mergeLoading || !canonicalName}>
              {mergeLoading ? "Merging..." : "Merge Selected"}
            </button>
          </div>
        </div>
      )}

      <div className="panel table-wrap">
        <table>
          <thead>
            <tr>
              <th className="col-check"></th>
              <th>Display Name</th>
              <th>Canonical Name</th>
              <th>Aliases</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {merchants.map((m) => (
              <tr key={m.id} className={`tx-row selectable ${selectedIds.has(m.id) ? "tx-selected" : ""}`} onClick={() => toggleSelect(m.id)}>
                <td className="col-check" onClick={(e) => e.stopPropagation()}>
                  <input
                    type="checkbox"
                    checked={selectedIds.has(m.id)}
                    onChange={() => toggleSelect(m.id)}
                  />
                </td>
                <td style={{ fontWeight: 600 }}>{m.display_name}</td>
                <td style={{ color: "var(--accent)", fontWeight: 600 }}>{m.canonical_name || "—"}</td>
                <td style={{ color: "var(--ink-muted)", fontSize: "0.8rem" }}>
                  {m.aliases.length > 0 ? m.aliases.join(", ") : "No aliases"}
                </td>
                <td style={{ textAlign: "right" }}>
                  <button 
                    className="btn icon-btn" 
                    title="Details"
                    onClick={(e) => {
                      e.stopPropagation();
                      setDetailsMerchant({ id: m.id, name: m.display_name });
                    }}
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/></svg>
                  </button>
                </td>
              </tr>
            ))}
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
