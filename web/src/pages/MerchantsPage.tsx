import { useEffect, useMemo, useState } from "react";
import { api, type Merchant } from "../api";
import { formatMoney } from "../format";
import MerchantDetailsModal from "../components/MerchantDetailsModal";
import SortHeader from "../components/SortHeader";
import PageHeader from "../components/common/PageHeader";
import { useToast } from "../hooks/useToast";

type SortField = "lifetime" | "30day" | "merchant" | "txcount";
type SortDir = "asc" | "desc";

export default function MerchantsPage() {
  const [merchants, setMerchants] = useState<Merchant[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const { showToast } = useToast();

  const [sortField, setSortField] = useState<SortField>("lifetime");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [canonicalName, setCanonicalName] = useState("");
  const [mergeLoading, setMergeLoading] = useState(false);
  const [detailsMerchant, setDetailsMerchant] = useState<{ id: string; name: string } | null>(null);

  const [pageSize, setPageSize] = useState<number>(25);
  const [page, setPage] = useState<number>(1);

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

  useEffect(() => {
    setPage(1);
  }, [searchQuery, sortField, sortDir]);

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortField(field);
      setSortDir(field === "merchant" ? "asc" : "desc");
    }
  };

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

  const filteredAndSortedMerchants = useMemo(() => {
    const q = searchQuery.toLowerCase().trim();
    let result = merchants;

    if (q) {
      result = result.filter(
        (m) =>
          m.display_name.toLowerCase().includes(q) ||
          (m.canonical_name && m.canonical_name.toLowerCase().includes(q)) ||
          (m.default_category && m.default_category.toLowerCase().includes(q)) ||
          m.aliases.some((a) => a.toLowerCase().includes(q))
      );
    }

    return [...result].sort((a, b) => {
      let cmp = 0;
      if (sortField === "lifetime") {
        cmp = (a.total_spent || 0) - (b.total_spent || 0);
      } else if (sortField === "30day") {
        cmp = (a.spent_last_30d || 0) - (b.spent_last_30d || 0);
      } else if (sortField === "merchant") {
        cmp = a.display_name.localeCompare(b.display_name);
      } else if (sortField === "txcount") {
        cmp = (a.transaction_count || 0) - (b.transaction_count || 0);
      }
      return sortDir === "asc" ? cmp : -cmp;
    });
  }, [merchants, searchQuery, sortField, sortDir]);

  const totalMerchants = filteredAndSortedMerchants.length;
  const totalPages = Math.max(1, Math.ceil(totalMerchants / pageSize));
  const currentPage = Math.min(page, totalPages);
  const offset = (currentPage - 1) * pageSize;
  const paginatedMerchants = useMemo(() => {
    return filteredAndSortedMerchants.slice(offset, offset + pageSize);
  }, [filteredAndSortedMerchants, offset, pageSize]);

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
      <PageHeader
        title="Merchants"
        subtitle={
          <>
            Manage normalized counterparties, aliases, and automated categorization rules.
            <span style={{ opacity: 0.4, margin: "0 6px" }}>·</span>
            <span style={{ color: "var(--ink-muted)" }}>{merchants.length} registered merchants</span>
          </>
        }
      />

      {/* Summary KPI Cards */}
      <section className="metrics" style={{ marginBottom: 24, display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "16px" }}>
        <article className="panel metric" style={{ padding: "16px" }}>
          <div className="metric-label" style={{ fontSize: "0.78rem", color: "var(--ink-muted)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "6px", fontWeight: 600 }}>
            Tracked Merchants
          </div>
          <div className="metric-value" style={{ fontSize: "1.7rem", fontWeight: 700 }}>
            {merchants.length}
          </div>
          <div className="metric-hint" style={{ fontSize: "0.8125rem", color: "var(--ink-muted)", marginTop: "4px" }}>
            {merchants.length} normalized entities
          </div>
        </article>

        <article className="panel metric" style={{ padding: "16px" }}>
          <div className="metric-label" style={{ fontSize: "0.78rem", color: "var(--ink-muted)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "6px", fontWeight: 600 }}>
            Last 30 Days
          </div>
          <div className="metric-value" style={{ fontSize: "1.7rem", fontWeight: 700, color: "var(--ink)" }}>
            {formatMoney(totalSpendLast30d, "INR")}
          </div>
          <div className="metric-hint" style={{ fontSize: "0.8125rem", color: "var(--ink-muted)", marginTop: "4px" }}>
            Past 30 days active spend
          </div>
        </article>

        <article className="panel metric" style={{ padding: "16px" }}>
          <div className="metric-label" style={{ fontSize: "0.78rem", color: "var(--ink-muted)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "6px", fontWeight: 600 }}>
            Lifetime Spend
          </div>
          <div className="metric-value" style={{ fontSize: "1.7rem", fontWeight: 700, color: "var(--ink)" }}>
            {formatMoney(totalSpendOverall, "INR")}
          </div>
          <div className="metric-hint" style={{ fontSize: "0.8125rem", color: "var(--ink-muted)", marginTop: "4px" }}>
            Lifetime recorded debit volume
          </div>
        </article>
      </section>

      {selectedIds.size > 0 && (
        <div className="review-action-bar" role="region" aria-label="Merge merchants">
          <div>Selected <strong>{selectedIds.size}</strong> merchants to merge.</div>
          <div className="review-action-buttons" style={{ display: "flex", flexWrap: "wrap", gap: 8, width: "100%" }}>
            <input 
              type="text" 
              placeholder="Canonical Name (e.g. Amazon)" 
              value={canonicalName}
              onChange={(e) => setCanonicalName(e.target.value)}
              className="input"
              style={{ flex: 1, minWidth: 180 }}
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
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14, flexWrap: "wrap", gap: 10 }}>
          <div>
            <h2 style={{ margin: 0 }}>Merchant Registry</h2>
            <div style={{ fontSize: "0.82rem", color: "var(--ink-muted)", marginTop: 2 }}>
              {filteredAndSortedMerchants.length} {filteredAndSortedMerchants.length === 1 ? "merchant" : "merchants"} found
            </div>
          </div>
          <input
            className="input"
            style={{ width: "min(340px, 100%)", height: 36, fontSize: "0.85rem", padding: "0 12px", borderRadius: "var(--radius-sm)", boxSizing: "border-box" }}
            placeholder="Search merchants, aliases, or categories…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        {/* Desktop Table View (>= 768px) */}
        <div className="tx-table-desktop">
          <table style={{ marginTop: 8 }}>
            <thead>
              <tr>
                <th className="col-check" style={{ width: 36 }} />
                <SortHeader
                  label="Merchant"
                  active={sortField === "merchant"}
                  dir={sortDir}
                  onClick={() => handleSort("merchant")}
                  style={{ width: "32%", maxWidth: 320 }}
                />
                <th style={{ width: "20%", minWidth: 140, maxWidth: 220 }}>Canonical Name</th>
                <th style={{ width: "14%", minWidth: 100, maxWidth: 140 }}>Aliases</th>
                <SortHeader
                  label="30-Day Spend"
                  className="num"
                  active={sortField === "30day"}
                  dir={sortDir}
                  onClick={() => handleSort("30day")}
                  style={{ width: 140, minWidth: 120 }}
                />
                <SortHeader
                  label="Lifetime Spend"
                  className="num"
                  active={sortField === "lifetime"}
                  dir={sortDir}
                  onClick={() => handleSort("lifetime")}
                  style={{ width: 140, minWidth: 120 }}
                />
              </tr>
            </thead>
            <tbody>
              {paginatedMerchants.map((m) => {
                const last30 = m.spent_last_30d ?? 0;
                const overall = m.total_spent ?? 0;
                const aliasCount = m.aliases.length;

                return (
                  <tr
                    key={m.id}
                    className={`tx-row selectable ${selectedIds.has(m.id) ? "tx-selected" : ""}`}
                    style={{ cursor: "pointer" }}
                    onClick={() => setDetailsMerchant({ id: m.id, name: m.canonical_name || m.display_name })}
                  >
                    <td className="col-check" onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={selectedIds.has(m.id)}
                        onChange={() => toggleSelect(m.id)}
                        aria-label={`Select ${m.display_name}`}
                      />
                    </td>
                    <td style={{ maxWidth: 320, wordBreak: "break-word", overflowWrap: "anywhere" }}>
                      <div style={{ fontWeight: 600, color: "var(--ink)", wordBreak: "break-word", overflowWrap: "anywhere", lineHeight: 1.35 }}>
                        {m.display_name}
                      </div>
                      <div style={{ fontSize: "0.76rem", color: "var(--ink-muted)", marginTop: 3, display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap", wordBreak: "break-word" }}>
                        <span>{m.transaction_count ?? 0} {m.transaction_count === 1 ? "transaction" : "transactions"}</span>
                        {m.default_category && (
                          <>
                            <span style={{ opacity: 0.5 }}>·</span>
                            <span style={{ color: "var(--ink)", fontWeight: 500 }}>{m.default_category}</span>
                          </>
                        )}
                      </div>
                    </td>
                    <td style={{ maxWidth: 220, wordBreak: "break-word", overflowWrap: "anywhere" }}>
                      {m.canonical_name ? (
                        <span style={{ color: "var(--accent)", fontWeight: 600, fontSize: "0.88rem", wordBreak: "break-word", overflowWrap: "anywhere" }}>
                          {m.canonical_name}
                        </span>
                      ) : (
                        <span style={{ color: "var(--ink-muted)", fontSize: "0.85rem" }}>—</span>
                      )}
                    </td>
                    <td>
                      {aliasCount > 0 ? (
                        <span
                          className="badge"
                          style={{
                            fontSize: "0.76rem",
                            fontWeight: 500,
                            cursor: "pointer",
                            background: "var(--surface)",
                            border: "1px solid var(--line)",
                            color: "var(--ink)",
                            display: "inline-flex",
                            alignItems: "center",
                          }}
                          title={m.aliases.join(", ")}
                        >
                          {aliasCount} {aliasCount === 1 ? "alias" : "aliases"}
                        </span>
                      ) : (
                        <span style={{ color: "var(--ink-muted)", fontSize: "0.85rem" }}>—</span>
                      )}
                    </td>
                    <td className="num tx-amount" style={{ fontSize: "0.88rem" }}>
                      {last30 > 0 ? (
                        <span style={{ fontWeight: 500, color: "var(--ink)" }}>
                          {formatMoney(last30, "INR")}
                        </span>
                      ) : (
                        <span style={{ color: "var(--ink-muted)" }}>—</span>
                      )}
                    </td>
                    <td className="num tx-amount" style={{ fontSize: "0.92rem", fontWeight: 600, color: "var(--ink)" }}>
                      {overall > 0 ? formatMoney(overall, "INR") : "₹0"}
                    </td>
                  </tr>
                );
              })}
              {filteredAndSortedMerchants.length === 0 && (
                <tr><td colSpan={6} className="empty">No merchants match your search filter.</td></tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Mobile Cards View (< 768px) */}
        <div className="tx-cards-mobile" style={{ marginTop: 8 }}>
          {/* Mobile Sort Control */}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10, padding: "0 4px" }}>
            <span style={{ fontSize: "0.78rem", color: "var(--ink-muted)", fontWeight: 500 }}>Sort by:</span>
            <div style={{ display: "flex", gap: 6 }}>
              <select
                value={sortField}
                onChange={(e) => setSortField(e.target.value as SortField)}
                className="input select"
                style={{ height: 32, fontSize: "0.8rem", padding: "0 8px" }}
              >
                <option value="lifetime">Lifetime Spend</option>
                <option value="30day">30-Day Spend</option>
                <option value="merchant">Merchant Name</option>
                <option value="txcount">Tx Count</option>
              </select>
              <button
                type="button"
                className="btn quiet icon-btn"
                style={{ height: 32, width: 32, padding: 0 }}
                onClick={() => setSortDir(sortDir === "asc" ? "desc" : "asc")}
                aria-label="Toggle sort direction"
              >
                {sortDir === "asc" ? "▲" : "▼"}
              </button>
            </div>
          </div>

          {paginatedMerchants.map((m) => {
            const last30 = m.spent_last_30d ?? 0;
            const overall = m.total_spent ?? 0;
            const aliasCount = m.aliases.length;

            return (
              <article
                key={m.id}
                className={`tx-card selectable ${selectedIds.has(m.id) ? "tx-selected" : ""}`}
                style={{ cursor: "pointer" }}
                onClick={() => setDetailsMerchant({ id: m.id, name: m.canonical_name || m.display_name })}
              >
                <div className="tx-card-header" style={{ alignItems: "flex-start", gap: 10 }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                      <span className="tx-card-merchant" style={{ wordBreak: "break-word" }}>{m.display_name}</span>
                      {m.canonical_name && (
                        <span className="badge" style={{ fontSize: "0.72rem", background: "var(--accent-soft)", color: "var(--accent)", border: "none", padding: "2px 6px" }}>
                          {m.canonical_name}
                        </span>
                      )}
                    </div>
                    <div style={{ color: "var(--ink-muted)", fontSize: "0.78rem", marginTop: 3, display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                      <span>{m.transaction_count ?? 0} {m.transaction_count === 1 ? "tx" : "txs"}</span>
                      {m.default_category && (
                        <>
                          <span style={{ opacity: 0.5 }}>·</span>
                          <span style={{ color: "var(--ink)" }}>{m.default_category}</span>
                        </>
                      )}
                    </div>
                  </div>

                  <div style={{ textAlign: "right", flexShrink: 0 }}>
                    <div style={{ fontSize: "0.7rem", color: "var(--ink-muted)", textTransform: "uppercase", letterSpacing: "0.04em", fontWeight: 600 }}>
                      Lifetime
                    </div>
                    <div className="tx-card-amount debit" style={{ fontSize: "1.05rem", fontWeight: 700 }}>
                      {overall > 0 ? formatMoney(overall, "INR") : "₹0"}
                    </div>
                  </div>
                </div>

                <div className="tx-card-footer" style={{ borderTop: "1px solid var(--line)", paddingTop: 8, marginTop: 8, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                    {aliasCount > 0 && (
                      <span className="badge" style={{ fontSize: "0.72rem", background: "var(--surface)", border: "1px solid var(--line)", color: "var(--ink-muted)" }}>
                        {aliasCount} {aliasCount === 1 ? "alias" : "aliases"}
                      </span>
                    )}
                    {last30 > 0 && (
                      <span style={{ fontSize: "0.78rem", color: "var(--ink-muted)" }}>
                        30d: <strong style={{ color: "var(--ink)" }}>{formatMoney(last30, "INR")}</strong>
                      </span>
                    )}
                  </div>

                  <div style={{ display: "flex", alignItems: "center", gap: 4 }} onClick={(e) => e.stopPropagation()}>
                    <label style={{ display: "inline-flex", alignItems: "center", gap: 4, cursor: "pointer", fontSize: "0.76rem", color: "var(--ink-muted)" }}>
                      <input
                        type="checkbox"
                        checked={selectedIds.has(m.id)}
                        onChange={() => toggleSelect(m.id)}
                        aria-label={`Select ${m.display_name}`}
                      />
                      <span>Select</span>
                    </label>
                  </div>
                </div>
              </article>
            );
          })}
          {filteredAndSortedMerchants.length === 0 && (
            <div className="empty" style={{ padding: 24 }}>No merchants match your search filter.</div>
          )}
        </div>

        {/* Pagination Footer */}
        <div
          className="tx-pagination-footer"
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: 12,
            marginTop: 14,
            padding: "10px 14px",
            background: "var(--surface)",
            border: "1px solid var(--line)",
            borderRadius: "var(--radius-sm)",
            fontSize: "0.85rem",
            flexWrap: "wrap",
          }}
        >
          {/* Left summary */}
          <div style={{ display: "flex", gap: 10, alignItems: "center", minWidth: 0 }}>
            <span style={{ whiteSpace: "nowrap" }}>
              Showing <strong>{totalMerchants === 0 ? 0 : offset + 1}–{Math.min(offset + paginatedMerchants.length, totalMerchants)}</strong> of{" "}
              <strong>{totalMerchants}</strong>
            </span>
            {searchQuery.trim() && (
              <>
                <span style={{ color: "var(--line)" }}>·</span>
                <span style={{ fontSize: "0.8rem", color: "var(--ink-muted)", whiteSpace: "nowrap" }}>
                  Filtered from {merchants.length} total
                </span>
              </>
            )}
          </div>

          {/* Right pagination & page size controls */}
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexShrink: 0 }}>
            <select
              className="input"
              style={{
                height: 30,
                minHeight: 30,
                fontSize: "0.8rem",
                padding: "0 6px",
                width: "auto",
                borderRadius: "var(--radius-sm)",
                border: "1px solid var(--line)",
                background: "var(--surface)",
                cursor: "pointer",
                boxSizing: "border-box",
              }}
              value={pageSize}
              onChange={(e) => {
                setPageSize(Number(e.target.value));
                setPage(1);
              }}
              title="Rows per page"
              aria-label="Rows per page"
            >
              <option value={25}>25 / page</option>
              <option value={50}>50 / page</option>
              <option value={100}>100 / page</option>
              <option value={250}>250 / page</option>
            </select>

            <button
              type="button"
              className="btn"
              disabled={currentPage <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              style={{ fontSize: "0.8rem", height: 30, padding: "0 10px", display: "inline-flex", alignItems: "center" }}
            >
              ‹ Prev
            </button>
            <span style={{ fontSize: "0.8rem", color: "var(--ink-muted)", whiteSpace: "nowrap", padding: "0 2px" }}>
              {currentPage} / {totalPages}
            </span>
            <button
              type="button"
              className="btn"
              disabled={currentPage >= totalPages}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              style={{ fontSize: "0.8rem", height: 30, padding: "0 10px", display: "inline-flex", alignItems: "center" }}
            >
              Next ›
            </button>
          </div>
        </div>
      </div>

      <MerchantDetailsModal
        merchantId={detailsMerchant?.id ?? null}
        merchantName={detailsMerchant?.name ?? ""}
        onClose={() => setDetailsMerchant(null)}
      />
    </>
  );
}
