import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  type CategoryTree,
  type DataIssueType,
  type GmailMessageView,
  type Transaction,
} from "../api";
import ClassifyPanel from "../components/ClassifyPanel";
import EmailViewerModal from "../components/EmailViewerModal";
import FlagIssueModal from "../components/FlagIssueModal";
import SortHeader from "../components/SortHeader";
import { formatDate, formatMoney, formatSource } from "../format";

type Props = {
  needsReview?: boolean;
};

type DirectionFilter = "all" | "debit" | "credit";
type SortBy = "date" | "merchant" | "amount" | "category" | "source" | "status";
type SortDir = "asc" | "desc";

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function dateValue(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function calendarMonth(value: string): Date {
  const date = value ? new Date(`${value}T00:00:00`) : new Date();
  return new Date(date.getFullYear(), date.getMonth(), 1);
}

function DateFilter({
  label,
  value,
  min,
  max,
  onChange,
}: {
  label: string;
  value: string;
  min?: string;
  max?: string;
  onChange: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [month, setMonth] = useState(() => calendarMonth(value));
  const pickerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const closeOnOutsideClick = (event: MouseEvent) => {
      if (!pickerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", closeOnOutsideClick);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOnOutsideClick);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  const year = month.getFullYear();
  const monthIndex = month.getMonth();
  const firstWeekday = new Date(year, monthIndex, 1).getDay();
  const daysInMonth = new Date(year, monthIndex + 1, 0).getDate();
  const labelValue = value
    ? new Date(`${value}T00:00:00`).toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
      })
    : "Select date";

  return (
    <div className="date-filter" ref={pickerRef}>
      <span>{label}</span>
      <button
        className="date-filter-trigger"
        type="button"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => {
          setMonth(calendarMonth(value));
          setOpen((isOpen) => !isOpen);
        }}
      >
        {labelValue}
        <span aria-hidden="true">⌄</span>
      </button>
      {value && (
        <button
          className="date-filter-clear"
          type="button"
          aria-label={`Clear ${label.toLowerCase()} date`}
          title={`Clear ${label.toLowerCase()} date`}
          onClick={() => onChange("")}
        >
          ×
        </button>
      )}
      {open && (
        <div className="date-calendar" role="dialog" aria-label={`Choose ${label.toLowerCase()} date`}>
          <div className="date-calendar-header">
            <button
              type="button"
              aria-label="Previous month"
              onClick={() => setMonth(new Date(year, monthIndex - 1, 1))}
            >
              ‹
            </button>
            <strong>{month.toLocaleDateString(undefined, { month: "long", year: "numeric" })}</strong>
            <button
              type="button"
              aria-label="Next month"
              onClick={() => setMonth(new Date(year, monthIndex + 1, 1))}
            >
              ›
            </button>
          </div>
          <div className="date-calendar-grid">
            {WEEKDAYS.map((day) => (
              <span className="date-calendar-weekday" key={day}>{day}</span>
            ))}
            {Array.from({ length: firstWeekday }, (_, index) => (
              <span aria-hidden="true" key={`empty-${index}`} />
            ))}
            {Array.from({ length: daysInMonth }, (_, index) => {
              const day = index + 1;
              const nextValue = dateValue(new Date(year, monthIndex, day));
              const disabled = (min != null && nextValue < min) || (max != null && nextValue > max);
              return (
                <button
                  type="button"
                  key={nextValue}
                  disabled={disabled}
                  className={nextValue === value ? "selected" : ""}
                  onClick={() => {
                    onChange(nextValue);
                    setOpen(false);
                  }}
                >
                  {day}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function merchantLabel(tx: Transaction): string | null {
  return tx.merchant_normalized || tx.merchant_raw || null;
}

function truncate(text: string | null | undefined, max: number): string | null {
  if (!text) return null;
  return text.length > max ? `${text.slice(0, max)}…` : text;
}

export default function TransactionsPage({ needsReview = false }: Props) {
  const [items, setItems] = useState<Transaction[]>([]);
  const [total, setTotal] = useState(0);
  const [q, setQ] = useState("");
  const [debouncedQ, setDebouncedQ] = useState("");
  const [offset, setOffset] = useState(0);
  const [directionFilter, setDirectionFilter] = useState<DirectionFilter>("all");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [sortBy, setSortBy] = useState<SortBy>("date");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [error, setError] = useState<string | null>(null);
  const [categories, setCategories] = useState<CategoryTree[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [panelOpen, setPanelOpen] = useState(false);
  const [panelTargets, setPanelTargets] = useState<Transaction[]>([]);
  const [saving, setSaving] = useState(false);
  const [panelError, setPanelError] = useState<string | null>(null);
  const [viewerOpen, setViewerOpen] = useState(false);
  const [viewerLoading, setViewerLoading] = useState(false);
  const [viewerError, setViewerError] = useState<string | null>(null);
  const [viewerMessage, setViewerMessage] = useState<GmailMessageView | null>(null);
  const [viewerTransactionId, setViewerTransactionId] = useState<string | null>(null);
  const [flagOpen, setFlagOpen] = useState(false);
  const [flagTargets, setFlagTargets] = useState<Transaction[]>([]);
  const [flagSaving, setFlagSaving] = useState(false);
  const [flagError, setFlagError] = useState<string | null>(null);

  useEffect(() => {
    const t = setTimeout(() => {
      setDebouncedQ(q);
      setOffset(0); // Reset pagination on search
    }, 250);
    return () => clearTimeout(t);
  }, [q]);

  const load = useCallback(async (signal?: AbortSignal) => {
    setError(null);
    try {
      const data = await api.transactions(
        {
          needs_review: needsReview ? true : undefined,
          direction: directionFilter !== "all" ? directionFilter : undefined,
          q: debouncedQ.trim() || undefined,
          date_from: dateFrom || undefined,
          date_to: dateTo || undefined,
          limit: needsReview ? 100 : 50,
          offset,
          sort_by: sortBy,
          sort_dir: sortDir,
        },
        signal
      );
      setItems(data.items);
      setTotal(data.total);
      setSelectedIds(new Set());
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") return;
      setError(err instanceof Error ? err.message : "Failed to load");
    }
  }, [needsReview, debouncedQ, directionFilter, dateFrom, dateTo, offset, sortBy, sortDir]);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  // Reset offset when filter or sort changes
  useEffect(() => {
    setOffset(0);
  }, [directionFilter, dateFrom, dateTo, sortBy, sortDir]);

  function toggleSort(column: SortBy) {
    if (sortBy === column) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortBy(column);
      setSortDir("asc");
    }
  }

  useEffect(() => {
    if (!needsReview) return;
    let cancelled = false;
    api
      .categories()
      .then((data) => {
        if (!cancelled) setCategories(data.items);
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [needsReview]);

  const selectedCount = selectedIds.size;
  const allSelected = items.length > 0 && selectedCount === items.length;
  const someSelected = selectedCount > 0 && !allSelected;

  const selectedTransactions = useMemo(
    () => items.filter((tx) => selectedIds.has(tx.id)),
    [items, selectedIds],
  );

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
    setSelectedIds(new Set(items.map((tx) => tx.id)));
  }

  function openClassify(targets: Transaction[]) {
    if (targets.length === 0) return;
    setPanelTargets(targets);
    setPanelError(null);
    setPanelOpen(true);
  }

  function closePanel() {
    if (saving) return;
    setPanelOpen(false);
    setPanelTargets([]);
    setPanelError(null);
  }

  async function saveClassification(categoryId: string, subcategoryId: string | null) {
    if (panelTargets.length === 0) return;
    setSaving(true);
    setPanelError(null);
    try {
      const ids = panelTargets.map((tx) => tx.id);
      if (ids.length === 1) {
        await api.classifyTransaction(ids[0], {
          category_id: categoryId,
          subcategory_id: subcategoryId,
        });
      } else {
        await api.classifyTransactionsBulk({
          transaction_ids: ids,
          category_id: categoryId,
          subcategory_id: subcategoryId,
        });
      }
      applyRemoved(ids);
    } catch (err) {
      setPanelError(err instanceof Error ? err.message : "Failed to classify");
    } finally {
      setSaving(false);
    }
  }

  async function excludeSelected() {
    if (panelTargets.length === 0) return;
    setSaving(true);
    setPanelError(null);
    try {
      const ids = panelTargets.map((tx) => tx.id);
      await api.excludeTransactions(ids);
      applyRemoved(ids);
    } catch (err) {
      setPanelError(err instanceof Error ? err.message : "Failed to exclude");
    } finally {
      setSaving(false);
    }
  }

  async function reimburseSelected() {
    if (panelTargets.length === 0) return;
    setSaving(true);
    setPanelError(null);
    try {
      const ids = panelTargets.map((tx) => tx.id);
      await api.markReimbursed(ids);
      applyRemoved(ids);
    } catch (err) {
      setPanelError(err instanceof Error ? err.message : "Failed to mark as reimbursed");
    } finally {
      setSaving(false);
    }
  }

  function applyRemoved(ids: string[]) {
    const removed = new Set(ids);
    setItems((prev) => prev.filter((row) => !removed.has(row.id)));
    setTotal((n) => Math.max(0, n - ids.length));
    setSelectedIds((prev) => {
      const next = new Set(prev);
      for (const id of ids) next.delete(id);
      return next;
    });
    setPanelOpen(false);
    setPanelTargets([]);
  }

  async function openEmail(tx: Transaction) {
    const messageId = tx.source_email_id;
    if (!messageId) return;
    setViewerOpen(true);
    setViewerLoading(true);
    setViewerError(null);
    setViewerMessage(null);
    setViewerTransactionId(tx.id);
    try {
      const message = await api.fetchGmailMessage(messageId);
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
    setViewerTransactionId(null);
    setViewerError(null);
    setViewerLoading(false);
  }

  function openFlag(targets: Transaction[]) {
    if (targets.length === 0) return;
    setFlagTargets(targets);
    setFlagError(null);
    setFlagOpen(true);
  }

  function closeFlag() {
    if (flagSaving) return;
    setFlagOpen(false);
    setFlagTargets([]);
    setFlagError(null);
  }

  async function submitFlag(body: {
    issue_type: DataIssueType;
    field_name?: string | null;
    suggested_value?: string | null;
    note?: string | null;
  }) {
    if (flagTargets.length === 0) return;
    setFlagSaving(true);
    setFlagError(null);
    try {
      const ids = flagTargets.map((tx) => tx.id);
      if (ids.length === 1) {
        await api.flagIssue(ids[0], body);
      } else {
        await api.flagIssuesBulk({ transaction_ids: ids, ...body });
      }
      // Flagged transactions are hidden from these tables until the flag is resolved.
      applyRemoved(ids);
      setFlagOpen(false);
      setFlagTargets([]);
    } catch (err) {
      setFlagError(err instanceof Error ? err.message : "Failed to flag issue");
    } finally {
      setFlagSaving(false);
    }
  }

  return (
    <section className="panel section">
      <h2>{needsReview ? "Needs review" : "Transactions"}</h2>
      <p className="lead">
        {needsReview
          ? "Select one or more rows, then classify them together."
          : "Searchable ledger of normalized transactions."}
      </p>

      <div className="toolbar">
        <input
          className="input"
          placeholder="Search merchant or description"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <DateFilter label="From" value={dateFrom} max={dateTo || undefined} onChange={setDateFrom} />
        <DateFilter label="To" value={dateTo} min={dateFrom || undefined} onChange={setDateTo} />
        <div className="segmented" role="group" aria-label="Direction filter">
          {(
            [
              ["all", "Both"],
              ["debit", "Debit only"],
              ["credit", "Credit only"],
            ] as const
          ).map(([value, label]) => (
            <button
              key={value}
              type="button"
              className={`segmented-btn${directionFilter === value ? " active" : ""}`}
              aria-pressed={directionFilter === value}
              onClick={() => setDirectionFilter(value)}
            >
              {label}
            </button>
          ))}
        </div>
        <button
          className="icon-action"
          type="button"
          title="Refresh transactions"
          aria-label="Refresh transactions"
          onClick={() => void load()}
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

      {needsReview && selectedCount > 0 && (
        <div className="review-action-bar" role="region" aria-label="Bulk actions">
          <span>
            <strong>{selectedCount}</strong> selected
          </span>
          <div className="review-action-buttons">
            <button
              className="btn primary"
              type="button"
              onClick={() => openClassify(selectedTransactions)}
            >
              Classify selected
            </button>
            <button className="btn" type="button" onClick={() => openFlag(selectedTransactions)}>
              Flag selected
            </button>
            <button className="btn" type="button" onClick={() => setSelectedIds(new Set())}>
              Clear selection
            </button>
          </div>
        </div>
      )}

      {error && <p className="error">{error}</p>}

      {items.length === 0 ? (
        <div className="empty">
          {needsReview
            ? "Nothing left to review. Nice."
            : "No transactions yet. Connect Gmail in Settings to start syncing."}
        </div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                {needsReview && (
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
                )}
                <SortHeader label="Date" active={sortBy === "date"} dir={sortDir} onClick={() => toggleSort("date")} />
                <SortHeader label="Merchant" active={sortBy === "merchant"} dir={sortDir} onClick={() => toggleSort("merchant")} />
                <SortHeader
                  label="Amount"
                  className="num"
                  active={sortBy === "amount"}
                  dir={sortDir}
                  onClick={() => toggleSort("amount")}
                />
                <SortHeader
                  label="Category"
                  active={sortBy === "category"}
                  dir={sortDir}
                  onClick={() => toggleSort("category")}
                />
                <SortHeader label="Source" active={sortBy === "source"} dir={sortDir} onClick={() => toggleSort("source")} />
                {needsReview ? (
                  <th>Action</th>
                ) : (
                  <SortHeader
                    label="Status"
                    active={sortBy === "status"}
                    dir={sortDir}
                    onClick={() => toggleSort("status")}
                  />
                )}
                <th />
              </tr>
            </thead>
            <tbody>
              {items.map((tx) => {
                const selected = selectedIds.has(tx.id);
                return (
                  <tr
                    key={tx.id}
                    className={[
                      tx.direction === "credit" ? "tx-row credit" : "tx-row debit",
                      needsReview ? "selectable" : "",
                      needsReview && selected ? "tx-selected" : "",
                    ]
                      .filter(Boolean)
                      .join(" ")}
                    onClick={needsReview ? () => toggleOne(tx.id) : undefined}
                  >
                    {needsReview && (
                      <td className="col-check" onClick={(e) => e.stopPropagation()}>
                        <input
                          type="checkbox"
                          checked={selected}
                          onChange={() => toggleOne(tx.id)}
                          aria-label={`Select ${merchantLabel(tx) ?? "transaction"}`}
                        />
                      </td>
                    )}
                    <td className="tx-date">{formatDate(tx.transaction_date)}</td>
                    <td>
                      <div>{merchantLabel(tx) ?? truncate(tx.description, 80) ?? "Uncategorized transaction"}</div>
                      {merchantLabel(tx) && tx.description && (
                        <div className="metric-hint" style={{ marginTop: 2 }}>
                          {truncate(tx.description, 80)}
                        </div>
                      )}
                    </td>
                    <td className="tx-amount num">
                      {tx.direction === "credit" ? "+" : "−"}
                      {formatMoney(tx.amount ?? 0, tx.currency)}
                    </td>
                    <td>
                      {tx.category ?? "Uncategorized"}
                      {tx.subcategory ? (
                        <div className="metric-hint" style={{ marginTop: 2 }}>
                          {tx.subcategory}
                        </div>
                      ) : null}
                    </td>
                    <td>{formatSource(tx.classification_source)}</td>
                    <td onClick={needsReview ? (event) => event.stopPropagation() : undefined}>
                      {needsReview ? (
                        <button
                          className="icon-action"
                          type="button"
                          title="Classify"
                          aria-label="Classify transaction"
                          onClick={() => openClassify([tx])}
                        >
                          <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" focusable="false">
                            <path fill="currentColor" d="M17.63 5.84C17.27 5.33 16.67 5 16 5L5 5.01C3.9 5.01 3 5.9 3 7v10c0 1.1.9 1.99 2 1.99L16 19c.67 0 1.27-.33 1.63-.84L22 12l-4.37-6.16zM16 17H5V7h11l3.55 5L16 17zm-9.5-3.5c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5z" />
                          </svg>
                        </button>
                      ) : (
                        <span className={`badge ${tx.needs_review ? "review" : "ok"}`}>
                          {tx.needs_review ? "Review" : "OK"}
                        </span>
                      )}
                    </td>
                    <td className="row-actions" onClick={(e) => e.stopPropagation()}>
                      {tx.source_email_id ? (
                        <button
                          className="gmail-link"
                          type="button"
                          title="View source email"
                          aria-label="View source email"
                          onClick={() => void openEmail(tx)}
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
                      ) : (
                        <span className="metric-hint">—</span>
                      )}
                      <button
                        className="icon-action"
                        type="button"
                        title="Flag a data issue"
                        aria-label="Flag a data issue"
                        onClick={() => openFlag([tx])}
                      >
                        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" focusable="false">
                          <path
                            fill="currentColor"
                            d="M14.4 6 14 4H5v17h2v-7h5.6l.4 2h7V6z"
                          />
                        </svg>
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 12 }}>
            <p className="metric-hint" style={{ margin: 0 }}>
              Showing {items.length} of {total}
            </p>
            {total > (needsReview ? 100 : 50) && (
              <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                <button
                  className="btn"
                  disabled={offset === 0}
                  onClick={() => setOffset((o) => Math.max(0, o - (needsReview ? 100 : 50)))}
                >
                  Previous
                </button>
                <span className="metric-hint">
                  Page {Math.floor(offset / (needsReview ? 100 : 50)) + 1} of {Math.ceil(total / (needsReview ? 100 : 50))}
                </span>
                <button
                  className="btn"
                  disabled={offset + (needsReview ? 100 : 50) >= total}
                  onClick={() => setOffset((o) => o + (needsReview ? 100 : 50))}
                >
                  Next
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {needsReview && (
        <ClassifyPanel
          open={panelOpen}
          transactions={panelTargets}
          categories={categories}
          saving={saving}
          error={panelError}
          onClose={closePanel}
          onSave={(categoryId, subcategoryId) => void saveClassification(categoryId, subcategoryId)}
          onExclude={() => void excludeSelected()}
          onReimburse={() => void reimburseSelected()}
          onFlag={(tx) => {
            closePanel();
            openFlag([tx]);
          }}
        />
      )}

      <EmailViewerModal
        open={viewerOpen}
        loading={viewerLoading}
        error={viewerError}
        message={viewerMessage}
        transactionId={viewerTransactionId}
        onClose={closeViewer}
      />

      <FlagIssueModal
        open={flagOpen}
        transactions={flagTargets}
        saving={flagSaving}
        error={flagError}
        onClose={closeFlag}
        onSubmit={(body) => void submitFlag(body)}
      />
    </section>
  );
}
