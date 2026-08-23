import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useSearchParams } from "react-router-dom";
import {
  api,
  type Account,
  type CategoryTree,
  type DataIssueType,
  type GmailMessageView,
  type Transaction,
} from "../api";
import ClassifyPanel from "../components/ClassifyPanel";
import EmailViewerModal from "../components/EmailViewerModal";
import FlagIssueModal from "../components/FlagIssueModal";
import MarkRecurringModal from "../components/MarkRecurringModal";
import SortHeader from "../components/SortHeader";
import TransactionDetailModal from "../components/TransactionDetailModal";
import PageHeader from "../components/common/PageHeader";
import AccountBadge from "../components/common/AccountBadge";
import { getCategoryIcon } from "../utils/categoryIcons";
import { formatDate, formatMoney } from "../format";

type Props = {
  needsReview?: boolean;
};

type DirectionFilter = "all" | "debit" | "credit";
type SortBy = "date" | "merchant" | "amount" | "category" | "source" | "status";
type SortDir = "asc" | "desc";

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function resolveCategoryTokens(tokens: string[], categoryList: CategoryTree[]): Set<string> {
  const result = new Set<string>();
  for (const token of tokens) {
    if (!token) continue;
    const lower = token.toLowerCase();
    if (lower === "uncategorized") {
      result.add("uncategorized");
      continue;
    }
    const matched = categoryList.find(
      (c) => c.id === token || c.slug.toLowerCase() === lower || c.name.toLowerCase() === lower
    );
    if (matched) {
      result.add(matched.id);
    } else {
      result.add(token);
    }
  }
  return result;
}

