import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  type DataIssue,
  type DataIssueStatus,
  type DataIssueSummaryGroup,
  type DataIssueType,
  type GmailMessageView,
} from "../api";
import EmailViewerModal from "../components/EmailViewerModal";
import SortHeader from "../components/SortHeader";
import PageHeader from "../components/common/PageHeader";
import SegmentedControl from "../components/common/SegmentedControl";
import Badge from "../components/common/Badge";
import { formatDate, formatDateTime, formatIssueType, formatMoney } from "../format";

type IssueSortBy = "created_at" | "issue_type" | "merchant" | "amount" | "details" | "source";
type SortDir = "asc" | "desc";

export default function DataIssuesPage() {
  const [status, setStatus] = useState<DataIssueStatus>("open");
  const [groups, setGroups] = useState<DataIssueSummaryGroup[]>([]);
  const [activeIssueType, setActiveIssueType] = useState<DataIssueType | null>(null);
  const [items, setItems] = useState<DataIssue[]>([]);
  const [total, setTotal] = useState(0);
  const [pageSize, setPageSize] = useState<number>(50);
  const [offset, setOffset] = useState(0);
  const [q, setQ] = useState("");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [viewerOpen, setViewerOpen] = useState(false);
  const [viewerLoading, setViewerLoading] = useState(false);
  const [viewerError, setViewerError] = useState<string | null>(null);
  const [viewerMessage, setViewerMessage] = useState<GmailMessageView | null>(null);

  const [sortBy, setSortBy] = useState<IssueSortBy>("created_at");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const searchInputRef = useRef<HTMLInputElement>(null);

  // Keyboard shortcut '/' to focus search
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (
        e.key === "/" &&
        document.activeElement !== searchInputRef.current &&
        !(document.activeElement instanceof HTMLInputElement || document.activeElement instanceof HTMLTextAreaElement)
      ) {
        e.preventDefault();
        searchInputRef.current?.focus();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  function toggleSort(column: IssueSortBy) {
    if (sortBy === column) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortBy(column);
      setSortDir("asc");
    }
  }

  const loadGroups = useCallback(async () => {
    try {
      const data = await api.dataIssuesSummary(status);
      setGroups(data.groups);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load issue groups");
    }
  }, [status]);

  const loadItems = useCallback(async () => {
    try {
      const data = await api.dataIssues({
        status,
        issue_type: activeIssueType ?? undefined,
        limit: pageSize,
        offset,
      });
      setItems(data.items);
      setTotal(data.total);
      setSelectedIds(new Set());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load flagged issues");
    }
  }, [status, activeIssueType, pageSize, offset]);

  useEffect(() => {
    setActiveIssueType(null);
    setOffset(0);
  }, [status]);

  useEffect(() => {
    setError(null);
    void loadGroups();
  }, [loadGroups]);

  useEffect(() => {
    setError(null);
    void loadItems();
  }, [loadItems]);

  const selectedCount = selectedIds.size;
  const allSelected = items.length > 0 && selectedCount === items.length;
  const someSelected = selectedCount > 0 && !allSelected;

  const groupTotal = useMemo(() => groups.reduce((sum, g) => sum + g.count, 0), [groups]);

  const aggregatedGroups = useMemo(() => {
    const map = new Map<DataIssueType, number>();
    for (const g of groups) {
      if (g.issue_type) {
        map.set(g.issue_type, (map.get(g.issue_type) || 0) + g.count);
      }
    }
    return Array.from(map.entries()).map(([issue_type, count]) => ({
      issue_type,
      count,
    }));
  }, [groups]);

  // Client-side search and sort
  const filteredAndSortedItems = useMemo(() => {
    const query = q.trim().toLowerCase();
    const filtered = query
      ? items.filter((issue) => {
          const merchant = (issue.transaction?.merchant ?? "").toLowerCase();
          const note = (issue.note ?? "").toLowerCase();
          const issueType = (issue.issue_type ?? "").toLowerCase();
          const reported = (issue.reported_value ?? "").toLowerCase();
          const suggested = (issue.suggested_value ?? "").toLowerCase();
          return (
            merchant.includes(query) ||
            note.includes(query) ||
            issueType.includes(query) ||
            reported.includes(query) ||
            suggested.includes(query)
          );
        })
      : items;

    const dir = sortDir === "asc" ? 1 : -1;
    function keyFor(issue: DataIssue): string | number {
      switch (sortBy) {
        case "created_at":
          return issue.created_at ?? "";
        case "issue_type":
          return formatIssueType(issue.issue_type);
        case "merchant":
          return issue.transaction?.merchant ?? "";
        case "amount":
          return issue.transaction?.amount ?? -Infinity;
        case "details":
          return `${issue.reported_value ?? ""} ${issue.suggested_value ?? ""} ${issue.note ?? ""}`.trim();
        case "source":
          return issue.source ?? "";
        default:
          return "";
      }
    }
    return [...filtered].sort((a, b) => {
      const ka = keyFor(a);
      const kb = keyFor(b);
      if (typeof ka === "number" && typeof kb === "number") return (ka - kb) * dir;
      return String(ka).localeCompare(String(kb)) * dir;
    });
  }, [items, q, sortBy, sortDir]);

  function toggleOne(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAll() {
    if (allSelected) {
      setSelectedIds(new Set());
      return;
    }
    setSelectedIds(new Set(items.map((issue) => issue.id)));
  }

  async function resolveSelected(nextStatus: "resolved" | "dismissed") {
    if (selectedIds.size === 0) return;
    setBusy(true);
    setError(null);
    try {
      await api.resolveDataIssuesBulk({ issue_ids: Array.from(selectedIds), status: nextStatus });
      await Promise.all([loadGroups(), loadItems()]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update issues");
    } finally {
      setBusy(false);
    }
  }

  async function resolveOne(id: string, nextStatus: "resolved" | "dismissed") {
    setBusy(true);
    setError(null);
    try {
      await api.resolveDataIssuesBulk({ issue_ids: [id], status: nextStatus });
      await Promise.all([loadGroups(), loadItems()]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update issue");
    } finally {
      setBusy(false);
    }
  }

  async function openEmail(sourceEmailId: string) {
    setViewerOpen(true);
    setViewerLoading(true);
    setViewerError(null);
    setViewerMessage(null);
    try {
      const message = await api.fetchGmailMessage(sourceEmailId);
      setViewerMessage(message);
    } catch (err) {
      setViewerError(err instanceof Error ? err.message : "Failed to fetch email");
    } finally {
      setViewerLoading(false);
    }
  }

  function closeViewer() {
    setViewerOpen(false);
    setViewerMessage(null);
    setViewerError(null);
    setViewerLoading(false);
  }

  const currentPage = Math.floor(offset / pageSize) + 1;
  const totalPages = Math.ceil(total / pageSize) || 1;

  return (
    <section className="panel section" style={{ maxWidth: 1160, margin: "0 auto" }}>
      {/* Header */}
      <PageHeader
        title="Data Issues"
        subtitle="Audit flagged extraction problems and parser discrepancies. Clear or reprocess shared root causes in bulk."
      />

      {/* ───────────────────────────────────────────────────────────── */}
      {/* STICKY FILTER BAR                                             */}
      {/* ───────────────────────────────────────────────────────────── */}
      <div className="sticky-filters">
        {/* Top Row: Search + Status Segmented Control + Page Size */}
        <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", alignItems: "center", justifyContent: "space-between", marginBottom: "10px" }}>
          <div style={{ flex: "1 1 300px", minWidth: "240px" }}>
            <input
              ref={searchInputRef}
              className="input"
              style={{
                width: "100%",
                height: 36,
                minHeight: 36,
                fontSize: "0.85rem",
                padding: "0 12px",
                borderRadius: "var(--radius-sm)",
                border: "1px solid var(--line)",
                background: "var(--surface)",
                boxSizing: "border-box",
              }}
              placeholder="Search by merchant, note, or issue details... (Press '/' to focus)"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </div>

          <div style={{ display: "flex", gap: "8px", alignItems: "center", flexWrap: "wrap" }}>
            {/* Status Segmented Control */}
            <SegmentedControl<DataIssueStatus>
              value={status}
              onChange={setStatus}
              size="sm"
              options={[
                { value: "open", label: "Open" },
                { value: "resolved", label: "Resolved" },
                { value: "dismissed", label: "Dismissed" },
              ]}
            />

            {/* Page Size Selector */}
            <select
              className="input"
              style={{
                height: 36,
                minHeight: 36,
                fontSize: "0.84rem",
                padding: "0 8px",
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
                setOffset(0);
              }}
              title="Rows per page"
              aria-label="Rows per page"
            >
              <option value={25}>25 / page</option>
              <option value={50}>50 / page</option>
              <option value={100}>100 / page</option>
            </select>

            {/* Refresh Button */}
            <button
              className="icon-action"
              type="button"
              title="Refresh data issues"
              aria-label="Refresh data issues"
              onClick={() => {
                void loadGroups();
                void loadItems();
              }}
              style={{
                width: 36,
                height: 36,
                minWidth: 36,
                minHeight: 36,
                padding: 0,
                borderRadius: "var(--radius-sm)",
                border: "1px solid var(--line)",
                background: "var(--surface)",
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
                boxSizing: "border-box",
              }}
            >
              <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" focusable="false">
                <path
                  fill="none"
                  stroke="currentColor"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="1.8"
                  d="M20 11a8 8 0 0 0-14.9-4M4 5v4h4m-4 4a8 8 0 0 0 14.9 4M20 19v-4h-4"
                />
              </svg>
            </button>
          </div>
        </div>

        {/* Second Row: Issue Group Count Pills */}
        {aggregatedGroups.length > 0 && (
          <div style={{ display: "flex", gap: "6px", flexWrap: "wrap", alignItems: "center" }}>
            <button
              type="button"
              className={`btn quiet ${activeIssueType === null ? "primary" : ""}`}
              style={{
                fontSize: "0.82rem",
                padding: "3px 10px",
                fontWeight: activeIssueType === null ? 600 : 500,
                borderRadius: "var(--radius-sm)",
                background: activeIssueType === null ? "var(--accent)" : "transparent",
                color: activeIssueType === null ? "#fff" : "var(--ink)",
                border: activeIssueType === null ? "1px solid var(--accent)" : "1px solid var(--line)",
              }}
              onClick={() => {
                setActiveIssueType(null);
                setOffset(0);
              }}
            >
              All {status} ({groupTotal})
            </button>
            {aggregatedGroups.map((g) => {
              const active = activeIssueType === g.issue_type;
              return (
                <button
                  key={g.issue_type}
                  type="button"
                  className={`btn quiet ${active ? "primary" : ""}`}
                  style={{
                    fontSize: "0.82rem",
                    padding: "3px 10px",
                    fontWeight: active ? 600 : 500,
                    borderRadius: "var(--radius-sm)",
                    background: active ? "var(--accent)" : "transparent",
                    color: active ? "#fff" : "var(--ink)",
                    border: active ? "1px solid var(--accent)" : "1px solid var(--line)",
                  }}
                  onClick={() => {
                    setActiveIssueType(active ? null : g.issue_type);
                    setOffset(0);
                  }}
                >
                  {formatIssueType(g.issue_type)} ({g.count})
                </button>
              );
            })}
          </div>
        )}
      </div>

      {error && <p className="error">{error}</p>}

      {/* Bulk Action Bar */}
      {selectedCount > 0 && (
        <div className="review-action-bar" role="region" aria-label="Bulk actions" style={{ marginBottom: "16px" }}>
          <span>
            <strong>{selectedCount}</strong> issues selected
          </span>
          <div className="review-action-buttons">
            {status !== "resolved" && (
              <button className="btn primary" type="button" disabled={busy} onClick={() => void resolveSelected("resolved")}>
                Mark resolved
              </button>
            )}
            {status !== "dismissed" && (
              <button className="btn" type="button" disabled={busy} onClick={() => void resolveSelected("dismissed")}>
                Dismiss
              </button>
            )}
            <button className="btn" type="button" onClick={() => setSelectedIds(new Set())}>
              Clear selection
            </button>
          </div>
        </div>
      )}

      {/* ───────────────────────────────────────────────────────────── */}
      {/* DATA ISSUES TABLE                                             */}
      {/* ───────────────────────────────────────────────────────────── */}
      {filteredAndSortedItems.length === 0 ? (
        <div className="empty" style={{ padding: "36px 0" }}>
          {status === "open" ? "No open data issues. All transactions look clean." : `No ${status} data issues found.`}
        </div>
      ) : (
        <div className="table-wrap">
          <div className="tx-table-desktop">
            <table>
              <thead>
                <tr>
                  <th className="col-check">
                    <input
                      type="checkbox"
                      checked={allSelected}
                      ref={(el) => {
                        if (el) el.indeterminate = someSelected;
                      }}
                      onChange={toggleAll}
                      aria-label="Select all visible"
                    />
                  </th>
                  <SortHeader
                    label="Flagged"
                    active={sortBy === "created_at"}
                    dir={sortDir}
                    onClick={() => toggleSort("created_at")}
                  />
                  <SortHeader
                    label="Issue Type"
                    active={sortBy === "issue_type"}
                    dir={sortDir}
                    onClick={() => toggleSort("issue_type")}
                  />
                  <SortHeader
                    label="Transaction / Description"
                    active={sortBy === "merchant"}
                    dir={sortDir}
                    onClick={() => toggleSort("merchant")}
                  />
                  <SortHeader
                    label="Amount"
                    className="num"
                    active={sortBy === "amount"}
                    dir={sortDir}
                    onClick={() => toggleSort("amount")}
                  />
                  <SortHeader
                    label="Discrepancy Details"
                    active={sortBy === "details"}
                    dir={sortDir}
                    onClick={() => toggleSort("details")}
                  />
                  <th style={{ textAlign: "right" }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredAndSortedItems.map((issue) => {
                  const selected = selectedIds.has(issue.id);
                  const tx = issue.transaction;
                  const merchant = tx?.merchant ?? "Uncategorized transaction";

                  return (
                    <tr
                      key={issue.id}
                      className={`tx-row selectable${selected ? " tx-selected" : ""}`}
                      style={{ cursor: "pointer" }}
                      onClick={() => toggleOne(issue.id)}
                    >
                      <td className="col-check" onClick={(e) => e.stopPropagation()}>
                        <input
                          type="checkbox"
                          checked={selected}
                          onChange={() => toggleOne(issue.id)}
                          aria-label={`Select flag on ${merchant}`}
                        />
                      </td>

                      {/* Flagged Date */}
                      <td className="tx-date" style={{ whiteSpace: "nowrap", fontSize: "0.85rem", color: "var(--ink)" }}>
                        {formatDateTime(issue.created_at)}
                      </td>

                      {/* Issue Type Badge */}
                      <td style={{ whiteSpace: "nowrap" }}>
                        <Badge variant="warn" size="sm">
                          {formatIssueType(issue.issue_type)}
                        </Badge>
                      </td>

                      {/* Transaction Merchant & Description */}
                      <td style={{ maxWidth: 260, paddingRight: 14 }}>
                        <div
                          style={{
                            fontWeight: 600,
                            fontSize: "0.92rem",
                            color: "var(--ink)",
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap",
                          }}
                          title={merchant}
                        >
                          {merchant}
                        </div>
                        {tx?.transaction_date && (
                          <div style={{ fontSize: "0.78rem", color: "var(--ink-muted)", marginTop: 1 }}>
                            Transaction date: {formatDate(tx.transaction_date)}
                          </div>
                        )}
                      </td>

                      {/* Amount */}
                      <td
                        className="tx-amount num"
                        style={{
                          whiteSpace: "nowrap",
                          fontVariantNumeric: "tabular-nums",
                          fontWeight: 600,
                          fontSize: "0.9rem",
                        }}
                      >
                        {tx?.amount != null ? formatMoney(tx.amount, tx.currency) : "—"}
                      </td>

                      {/* Discrepancy Details & Note */}
                      <td style={{ maxWidth: 300 }}>
                        {issue.field_name && (
                          <div style={{ fontSize: "0.86rem", fontWeight: 500 }}>
                            <span style={{ color: "var(--ink-muted)" }}>{issue.field_name}: </span>
                            <span style={{ textDecoration: "line-through", color: "var(--debit)" }}>
                              {issue.reported_value ?? "—"}
                            </span>
                            {issue.suggested_value && (
                              <span style={{ color: "var(--credit)", fontWeight: 600 }}> → {issue.suggested_value}</span>
                            )}
                          </div>
                        )}
                        {issue.note && (
                          <div style={{ fontSize: "0.78rem", color: "var(--ink-muted)", marginTop: 2 }}>
                            {issue.note}
                          </div>
                        )}
                      </td>

                      {/* Actions */}
                      <td onClick={(e) => e.stopPropagation()} style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                        <div style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
                          {tx?.source_email_id && (
                            <button
                              className="btn quiet icon-btn"
                              type="button"
                              title="View source email"
                              aria-label="View source email"
                              onClick={() => void openEmail(tx.source_email_id!)}
                              style={{ width: 32, height: 32 }}
                            >
                              <svg className="gmail-icon" viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
                                <path
                                  fill="currentColor"
                                  d="M20 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4-8 5L4 8V6l8 5 8-5v2z"
                                />
                              </svg>
                            </button>
                          )}
                          {status !== "resolved" && (
                            <button
                              className="btn primary"
                              type="button"
                              title="Mark resolved"
                              disabled={busy}
                              style={{ fontSize: "0.78rem", padding: "4px 8px" }}
                              onClick={() => void resolveOne(issue.id, "resolved")}
                            >
                              ✓ Resolve
                            </button>
                          )}
                          {status !== "dismissed" && (
                            <button
                              className="btn quiet"
                              type="button"
                              title="Dismiss issue"
                              disabled={busy}
                              style={{ fontSize: "0.78rem", padding: "4px 8px" }}
                              onClick={() => void resolveOne(issue.id, "dismissed")}
                            >
                              Dismiss
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Mobile Card Layout */}
          <div className="tx-cards-mobile" role="feed" aria-label="Data issues list">
            {filteredAndSortedItems.map((issue) => {
              const selected = selectedIds.has(issue.id);
              const tx = issue.transaction;
              const merchant = tx?.merchant ?? "Uncategorized transaction";

              return (
                <article
                  key={issue.id}
                  className={`tx-card ${selected ? "tx-selected" : ""}`}
                  onClick={() => toggleOne(issue.id)}
                  style={{ cursor: "pointer" }}
                >
                  <div className="tx-card-header">
                    <div className="tx-card-title-group">
                      <div onClick={(e) => e.stopPropagation()}>
                        <input
                          type="checkbox"
                          checked={selected}
                          onChange={() => toggleOne(issue.id)}
                          aria-label={`Select flag on ${merchant}`}
                          style={{ width: 18, height: 18 }}
                        />
                      </div>
                      <div>
                        <div className="tx-card-merchant" style={{ fontWeight: 600, fontSize: "0.95rem" }}>
                          {merchant}
                        </div>
                        <div className="tx-card-date" style={{ fontSize: "0.78rem", color: "var(--ink-muted)", marginTop: 2 }}>
                          Flagged {formatDateTime(issue.created_at)}
                        </div>
                      </div>
                    </div>

                    <Badge variant="warn" size="sm">
                      {formatIssueType(issue.issue_type)}
                    </Badge>
                  </div>

                  <div className="tx-card-body" style={{ marginTop: 6 }}>
                    {issue.field_name && (
                      <div style={{ fontSize: "0.85rem" }}>
                        <span style={{ color: "var(--ink-muted)" }}>{issue.field_name}: </span>
                        <span style={{ textDecoration: "line-through", color: "var(--debit)" }}>
                          {issue.reported_value ?? "—"}
                        </span>
                        {issue.suggested_value && (
                          <span style={{ color: "var(--credit)", fontWeight: 600 }}> → {issue.suggested_value}</span>
                        )}
                      </div>
                    )}
                    {issue.note && (
                      <div style={{ fontSize: "0.8rem", color: "var(--ink-muted)", marginTop: 2 }}>
                        {issue.note}
                      </div>
                    )}
                    {tx?.amount != null && (
                      <div style={{ marginTop: 4, fontWeight: 600, fontSize: "0.92rem" }}>
                        Amount: {formatMoney(tx.amount, tx.currency)}
                      </div>
                    )}
                  </div>

                  <div className="tx-card-footer" onClick={(e) => e.stopPropagation()} style={{ marginTop: 8, borderTop: "1px solid var(--line)", paddingTop: 8 }}>
                    <div style={{ display: "flex", gap: 6, marginLeft: "auto" }}>
                      {tx?.source_email_id && (
                        <button
                          className="btn quiet icon-btn"
                          type="button"
                          onClick={() => void openEmail(tx.source_email_id!)}
                          style={{ width: 34, height: 34 }}
                        >
                          <svg className="gmail-icon" viewBox="0 0 24 24" width="16" height="16">
                            <path fill="currentColor" d="M20 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4-8 5L4 8V6l8 5 8-5v2z"/>
                          </svg>
                        </button>
                      )}
                      {status !== "resolved" && (
                        <button
                          className="btn primary"
                          type="button"
                          disabled={busy}
                          style={{ fontSize: "0.82rem", padding: "6px 12px" }}
                          onClick={() => void resolveOne(issue.id, "resolved")}
                        >
                          ✓ Resolve
                        </button>
                      )}
                      {status !== "dismissed" && (
                        <button
                          className="btn quiet"
                          type="button"
                          disabled={busy}
                          style={{ fontSize: "0.82rem", padding: "6px 12px" }}
                          onClick={() => void resolveOne(issue.id, "dismissed")}
                        >
                          Dismiss
                        </button>
                      )}
                    </div>
                  </div>
                </article>
              );
            })}
          </div>

          {/* ───────────────────────────────────────────────────────────── */}
          {/* FOOTER & PAGINATION                                           */}
          {/* ───────────────────────────────────────────────────────────── */}
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              flexWrap: "wrap",
              gap: 12,
              marginTop: 14,
              padding: "12px 16px",
              background: "var(--surface)",
              border: "1px solid var(--line)",
              borderRadius: "var(--radius-sm)",
              fontSize: "0.875rem",
            }}
          >
            <div>
              Showing <strong>{offset + 1}–{Math.min(offset + items.length, total)}</strong> of{" "}
              <strong>{total}</strong> {status} issues
            </div>

            {total > pageSize && (
              <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                <button
                  className="btn"
                  disabled={offset === 0}
                  onClick={() => setOffset((o) => Math.max(0, o - pageSize))}
                  style={{ fontSize: "0.84rem", padding: "5px 12px" }}
                >
                  ‹ Previous
                </button>
                <span style={{ fontSize: "0.84rem", color: "var(--ink-muted)", padding: "0 4px" }}>
                  Page {currentPage} of {totalPages}
                </span>
                <button
                  className="btn"
                  disabled={offset + pageSize >= total}
                  onClick={() => setOffset((o) => o + pageSize)}
                  style={{ fontSize: "0.84rem", padding: "5px 12px" }}
                >
                  Next ›
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Email Viewer Modal */}
      <EmailViewerModal
        open={viewerOpen}
        loading={viewerLoading}
        error={viewerError}
        message={viewerMessage}
        onClose={closeViewer}
      />
    </section>
  );
}
