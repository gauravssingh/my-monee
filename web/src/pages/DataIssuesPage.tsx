import { useCallback, useEffect, useMemo, useState } from "react";
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
import { formatDateTime, formatIssueType, formatMoney } from "../format";

type GroupKey = { issueType: DataIssueType | null; source: string | null };
type IssueSortBy = "created_at" | "issue_type" | "merchant" | "amount" | "details" | "source";
type SortDir = "asc" | "desc";

function sourceLabel(source: string | null): string {
  return source ?? "Unknown source";
}

function groupsMatch(a: GroupKey, b: GroupKey): boolean {
  return a.issueType === b.issueType && a.source === b.source;
}

export default function DataIssuesPage() {
  const [status, setStatus] = useState<DataIssueStatus>("open");
  const [groups, setGroups] = useState<DataIssueSummaryGroup[]>([]);
  const [activeGroup, setActiveGroup] = useState<GroupKey | null>(null);
  const [items, setItems] = useState<DataIssue[]>([]);
  const [total, setTotal] = useState(0);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [viewerOpen, setViewerOpen] = useState(false);
  const [viewerLoading, setViewerLoading] = useState(false);
  const [viewerError, setViewerError] = useState<string | null>(null);
  const [viewerMessage, setViewerMessage] = useState<GmailMessageView | null>(null);
  const [sortBy, setSortBy] = useState<IssueSortBy>("created_at");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

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
        issue_type: activeGroup?.issueType ?? undefined,
        source: activeGroup?.source ?? undefined,
        limit: 200,
      });
      setItems(data.items);
      setTotal(data.total);
      setSelectedIds(new Set());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load flagged issues");
    }
  }, [status, activeGroup]);

  useEffect(() => {
    setActiveGroup(null);
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

  const sortedItems = useMemo(() => {
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
    return [...items].sort((a, b) => {
      const ka = keyFor(a);
      const kb = keyFor(b);
      if (typeof ka === "number" && typeof kb === "number") return (ka - kb) * dir;
      return String(ka).localeCompare(String(kb)) * dir;
    });
  }, [items, sortBy, sortDir]);

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

  return (
    <section className="panel section">
      <h2>Data issues</h2>
      <p className="lead">
        Flagged extraction problems, grouped by issue type and source so a shared root cause — a
        parser bug, a bad merchant match — can be fixed once and cleared in bulk.
      </p>

      <div className="toolbar">
        <div className="segmented" role="group" aria-label="Status filter">
          {(
            [
              ["open", "Open"],
              ["resolved", "Resolved"],
              ["dismissed", "Dismissed"],
            ] as const
          ).map(([value, label]) => (
            <button
              key={value}
              type="button"
              className={`segmented-btn${status === value ? " active" : ""}`}
              aria-pressed={status === value}
              onClick={() => setStatus(value)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {error && <p className="error">{error}</p>}

      {groups.length > 0 && (
        <div className="issue-group-list" role="group" aria-label="Issue groups">
          <button
            type="button"
            className={`issue-group${activeGroup === null ? " active" : ""}`}
            onClick={() => setActiveGroup(null)}
          >
            <span>All {status}</span>
            <span className="issue-group-count">{groupTotal}</span>
          </button>
          {groups.map((g) => {
            const key: GroupKey = { issueType: g.issue_type, source: g.source };
            const active = activeGroup != null && groupsMatch(activeGroup, key);
            return (
              <button
                key={`${g.issue_type}:${g.source ?? ""}`}
                type="button"
                className={`issue-group${active ? " active" : ""}`}
                onClick={() => setActiveGroup(key)}
              >
                <span>
                  {formatIssueType(g.issue_type)} · {sourceLabel(g.source)}
                </span>
                <span className="issue-group-count">{g.count}</span>
              </button>
            );
          })}
        </div>
      )}

      {selectedCount > 0 && (
        <div className="review-action-bar" role="region" aria-label="Bulk actions">
          <span>
            <strong>{selectedCount}</strong> selected
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

      {items.length === 0 ? (
        <div className="empty">
          {status === "open" ? "No open data issues. Nice." : `No ${status} data issues.`}
        </div>
      ) : (
        <div className="table-wrap">
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
                  label="Issue"
                  active={sortBy === "issue_type"}
                  dir={sortDir}
                  onClick={() => toggleSort("issue_type")}
                />
                <SortHeader
                  label="Transaction"
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
                  label="Details"
                  active={sortBy === "details"}
                  dir={sortDir}
                  onClick={() => toggleSort("details")}
                />
                <SortHeader
                  label="Source"
                  active={sortBy === "source"}
                  dir={sortDir}
                  onClick={() => toggleSort("source")}
                />
                <th />
              </tr>
            </thead>
            <tbody>
              {sortedItems.map((issue) => {
                const selected = selectedIds.has(issue.id);
                const tx = issue.transaction;
                return (
                  <tr
                    key={issue.id}
                    className={`tx-row selectable${selected ? " tx-selected" : ""}`}
                    onClick={() => toggleOne(issue.id)}
                  >
                    <td className="col-check" onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={selected}
                        onChange={() => toggleOne(issue.id)}
                        aria-label={`Select flag on ${tx?.merchant ?? "transaction"}`}
                      />
                    </td>
                    <td className="tx-date">{formatDateTime(issue.created_at)}</td>
                    <td>{formatIssueType(issue.issue_type)}</td>
                    <td>{tx?.merchant ?? "Uncategorized transaction"}</td>
                    <td className="tx-amount num">
                      {tx?.amount != null ? formatMoney(tx.amount, tx.currency) : "—"}
                    </td>
                    <td>
                      {issue.field_name && (
                        <div>
                          {issue.reported_value ?? "—"}
                          {issue.suggested_value ? ` → ${issue.suggested_value}` : ""}
                        </div>
                      )}
                      {issue.note && <div className="metric-hint" style={{ marginTop: 2 }}>{issue.note}</div>}
                    </td>
                    <td>{sourceLabel(issue.source)}</td>
                    <td onClick={(e) => e.stopPropagation()}>
                      <div style={{ display: "flex", gap: 4, justifyContent: "flex-end" }}>
                        {tx?.source_email_id && (
                          <button
                            className="gmail-link"
                            type="button"
                            title="View source email"
                            aria-label="View source email"
                            onClick={() => void openEmail(tx.source_email_id!)}
                          >
                            <svg
                              className="gmail-icon"
                              viewBox="0 0 24 24"
                              width="18"
                              height="18"
                              aria-hidden="true"
                              focusable="false"
                            >
                              <path
                                fill="currentColor"
                                d="M20 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4-8 5L4 8V6l8 5 8-5v2z"
                              />
                            </svg>
                          </button>
                        )}
                        {status !== "resolved" && (
                          <button
                            className="icon-action"
                            type="button"
                            title="Mark resolved"
                            aria-label="Mark resolved"
                            disabled={busy}
                            onClick={() => void resolveOne(issue.id, "resolved")}
                          >
                            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" focusable="false">
                              <path
                                fill="none"
                                stroke="currentColor"
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth="1.8"
                                d="M4 12.5 9 17l11-11"
                              />
                            </svg>
                          </button>
                        )}
                        {status !== "dismissed" && (
                          <button
                            className="icon-action"
                            type="button"
                            title="Dismiss"
                            aria-label="Dismiss"
                            disabled={busy}
                            onClick={() => void resolveOne(issue.id, "dismissed")}
                          >
                            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" focusable="false">
                              <path
                                fill="none"
                                stroke="currentColor"
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth="1.8"
                                d="M6 6l12 12M18 6 6 18"
                              />
                            </svg>
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="metric-hint" style={{ marginTop: 12 }}>
            Showing {items.length} of {total}
          </p>
        </div>
      )}

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