function dateValue(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function calendarMonth(value: string): Date {
  if (!value) return new Date();
  const parsed = new Date(`${value}T00:00:00`);
  return Number.isNaN(parsed.getTime()) ? new Date() : parsed;
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
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => {
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
    : "All";

  return (
    <div className="date-filter" ref={pickerRef}>
      <div className="date-filter-input-wrap">
        <button
          className="date-filter-trigger"
          type="button"
          aria-haspopup="dialog"
          aria-expanded={open}
          onClick={() => {
            setMonth(calendarMonth(value));
            setOpen((isOpen) => !isOpen);
          }}
          style={{
            background: value ? "var(--surface)" : "var(--surface)",
            fontWeight: value ? 600 : 400,
          }}
        >
          <span style={{ color: "var(--ink-muted)", fontWeight: 500, marginRight: 2 }}>{label}:</span>
          <span style={{ color: value ? "var(--ink)" : "var(--ink-muted)" }}>{labelValue}</span>
          <span className="date-filter-chevron" aria-hidden="true" style={{ opacity: value ? 0 : 0.6 }}>▾</span>
        </button>
        {value && (
          <button
            className="date-filter-clear"
            type="button"
            aria-label={`Clear ${label.toLowerCase()} date`}
            title={`Clear ${label.toLowerCase()} date`}
            onClick={(e) => {
              e.stopPropagation();
              onChange("");
            }}
          >
            ×
          </button>
        )}
      </div>
      {open && createPortal(
        <div
          className="date-calendar-overlay"
          role="presentation"
          onClick={() => setOpen(false)}
        >
          <div
            className="date-calendar date-calendar-modal"
            role="dialog"
            aria-modal="true"
            aria-label={`Choose ${label.toLowerCase()} date`}
            onClick={(e) => e.stopPropagation()}
          >
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
            <div className="date-calendar-footer">
              {value && (
                <button
                  type="button"
                  className="btn quiet"
                  style={{ fontSize: "0.82rem", padding: "6px 12px" }}
                  onClick={() => {
                    onChange("");
                    setOpen(false);
                  }}
                >
                  Clear Date
                </button>
              )}
              <button
                type="button"
                className="btn primary"
                style={{ fontSize: "0.82rem", padding: "6px 16px", marginLeft: "auto" }}
                onClick={() => setOpen(false)}
              >
                Done
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}
    </div>
  );
}

function merchantLabel(tx: Transaction): string | null {
  return tx.merchant_normalized || tx.merchant_raw || null;
}

export default function TransactionsPage({ needsReview = false }: Props) {
  const [searchParams] = useSearchParams();
  const [items, setItems] = useState<Transaction[]>([]);
  const [total, setTotal] = useState(0);
  const [totalDebit, setTotalDebit] = useState(0);
  const [totalCredit, setTotalCredit] = useState(0);
  const [pageSize, setPageSize] = useState<number>(needsReview ? 100 : 50);

  const [q, setQ] = useState(() => searchParams.get("q") || "");
  const [debouncedQ, setDebouncedQ] = useState(() => searchParams.get("q") || "");

  // Multi-category selection state
  const [selectedCategoryIds, setSelectedCategoryIds] = useState<Set<string>>(() => {
    const param =
      searchParams.get("category_ids") ||
      searchParams.get("category_id") ||
      searchParams.get("category") ||
      "";
    if (!param) return new Set();
    return new Set(param.split(",").map((s) => s.trim()).filter(Boolean));
  });
  const [categoryDropdownOpen, setCategoryDropdownOpen] = useState(false);

  const [selectedAccount, setSelectedAccount] = useState<string>(() => searchParams.get("account") || "");
  const [offset, setOffset] = useState(0);
  const [directionFilter, setDirectionFilter] = useState<DirectionFilter>("all");
  const [dateFrom, setDateFrom] = useState(() => searchParams.get("date_from") || "");
  const [dateTo, setDateTo] = useState(() => searchParams.get("date_to") || "");
  const [sortBy, setSortBy] = useState<SortBy>("date");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [error, setError] = useState<string | null>(null);
  const [mobileFiltersExpanded, setMobileFiltersExpanded] = useState(false);

  const activeFilterCount = useMemo(() => {
    let count = 0;
    if (directionFilter !== "all") count++;
    if (selectedCategoryIds.size > 0) count++;
    if (selectedAccount) count++;
    if (dateFrom || dateTo) count++;
    return count;
  }, [directionFilter, selectedCategoryIds, selectedAccount, dateFrom, dateTo]);

  const [categories, setCategories] = useState<CategoryTree[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  // Detail Modal State
  const [detailTx, setDetailTx] = useState<Transaction | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);

  // Classify Panel State
  const [panelOpen, setPanelOpen] = useState(false);
  const [panelTargets, setPanelTargets] = useState<Transaction[]>([]);
  const [saving, setSaving] = useState(false);
  const [panelError, setPanelError] = useState<string | null>(null);

  // Email Viewer Modal State
  const [viewerOpen, setViewerOpen] = useState(false);
  const [viewerLoading, setViewerLoading] = useState(false);
  const [viewerError, setViewerError] = useState<string | null>(null);
  const [viewerMessage, setViewerMessage] = useState<GmailMessageView | null>(null);
  const [viewerTransactionId, setViewerTransactionId] = useState<string | null>(null);

  // Flag Issue Modal State
  const [flagOpen, setFlagOpen] = useState(false);
  const [flagTargets, setFlagTargets] = useState<Transaction[]>([]);
  const [flagSaving, setFlagSaving] = useState(false);
  const [flagError, setFlagError] = useState<string | null>(null);

  // Recurring Modal State
  const [recurringOpen, setRecurringOpen] = useState(false);
  const [recurringTarget, setRecurringTarget] = useState<Transaction | null>(null);

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

  // Sync state with URL params
  useEffect(() => {
    const urlQ = searchParams.get("q") || "";
    const urlCategory = searchParams.get("category_ids") || searchParams.get("category_id") || searchParams.get("category") || "";
    const urlAccount = searchParams.get("account") || "";
    const urlFrom = searchParams.get("date_from") || "";
    const urlTo = searchParams.get("date_to") || "";
    setQ(urlQ);
    setDebouncedQ(urlQ);
    if (urlCategory) {
      const tokens = urlCategory.split(",").map((s) => s.trim()).filter(Boolean);
      setSelectedCategoryIds(categories.length > 0 ? resolveCategoryTokens(tokens, categories) : new Set(tokens));
    } else {
      setSelectedCategoryIds(new Set());
    }
    setSelectedAccount(urlAccount);
    setDateFrom(urlFrom);
    setDateTo(urlTo);
    setOffset(0);
  }, [searchParams, categories]);

  useEffect(() => {
    const t = setTimeout(() => {
      setDebouncedQ(q);
      setOffset(0);
    }, 250);
    return () => clearTimeout(t);
  }, [q]);

  // Load categories & accounts on mount
  useEffect(() => {
    let cancelled = false;
    api
      .categories()
      .then((data) => {
        if (!cancelled) {
          setCategories(data.items);
          const urlCategory = searchParams.get("category_ids") || searchParams.get("category_id") || searchParams.get("category") || "";
          if (urlCategory) {
            const tokens = urlCategory.split(",").map((s) => s.trim()).filter(Boolean);
            setSelectedCategoryIds(resolveCategoryTokens(tokens, data.items));
          }
        }
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      });

    api
      .accounts()
      .then((data) => {
        if (!cancelled) setAccounts(data.accounts || []);
      })
      .catch(() => {
        // Accounts are non-blocking
      });

    return () => {
      cancelled = true;
    };
  }, [searchParams]);

  const load = useCallback(
    async (signal?: AbortSignal) => {
      setError(null);
      try {
        let catIds: string[] | undefined = undefined;
        const directionParam = directionFilter !== "all" ? directionFilter : undefined;
        const statusParam = needsReview ? "review" : "ok";

        if (selectedCategoryIds.size > 0) {
          catIds = Array.from(selectedCategoryIds);
        }

        const data = await api.transactions(
          {
            needs_review: needsReview ? true : undefined,
            direction: directionParam,
            status: statusParam,
            account: selectedAccount || undefined,
            q: debouncedQ.trim() || undefined,
            category_ids: catIds,
            date_from: dateFrom || undefined,
            date_to: dateTo || undefined,
            limit: pageSize,
            offset,
            sort_by: sortBy,
            sort_dir: sortDir,
          },
          signal
        );
        setItems(data.items);
        setTotal(data.total);
        setTotalDebit(data.total_debit ?? 0);
        setTotalCredit(data.total_credit ?? 0);
        setSelectedIds(new Set());
      } catch (err) {
        if (err instanceof Error && err.name === "AbortError") return;
        setError(err instanceof Error ? err.message : "Failed to load");
      }
    },
    [
      needsReview,
      directionFilter,
      selectedCategoryIds,
      selectedAccount,
      debouncedQ,
      dateFrom,
      dateTo,
      pageSize,
      offset,
      sortBy,
      sortDir,
    ]
  );

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  // Reset pagination when any filter changes
  useEffect(() => {
    setOffset(0);
  }, [directionFilter, selectedCategoryIds, selectedAccount, dateFrom, dateTo, pageSize, sortBy, sortDir]);

  function toggleSort(column: SortBy) {
    if (sortBy === column) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortBy(column);
      setSortDir("asc");
    }
  }

  const selectedCount = selectedIds.size;
  const allSelected = items.length > 0 && selectedCount === items.length;
  const someSelected = selectedCount > 0 && !allSelected;

  const selectedTransactions = useMemo(
    () => items.filter((tx) => selectedIds.has(tx.id)),
    [items, selectedIds]
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
      if (needsReview) {
        applyRemoved(ids);
      } else {
        const chosenCat = categories.find((c) => c.id === categoryId);
        const chosenSub = chosenCat?.subcategories.find((s) => s.id === subcategoryId);
        setItems((prev) =>
          prev.map((t) =>
            ids.includes(t.id)
              ? {
                  ...t,
                  category_id: categoryId,
                  subcategory_id: subcategoryId,
                  category: chosenCat?.name || t.category,
                  subcategory: chosenSub?.name || null,
                  needs_review: false,
                  user_verified: true,
                }
              : t
          )
        );
        setPanelOpen(false);
        setPanelTargets([]);
      }
      if (detailTx && ids.includes(detailTx.id)) {
        setDetailOpen(false);
        setDetailTx(null);
      }
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
      applyRemoved(ids);
      setFlagOpen(false);
      setFlagTargets([]);
      if (detailTx && ids.includes(detailTx.id)) {
        setDetailOpen(false);
        setDetailTx(null);
      }
    } catch (err) {
      setFlagError(err instanceof Error ? err.message : "Failed to flag issue");
    } finally {
      setFlagSaving(false);
    }
  }

  function openRecurring(tx: Transaction) {
    setRecurringTarget(tx);
    setRecurringOpen(true);
  }

  function closeRecurring() {
    setRecurringOpen(false);
    setRecurringTarget(null);
  }

  function handleRowClick(tx: Transaction) {
    // In needs review mode, clicking row toggles checkbox
    if (needsReview) {
      toggleOne(tx.id);
      return;
    }
    // Otherwise, open detail modal
    setDetailTx(tx);
    setDetailOpen(true);
  }

  const distinctAccounts = useMemo(() => {
    const list: string[] = [];
    const seen = new Set<string>();
    accounts.forEach((a) => {
      const name = a.account_number_masked ? `${a.name} (${a.account_number_masked})` : a.name;
      if (!seen.has(name)) {
        seen.add(name);
        list.push(name);
      }
    });
    return list;
  }, [accounts]);

  const currentPage = Math.floor(offset / pageSize) + 1;
  const totalPages = Math.ceil(total / pageSize) || 1;

  return (
    <section className="panel section" style={{ maxWidth: 1160, margin: "0 auto" }}>
      {/* Header */}
      <PageHeader
        title={needsReview ? "Needs Review" : "Classified Transactions"}
        subtitle={
          needsReview
            ? "Review and batch-classify unclassified transactions to improve model memory."
            : "Searchable, durable ledger of classified and verified financial movements."
        }
      />

      {/* ───────────────────────────────────────────────────────────── */}
      {/* STICKY FILTER BAR                                             */}
      {/* ───────────────────────────────────────────────────────────── */}
      <div className="sticky-filters">
        {/* Top Search & Action Bar */}
        <div style={{ display: "flex", gap: "8px", alignItems: "center", width: "100%" }}>
          {/* Search Box */}
          <div style={{ flex: "1 1 240px", minWidth: "160px" }}>
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
              placeholder="Search merchant, description, account... (Press '/' to focus)"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </div>

          {/* Mobile Filter Toggle Button */}
          <button
            type="button"
            className="btn quiet filters-mobile-toggle"
            style={{
              height: 36,
              minHeight: 36,
              fontSize: "0.84rem",
              padding: "0 10px",
              border: "1px solid var(--line)",
              borderRadius: "var(--radius-sm)",
              alignItems: "center",
              gap: 5,
              background: mobileFiltersExpanded || activeFilterCount > 0 ? "var(--surface)" : "transparent",
              fontWeight: activeFilterCount > 0 ? 600 : 400,
              flexShrink: 0,
              boxSizing: "border-box",
            }}
            onClick={() => setMobileFiltersExpanded((prev) => !prev)}
            aria-expanded={mobileFiltersExpanded}
          >
            <span>Filters{activeFilterCount > 0 ? ` (${activeFilterCount})` : ""}</span>
            <span style={{ fontSize: "0.68rem", opacity: 0.7 }}>{mobileFiltersExpanded ? "▲" : "▼"}</span>
          </button>

          {/* Refresh Button */}
          <button
            className="icon-action"
            type="button"
            title="Refresh transactions"
            aria-label="Refresh transactions"
            onClick={() => void load()}
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

        {/* Detailed Controls (Inline on Desktop, Expandable on Mobile) */}
        <div className={`filters-desktop-wrap${mobileFiltersExpanded ? " expanded-mobile" : ""}`} style={{ marginTop: "8px" }}>
          {/* Date Pickers */}
          <div className="date-filter-group" style={{ display: "flex", gap: "6px" }}>
            <DateFilter label="From" value={dateFrom} max={dateTo || undefined} onChange={setDateFrom} />
            <DateFilter label="To" value={dateTo} min={dateFrom || undefined} onChange={setDateTo} />
          </div>

          {/* Direction Segmented Control */}
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

          {/* Multi-Category Selector Popover & Account Dropdown (Only for Classified view) */}
          {!needsReview && (
            <>
              {/* Multi-Category Selector Popover */}
              <div style={{ position: "relative" }}>
                <button
                  type="button"
                  className="input"
                  style={{
                    height: 36,
                    minHeight: 36,
                    fontSize: "0.84rem",
                    padding: "0 10px",
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 6,
                    cursor: "pointer",
                    minWidth: 140,
                    borderRadius: "var(--radius-sm)",
                    border: "1px solid var(--line)",
                    background: "var(--surface)",
                    fontWeight: selectedCategoryIds.size > 0 ? 600 : 400,
                    boxSizing: "border-box",
                  }}
                  onClick={() => setCategoryDropdownOpen((prev) => !prev)}
                  aria-haspopup="dialog"
                  aria-expanded={categoryDropdownOpen}
                >
                  <span style={{ color: "var(--ink-muted)", fontWeight: 500 }}>Category:</span>
                  <span style={{ color: selectedCategoryIds.size > 0 ? "var(--ink)" : "var(--ink-muted)" }}>
                    {selectedCategoryIds.size === 0 ? "All" : `(${selectedCategoryIds.size})`}
                  </span>
                  <span style={{ fontSize: "0.75rem", opacity: 0.6, marginLeft: "auto" }}>▾</span>
                </button>

                {categoryDropdownOpen && (
                  <>
                    <div
                      style={{ position: "fixed", inset: 0, zIndex: 30 }}
                      onClick={() => setCategoryDropdownOpen(false)}
                    />
                    <div
                      style={{
                        position: "absolute",
                        top: "calc(100% + 4px)",
                        left: 0,
                        zIndex: 31,
                        background: "var(--surface)",
                        border: "1px solid var(--line)",
                        borderRadius: "var(--radius-sm)",
                        boxShadow: "0 6px 20px rgba(0,0,0,0.15)",
                        padding: "8px",
                        minWidth: "220px",
                        maxHeight: "320px",
                        overflowY: "auto",
                      }}
                    >
                      <div
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          paddingBottom: "6px",
                          marginBottom: "6px",
                          borderBottom: "1px solid var(--line)",
                        }}
                      >
                        <button
                          type="button"
                          className="btn quiet"
                          style={{ fontSize: "0.75rem", padding: "2px 6px" }}
                          onClick={() => {
                            setSelectedCategoryIds(new Set());
                            setOffset(0);
                          }}
                        >
                          Clear All
                        </button>
                        <button
                          type="button"
                          className="btn quiet"
                          style={{ fontSize: "0.75rem", padding: "2px 6px" }}
                          onClick={() => {
                            setSelectedCategoryIds(new Set(categories.map((c) => c.id).concat("uncategorized")));
                            setOffset(0);
                          }}
                        >
                          Select All
                        </button>
                      </div>

                      <label
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: "8px",
                          padding: "5px 6px",
                          fontSize: "0.84rem",
                          cursor: "pointer",
                          borderRadius: "var(--radius-sm)",
                        }}
                      >
                        <input
                          type="checkbox"
                          checked={selectedCategoryIds.has("uncategorized")}
                          onChange={() => {
                            setSelectedCategoryIds((prev) => {
                              const next = new Set(prev);
                              if (next.has("uncategorized")) next.delete("uncategorized");
                              else next.add("uncategorized");
                              return next;
                            });
                            setOffset(0);
                          }}
                        />
                        <span>Uncategorized</span>
                      </label>

                      {categories.map((c) => {
                        const isChecked = selectedCategoryIds.has(c.id);
                        return (
                          <label
                            key={c.id}
                            style={{
                              display: "flex",
                              alignItems: "center",
                              gap: "8px",
                              padding: "5px 6px",
                              fontSize: "0.84rem",
                              cursor: "pointer",
                              borderRadius: "var(--radius-sm)",
                            }}
                          >
                            <input
                              type="checkbox"
                              checked={isChecked}
                              onChange={() => {
                                setSelectedCategoryIds((prev) => {
                                  const next = new Set(prev);
                                  if (next.has(c.id)) next.delete(c.id);
                                  else next.add(c.id);
                                  return next;
                                });
                                setOffset(0);
                              }}
                            />
                            <span>{getCategoryIcon(c.name, c.expense_type)} {c.name}</span>
                          </label>
                        );
                      })}
                    </div>
                  </>
                )}
              </div>

              {/* Account Dropdown */}
              <select
                className="input"
                style={{
                  height: 36,
                  minHeight: 36,
                  fontSize: "0.84rem",
                  padding: "0 10px",
                  width: "auto",
                  minWidth: 140,
                  borderRadius: "var(--radius-sm)",
                  border: "1px solid var(--line)",
                  background: "var(--surface)",
                  cursor: "pointer",
                  boxSizing: "border-box",
                }}
                value={selectedAccount}
                onChange={(e) => setSelectedAccount(e.target.value)}
                aria-label="Filter by Account"
              >
                <option value="">Account: All</option>
                {distinctAccounts.map((acc) => (
                  <option key={acc} value={acc}>
                    {acc}
                  </option>
                ))}
                <option value="unlinked">Unlinked / Unknown</option>
              </select>
            </>
          )}

          {/* Page Size Selector (Only in Needs Review mode) */}
          {needsReview && (
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
              onChange={(e) => setPageSize(Number(e.target.value))}
              title="Rows per page"
              aria-label="Rows per page"
            >
              <option value={25}>25 / page</option>
              <option value={50}>50 / page</option>
              <option value={100}>100 / page</option>
            </select>
          )}
        </div>
      </div>

      {/* Review Bulk Action Bar (Needs Review mode) */}
      {needsReview && selectedCount > 0 && (
        <div className="review-action-bar" role="region" aria-label="Bulk actions">
          <span>
            <strong>{selectedCount}</strong> selected
          </span>
          <div className="review-action-buttons">
            <button className="btn primary" type="button" onClick={() => openClassify(selectedTransactions)}>
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

      {/* ───────────────────────────────────────────────────────────── */}
      {/* TRANSACTION TABLE / LIST                                      */}
      {/* ───────────────────────────────────────────────────────────── */}
      {items.length === 0 ? (
        <div className="empty" style={{ padding: "36px 0" }}>
          {needsReview
            ? "Nothing left to review. All transactions are classified."
            : "No transactions found matching your filter criteria."}
        </div>
      ) : (
        <div className="table-wrap">
          {/* Desktop Table View (>= 768px) */}
          <div className="tx-table-desktop">
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
                  <SortHeader label="Merchant / Description" active={sortBy === "merchant"} dir={sortDir} onClick={() => toggleSort("merchant")} />
                  <SortHeader label="Category" active={sortBy === "category"} dir={sortDir} onClick={() => toggleSort("category")} />
                  <th>Account</th>
                  <SortHeader label="Amount" className="num" active={sortBy === "amount"} dir={sortDir} onClick={() => toggleSort("amount")} />
                  {needsReview && <th style={{ width: 80 }}>Action</th>}
                </tr>
              </thead>
              <tbody>
                {items.map((tx) => {
                  const selected = selectedIds.has(tx.id);
                  const isCredit = tx.direction === "credit";
                  const merchant = merchantLabel(tx) ?? "Unidentified merchant";
                  const isLargeAmount = (tx.amount ?? 0) >= 30000;

                  return (
                    <tr
                      key={tx.id}
                      className={[
                        isCredit ? "tx-row credit" : "tx-row debit",
                        "clickable",
                        needsReview && selected ? "tx-selected" : "",
                      ]
                        .filter(Boolean)
                        .join(" ")}
                      style={{ cursor: "pointer" }}
                      onClick={() => handleRowClick(tx)}
                      title="Click to view details & audit trail"
                    >
                      {needsReview && (
                        <td className="col-check" onClick={(e) => e.stopPropagation()}>
                          <input
                            type="checkbox"
                            checked={selected}
                            onChange={() => toggleOne(tx.id)}
                            aria-label={`Select ${merchant}`}
                          />
                        </td>
                      )}

                      {/* Date Column */}
                      <td className="tx-date" style={{ whiteSpace: "nowrap", fontSize: "0.85rem", color: "var(--ink)" }}>
                        {formatDate(tx.transaction_date)}
                      </td>

                      {/* Merchant & Description (Two-line structure with ellipsis) */}
                      <td style={{ maxWidth: 280, paddingRight: 16 }}>
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
                        {tx.description && (
                          <div
                            style={{
                              fontSize: "0.78rem",
                              color: "var(--ink-muted)",
                              marginTop: 1,
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                              whiteSpace: "nowrap",
                            }}
                            title={tx.description}
                          >
                            {tx.description}
                          </div>
                        )}
                      </td>

                      {/* Category & Subcategory + Quick Edit Button */}
                      <td style={{ minWidth: 160, maxWidth: 240, paddingRight: 12 }}>
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 6 }}>
                          <div style={{ minWidth: 0, flex: "1 1 auto" }}>
                            {tx.category ? (
                              <>
                                <div
                                  style={{
                                    display: "flex",
                                    alignItems: "center",
                                    gap: 6,
                                    fontWeight: 600,
                                    fontSize: "14px",
                                    color: "var(--ink)",
                                    lineHeight: 1.25,
                                  }}
                                >
                                  <span
                                    style={{
                                      width: 20,
                                      minWidth: 20,
                                      fontSize: "14px",
                                      lineHeight: 1,
                                      display: "inline-flex",
                                      alignItems: "center",
                                      justifyContent: "center",
                                      flexShrink: 0,
                                    }}
                                    aria-hidden="true"
                                  >
                                    {getCategoryIcon(tx.category)}
                                  </span>
                                  <span
                                    style={{
                                      overflow: "hidden",
                                      textOverflow: "ellipsis",
                                      whiteSpace: "nowrap",
                                    }}
                                    title={tx.category}
                                  >
                                    {tx.category}
                                  </span>
                                </div>
                                {tx.subcategory && (
                                  <div
                                    style={{
                                      fontSize: "12px",
                                      color: "var(--ink-muted)",
                                      fontWeight: 400,
                                      marginTop: 1,
                                      paddingLeft: 26,
                                      overflow: "hidden",
                                      textOverflow: "ellipsis",
                                      whiteSpace: "nowrap",
                                      lineHeight: 1.2,
                                    }}
                                    title={tx.subcategory}
                                  >
                                    {tx.subcategory}
                                  </div>
                                )}
                              </>
                            ) : (
                              <div style={{ color: "var(--ink-muted)", fontSize: "14px", fontWeight: 400 }}>
                                Uncategorized
                              </div>
                            )}
                          </div>
                          {!needsReview && (
                            <button
                              type="button"
                              className="btn quiet icon-btn"
                              style={{
                                width: 24,
                                height: 24,
                                padding: 0,
                                display: "inline-flex",
                                alignItems: "center",
                                justifyContent: "center",
                                color: "var(--ink-muted)",
                                border: "1px solid var(--line)",
                                borderRadius: "var(--radius-sm)",
                                flexShrink: 0,
                                opacity: 0.5,
                              }}
                              title={`Modify classification for ${merchant}`}
                              aria-label={`Modify classification for ${merchant}`}
                              onClick={(e) => {
                                e.stopPropagation();
                                openClassify([tx]);
                              }}
                            >
                              <svg viewBox="0 0 24 24" width="12" height="12" aria-hidden="true" focusable="false">
                                <path
                                  fill="none"
                                  stroke="currentColor"
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                  strokeWidth="2"
                                  d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"
                                />
                              </svg>
                            </button>
                          )}
                        </div>
                      </td>

                      {/* Account / Payment Method */}
                      <td style={{ color: "var(--ink)", fontSize: "0.82rem", whiteSpace: "nowrap" }}>
                        {tx.account ? (
                          <AccountBadge accountName={tx.account} logoSize={18} showIdentifiers={false} />
                        ) : (
                          <span style={{ color: "var(--ink-muted)" }}>—</span>
                        )}
                      </td>

                      {/* Amount (Heavier weight for large amounts, strictly right-aligned) */}
                      <td
                        className="tx-amount num"
                        style={{
                          whiteSpace: "nowrap",
                          fontVariantNumeric: "tabular-nums",
                          fontWeight: isLargeAmount ? 700 : 600,
                          fontSize: isLargeAmount ? "0.96rem" : "0.9rem",
                        }}
                      >
                        {isCredit ? "+" : "−"}
                        {formatMoney(tx.amount ?? 0, tx.currency)}
                      </td>

                      {/* Action Column (Only in Needs Review mode) */}
                      {needsReview && (
                        <td onClick={(e) => e.stopPropagation()} style={{ whiteSpace: "nowrap", textAlign: "right" }}>
                          <div style={{ display: "inline-flex", gap: 5, alignItems: "center", justifyContent: "flex-end" }}>
                            {/* 1. View Source Email */}
                            {tx.source_email_id && (
                              <button
                                className="btn quiet icon-btn"
                                type="button"
                                title="View source email"
                                aria-label="View source email"
                                style={{
                                  width: 28,
                                  height: 28,
                                  padding: 0,
                                  display: "inline-flex",
                                  alignItems: "center",
                                  justifyContent: "center",
                                  borderRadius: "var(--radius-sm)",
                                  border: "1px solid var(--line)",
                                }}
                                onClick={() => void openEmail(tx)}
                              >
                                <svg className="gmail-icon" viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">
                                  <path
                                    fill="currentColor"
                                    d="M20 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4-8 5L4 8V6l8 5 8-5v2z"
                                  />
                                </svg>
                              </button>
                            )}

                            {/* 2. Classify (with tag icon) */}
                            <button
                              className="btn primary"
                              type="button"
                              title={`Classify ${merchant}`}
                              aria-label={`Classify ${merchant}`}
                              style={{
                                height: 28,
                                minHeight: 28,
                                fontSize: "0.78rem",
                                padding: "0 8px",
                                display: "inline-flex",
                                alignItems: "center",
                                gap: 5,
                              }}
                              onClick={() => openClassify([tx])}
                            >
                              <svg
                                viewBox="0 0 24 24"
                                width="12"
                                height="12"
                                fill="none"
                                stroke="currentColor"
                                strokeWidth="2.2"
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                aria-hidden="true"
                              >
                                <path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z" />
                                <line x1="7" y1="7" x2="7.01" y2="7" />
                              </svg>
                              <span>Classify</span>
                            </button>

                            {/* 3. Flag Data Issue */}
                            <button
                              className="btn quiet icon-btn"
                              type="button"
                              title={`Flag data issue for ${merchant}`}
                              aria-label={`Flag data issue for ${merchant}`}
                              style={{
                                width: 28,
                                height: 28,
                                padding: 0,
                                display: "inline-flex",
                                alignItems: "center",
                                justifyContent: "center",
                                borderRadius: "var(--radius-sm)",
                                border: "1px solid var(--line)",
                                color: "var(--ink-muted)",
                              }}
                              onClick={() => openFlag([tx])}
                            >
                              <svg
                                viewBox="0 0 24 24"
                                width="13"
                                height="13"
                                fill="none"
                                stroke="currentColor"
                                strokeWidth="2"
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                aria-hidden="true"
                              >
                                <path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z" />
                                <line x1="4" y1="22" x2="4" y2="15" />
                              </svg>
                            </button>
                          </div>
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Mobile Card Layout (< 768px) */}
          <div className="tx-cards-mobile" role="feed" aria-label="Transactions list">
            {items.map((tx) => {
              const selected = selectedIds.has(tx.id);
              const isCredit = tx.direction === "credit";
              const merchant = merchantLabel(tx) ?? "Unidentified merchant";

              return (
                <article
                  key={tx.id}
                  className={`tx-card ${isCredit ? "credit" : "debit"} ${needsReview ? "selectable" : ""} ${needsReview && selected ? "tx-selected" : ""}`}
                  onClick={() => handleRowClick(tx)}
                  style={{ cursor: "pointer" }}
                >
                  <div className="tx-card-header">
                    <div className="tx-card-title-group">
                      {needsReview && (
                        <div onClick={(e) => e.stopPropagation()}>
                          <input
                            type="checkbox"
                            checked={selected}
                            onChange={() => toggleOne(tx.id)}
                            aria-label={`Select ${merchant}`}
                            style={{ width: 18, height: 18 }}
                          />
                        </div>
                      )}
                      <div>
                        <div className="tx-card-merchant" style={{ fontWeight: 600, fontSize: "0.95rem" }}>
                          {merchant}
                        </div>
                        <div className="tx-card-date" style={{ fontSize: "0.78rem", color: "var(--ink-muted)", marginTop: 2 }}>
                          {formatDate(tx.transaction_date)}
                        </div>
                      </div>
                    </div>

                    <div className={`tx-card-amount ${isCredit ? "credit" : "debit"}`} style={{ fontWeight: 700 }}>
                      {isCredit ? "+" : "−"}
                      {formatMoney(tx.amount ?? 0, tx.currency)}
                    </div>
                  </div>

                  <div className="tx-card-body" style={{ marginTop: 6, display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
                    <div className="tx-card-meta" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 6 }}>
                      <span
                        className="tx-card-tag"
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: 5,
                          background: "var(--bg)",
                          border: "1px solid var(--line)",
                          borderRadius: "var(--radius-sm)",
                          padding: "2px 6px 2px 7px",
                          fontWeight: 500,
                          fontSize: "0.78rem",
                          color: "var(--ink)",
                        }}
                      >
                        {tx.category ? (
                          <>
                            <span style={{ fontSize: "0.88rem", lineHeight: 1 }} aria-hidden="true">
                              {getCategoryIcon(tx.category)}
                            </span>
                            <span>{tx.category}</span>
                          </>
                        ) : (
                          <span style={{ color: "var(--ink-muted)" }}>Uncategorized</span>
                        )}
                        {tx.subcategory && (
                          <span style={{ color: "var(--ink-muted)", fontWeight: 400 }}>· {tx.subcategory}</span>
                        )}
                        {!needsReview && (
                          <button
                            type="button"
                            className="btn quiet icon-btn"
                            style={{
                              width: 22,
                              height: 22,
                              padding: 0,
                              display: "inline-flex",
                              alignItems: "center",
                              justifyContent: "center",
                              border: "none",
                              background: "transparent",
                              color: "var(--ink-muted)",
                              cursor: "pointer",
                            }}
                            title={`Modify classification for ${merchant}`}
                            aria-label={`Modify classification for ${merchant}`}
                            onClick={(e) => {
                              e.stopPropagation();
                              openClassify([tx]);
                            }}
                          >
                            <svg viewBox="0 0 24 24" width="12" height="12" aria-hidden="true" focusable="false">
                              <path
                                fill="none"
                                stroke="currentColor"
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth="2"
                                d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"
                              />
                            </svg>
                          </button>
                        )}
                      </span>

                      {tx.account && (
                        <AccountBadge accountName={tx.account} logoSize={16} showIdentifiers={false} />
                      )}
                    </div>

                    {needsReview && (
                      <div style={{ display: "flex", gap: 5, alignItems: "center" }} onClick={(e) => e.stopPropagation()}>
                        {/* 1. View Source Email */}
                        {tx.source_email_id && (
                          <button
                            className="btn quiet icon-btn"
                            type="button"
                            title="View source email"
                            aria-label="View source email"
                            style={{
                              width: 30,
                              height: 30,
                              padding: 0,
                              display: "inline-flex",
                              alignItems: "center",
                              justifyContent: "center",
                              border: "1px solid var(--line)",
                              borderRadius: "var(--radius-sm)",
                            }}
                            onClick={() => void openEmail(tx)}
                          >
                            <svg className="gmail-icon" viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">
                              <path
                                fill="currentColor"
                                d="M20 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4-8 5L4 8V6l8 5 8-5v2z"
                              />
                            </svg>
                          </button>
                        )}

                        {/* 2. Classify (with tag icon) */}
                        <button
                          className="btn primary"
                          type="button"
                          title={`Classify ${merchant}`}
                          aria-label={`Classify ${merchant}`}
                          style={{
                            height: 30,
                            minHeight: 30,
                            fontSize: "0.78rem",
                            padding: "0 9px",
                            display: "inline-flex",
                            alignItems: "center",
                            gap: 5,
                          }}
                          onClick={() => openClassify([tx])}
                        >
                          <svg
                            viewBox="0 0 24 24"
                            width="12"
                            height="12"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2.2"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            aria-hidden="true"
                          >
                            <path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z" />
                            <line x1="7" y1="7" x2="7.01" y2="7" />
                          </svg>
                          <span>Classify</span>
                        </button>

                        {/* 3. Flag Data Issue */}
                        <button
                          className="btn quiet icon-btn"
                          type="button"
                          title={`Flag data issue for ${merchant}`}
                          aria-label={`Flag data issue for ${merchant}`}
                          style={{
                            width: 30,
                            height: 30,
                            padding: 0,
                            display: "inline-flex",
                            alignItems: "center",
                            justifyContent: "center",
                            border: "1px solid var(--line)",
                            borderRadius: "var(--radius-sm)",
                            color: "var(--ink-muted)",
                          }}
                          onClick={() => openFlag([tx])}
                        >
                          <svg
                            viewBox="0 0 24 24"
                            width="13"
                            height="13"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            aria-hidden="true"
                          >
                            <path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z" />
                            <line x1="4" y1="22" x2="4" y2="15" />
                          </svg>
                        </button>
                      </div>
                    )}
                  </div>
                </article>
              );
            })}
          </div>

          {/* ───────────────────────────────────────────────────────────── */}
          {/* FOOTER & PAGINATION                                           */}
          {/* ───────────────────────────────────────────────────────────── */}
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
            }}
          >
            {/* Left summary */}
            <div style={{ display: "flex", gap: 10, alignItems: "center", minWidth: 0, overflow: "hidden" }}>
              <span style={{ whiteSpace: "nowrap" }}>
                Showing <strong>{offset + 1}–{Math.min(offset + items.length, total)}</strong> of{" "}
                <strong>{total}</strong>
              </span>
              <span style={{ color: "var(--line)" }}>·</span>
              <span style={{ whiteSpace: "nowrap" }}>
                <span style={{ color: "var(--ink-muted)" }}>Outflow </span>
                <strong style={{ color: "var(--ink)" }}>{formatMoney(totalDebit)}</strong>
              </span>
              {totalCredit > 0 && (
                <>
                  <span style={{ color: "var(--line)" }}>·</span>
                  <span style={{ whiteSpace: "nowrap" }}>
                    <span style={{ color: "var(--ink-muted)" }}>Inflow </span>
                    <strong style={{ color: "var(--credit)" }}>+{formatMoney(totalCredit)}</strong>
                  </span>
                </>
              )}
            </div>

            {/* Right pagination & page size controls */}
            <div style={{ display: "flex", gap: 8, alignItems: "center", flexShrink: 0 }}>
              {!needsReview && (
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
                    setOffset(0);
                  }}
                  title="Rows per page"
                  aria-label="Rows per page"
                >
                  <option value={25}>25 / page</option>
                  <option value={50}>50 / page</option>
                  <option value={100}>100 / page</option>
                </select>
              )}

              {total > pageSize && (
                <>
                  <button
                    className="btn"
                    disabled={offset === 0}
                    onClick={() => setOffset((o) => Math.max(0, o - pageSize))}
                    style={{ fontSize: "0.8rem", height: 30, padding: "0 10px", display: "inline-flex", alignItems: "center" }}
                  >
                    ‹ Prev
                  </button>
                  <span style={{ fontSize: "0.8rem", color: "var(--ink-muted)", whiteSpace: "nowrap", padding: "0 2px" }}>
                    {currentPage} / {totalPages}
                  </span>
                  <button
                    className="btn"
                    disabled={offset + pageSize >= total}
                    onClick={() => setOffset((o) => o + pageSize)}
                    style={{ fontSize: "0.8rem", height: 30, padding: "0 10px", display: "inline-flex", alignItems: "center" }}
                  >
                    Next ›
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ───────────────────────────────────────────────────────────── */}
      {/* MODALS                                                        */}
      {/* ───────────────────────────────────────────────────────────── */}

      {/* Transaction Detail Audit Modal */}
      <TransactionDetailModal
        open={detailOpen}
        transaction={detailTx}
        onClose={() => {
          setDetailOpen(false);
          setDetailTx(null);
        }}
        onClassify={(tx) => {
          openClassify([tx]);
        }}
        onViewEmail={(tx) => {
          void openEmail(tx);
        }}
        onMarkRecurring={(tx) => {
          openRecurring(tx);
        }}
        onFlagIssue={(tx) => {
          openFlag([tx]);
        }}
      />

      {/* Classify Panel */}
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

      {/* Email Viewer Modal */}
      <EmailViewerModal
        open={viewerOpen}
        loading={viewerLoading}
        error={viewerError}
        message={viewerMessage}
        transactionId={viewerTransactionId}
        onClose={closeViewer}
      />

      {/* Flag Issue Modal */}
      <FlagIssueModal
        open={flagOpen}
        transactions={flagTargets}
        saving={flagSaving}
        error={flagError}
        onClose={closeFlag}
        onSubmit={(body) => void submitFlag(body)}
      />

      {/* Mark Recurring Modal */}
      <MarkRecurringModal
        open={recurringOpen}
        transaction={recurringTarget}
        onClose={closeRecurring}
        onSuccess={() => {
          closeRecurring();
          void load();
        }}
      />
    </section>
  );
}
