import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type CategoryTree } from "../../api";
import { useConfirm } from "../../hooks/useConfirm";
import { useToast } from "../../hooks/useToast";
import { getCategoryIcon } from "../../utils/categoryIcons";

const EXPENSE_TYPES = [
  { value: "all", label: "All" },
  { value: "essential", label: "Essential" },
  { value: "discretionary", label: "Discretionary" },
  { value: "financial", label: "Financial" },
  { value: "investment", label: "Investment" },
  { value: "transfer", label: "Transfer" },
];

function CategoryDeleteButton({ disabled, onConfirm }: { disabled: boolean; onConfirm: () => void }) {
  const { armed, trigger } = useConfirm(onConfirm);
  return (
    <button
      type="button"
      className={`category-delete-button${armed ? " armed" : ""}`}
      disabled={disabled}
      onClick={trigger}
      aria-label={armed ? "Confirm delete category" : "Delete category"}
      title={armed ? "Click again to confirm deletion" : "Delete category"}
    >
      <svg viewBox="0 0 24 24" aria-hidden="true" width="14" height="14">
        <path d="M3 6h18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        <path d="M8 6V4h8v2" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        <path d="M19 6l-1 14H6L5 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" fill="none" />
        <path d="M10 11v5M14 11v5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      </svg>
    </button>
  );
}

function SubCategoryChip({
  name,
  disabled,
  onConfirm,
}: {
  name: string;
  disabled: boolean;
  onConfirm: () => void;
}) {
  const { armed, trigger } = useConfirm(onConfirm);
  return (
    <span
      className="sub-chip"
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        padding: "3px 8px",
        borderRadius: "var(--radius-sm, 4px)",
        background: armed ? "var(--debit-soft)" : "var(--surface)",
        border: `1px solid ${armed ? "var(--danger)" : "var(--line)"}`,
        fontSize: "0.8125rem",
        color: armed ? "var(--danger)" : "var(--ink)",
      }}
    >
      {name}
      <button
        type="button"
        className="icon-action"
        style={{
          border: "none",
          background: "none",
          cursor: "pointer",
          padding: "0 2px",
          color: "inherit",
          fontSize: "1rem",
          lineHeight: 1,
        }}
        title={armed ? `Click again to remove ${name}` : `Remove ${name}`}
        disabled={disabled}
        onClick={trigger}
      >
        ×
      </button>
    </span>
  );
}

export default function CategorySettings() {
  const [categories, setCategories] = useState<CategoryTree[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [newCategory, setNewCategory] = useState("");
  const [showAddForm, setShowAddForm] = useState(false);
  const [filterQuery, setFilterQuery] = useState("");
  const [selectedType, setSelectedType] = useState("all");
  const [expandedCats, setExpandedCats] = useState<Set<string>>(new Set());
  const [subdrafts, setSubdrafts] = useState<Record<string, string>>({});
  const { showToast } = useToast();

  const refresh = useCallback(async () => {
    try {
      const cats = await api.categories();
      setCategories(cats.items);
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Failed to load categories", "error");
    }
  }, [showToast]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  function toggleExpand(id: string) {
    setExpandedCats((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  function expandAll() {
    setExpandedCats(new Set(categories.map((c) => c.id)));
  }

  function collapseAll() {
    setExpandedCats(new Set());
  }

  async function addCategory() {
    const name = newCategory.trim();
    if (!name) return;
    setBusy("cat");
    try {
      await api.createCategory(name);
      setNewCategory("");
      setShowAddForm(false);
      await refresh();
      showToast(`Category "${name}" created`, "success");
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Failed to create category", "error");
    } finally {
      setBusy(null);
    }
  }

  async function removeCategory(id: string) {
    setBusy(`del-${id}`);
    try {
      await api.deleteCategory(id);
      await refresh();
      showToast("Category deleted", "success");
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Failed to delete category", "error");
    } finally {
      setBusy(null);
    }
  }

  async function addSubcategory(categoryId: string) {
    const name = subdrafts[categoryId];
    if (!name?.trim()) return;
    setBusy(`sub-${categoryId}`);
    try {
      await api.createSubcategory(categoryId, name.trim());
      setSubdrafts((prev) => ({ ...prev, [categoryId]: "" }));
      await refresh();
      showToast(`Subcategory "${name}" added`, "success");
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Failed to add subcategory", "error");
    } finally {
      setBusy(null);
    }
  }

  async function updateExpenseType(categoryId: string, expenseType: string) {
    setBusy(`type-${categoryId}`);
    try {
      await api.updateCategoryExpenseType(categoryId, expenseType);
      await refresh();
      showToast("Expense type updated", "success");
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Failed to update expense type", "error");
    } finally {
      setBusy(null);
    }
  }

  async function removeSubcategory(id: string) {
    setBusy(`del-sub-${id}`);
    try {
      await api.deleteSubcategory(id);
      await refresh();
      showToast("Subcategory removed", "success");
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Failed to delete subcategory", "error");
    } finally {
      setBusy(null);
    }
  }

  const countsByType = useMemo(() => {
    const counts: Record<string, number> = { all: categories.length };
    for (const c of categories) {
      const t = c.expense_type || "discretionary";
      counts[t] = (counts[t] || 0) + 1;
    }
    return counts;
  }, [categories]);

  const filteredCategories = useMemo(() => {
    return categories.filter((cat) => {
      const matchesType =
        selectedType === "all" || (cat.expense_type || "discretionary") === selectedType;
      const q = filterQuery.toLowerCase().trim();
      const matchesQuery =
        !q ||
        cat.name.toLowerCase().includes(q) ||
        cat.subcategories.some((s) => s.name.toLowerCase().includes(q));
      return matchesType && matchesQuery;
    });
  }, [categories, selectedType, filterQuery]);

  return (
    <div className="settings-section-container">
      <div className="settings-section-header">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 12 }}>
          <div>
            <h2>Categories &amp; Hierarchy</h2>
            <p className="lead">
              Manage the master category taxonomy and subcategories used for classification and spending analysis.
            </p>
          </div>
          <button
            className="btn primary"
            type="button"
            onClick={() => setShowAddForm((prev) => !prev)}
            style={{ whiteSpace: "nowrap" }}
          >
            {showAddForm ? "Cancel" : "+ Add Category"}
          </button>
        </div>
      </div>

      {/* Inline Add Category Form */}
      {showAddForm && (
        <div className="settings-card" style={{ animation: "rise 0.2s ease both", marginBottom: 16 }}>
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <input
              className="input"
              style={{ flex: 1, minWidth: 200 }}
              placeholder="Enter category name (e.g. Groceries, Healthcare)…"
              value={newCategory}
              onChange={(e) => setNewCategory(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && void addCategory()}
              autoFocus
            />
            <button
              className="btn primary"
              type="button"
              disabled={busy !== null || !newCategory.trim()}
              onClick={() => void addCategory()}
            >
              {busy === "cat" ? "Creating…" : "Save Category"}
            </button>
            <button
              className="btn quiet"
              type="button"
              onClick={() => {
                setNewCategory("");
                setShowAddForm(false);
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Filter and Search Bar */}
      <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 16 }}>
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <div style={{ position: "relative", flex: 1, minWidth: 220 }}>
            <input
              className="input"
              style={{ width: "100%", paddingLeft: 32, boxSizing: "border-box" }}
              placeholder="Search categories or subcategories…"
              value={filterQuery}
              onChange={(e) => setFilterQuery(e.target.value)}
            />
            <svg
              width="15"
              height="15"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", color: "var(--ink-muted)" }}
            >
              <circle cx="11" cy="11" r="8" />
              <line x1="21" x2="16.65" y1="21" y2="16.65" />
            </svg>
          </div>

          <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <button
              type="button"
              className="btn quiet"
              onClick={expandAll}
              style={{ fontSize: "0.78rem", padding: "4px 8px" }}
            >
              Expand All
            </button>
            <button
              type="button"
              className="btn quiet"
              onClick={collapseAll}
              style={{ fontSize: "0.78rem", padding: "4px 8px" }}
            >
              Collapse All
            </button>
          </div>
        </div>

        {/* Expense Type Filter Pills */}
        <div className="segmented" style={{ overflowX: "auto", display: "flex", WebkitOverflowScrolling: "touch" }}>
          {EXPENSE_TYPES.map((t) => {
            const count = countsByType[t.value] || 0;
            return (
              <button
                key={t.value}
                type="button"
                className={`segmented-btn${selectedType === t.value ? " active" : ""}`}
                onClick={() => setSelectedType(t.value)}
                style={{ fontSize: "0.78rem", padding: "5px 10px", flexShrink: 0, whiteSpace: "nowrap" }}
              >
                {t.label} <span className="metric-hint" style={{ fontSize: "0.72rem", marginLeft: 4 }}>({count})</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Expandable Category Rows List */}
      <div className="category-accordion-list">
        {filteredCategories.length === 0 && (
          <div className="settings-card" style={{ textAlign: "center", padding: "28px 16px", color: "var(--ink-muted)" }}>
            No categories match your search or filter criteria.
          </div>
        )}

        {filteredCategories.map((cat) => {
          const isExpanded = expandedCats.has(cat.id);
          const icon = getCategoryIcon(cat.name, cat.expense_type);
          const subCount = cat.subcategories.length;

          return (
            <div key={cat.id} className={`category-row-card ${isExpanded ? "expanded" : ""}`}>
              {/* Category Main Row */}
              <div className="category-row-main" onClick={() => toggleExpand(cat.id)}>
                <div className="category-row-primary">
                  <div className="category-icon-badge" aria-hidden="true">
                    {icon}
                  </div>
                  <div className="category-row-text">
                    <div className="category-name-line">
                      <strong className="category-title">{cat.name}</strong>
                      {cat.is_system && <span className="system-tag">System</span>}
                    </div>
                    <div className="category-sub-meta">
                      <span className="category-type-pill">{cat.expense_type || "discretionary"}</span>
                      <span>·</span>
                      <span>{cat.transaction_count} transactions</span>
                      <span>·</span>
                      <span>{subCount} {subCount === 1 ? "subcategory" : "subcategories"}</span>
                    </div>
                  </div>
                </div>

                <div className="category-row-actions" onClick={(e) => e.stopPropagation()}>
                  <select
                    className="category-type-select"
                    value={cat.expense_type || "discretionary"}
                    onChange={(e) => void updateExpenseType(cat.id, e.target.value)}
                    disabled={busy !== null}
                    aria-label={`Expense type for ${cat.name}`}
                  >
                    <option value="essential">Essential</option>
                    <option value="discretionary">Discretionary</option>
                    <option value="financial">Financial</option>
                    <option value="investment">Investment</option>
                    <option value="transfer">Transfer</option>
                  </select>

                  {!cat.is_system && (
                    <CategoryDeleteButton
                      disabled={busy !== null}
                      onConfirm={() => void removeCategory(cat.id)}
                    />
                  )}

                  <button
                    type="button"
                    className="category-expand-btn"
                    onClick={() => toggleExpand(cat.id)}
                    aria-label={isExpanded ? `Collapse ${cat.name}` : `Expand ${cat.name}`}
                  >
                    <svg
                      width="16"
                      height="16"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      style={{
                        transform: isExpanded ? "rotate(180deg)" : "rotate(0deg)",
                        transition: "transform 0.2s ease",
                      }}
                    >
                      <polyline points="6 9 12 15 18 9" />
                    </svg>
                  </button>
                </div>
              </div>

              {/* Subcategories Accordion Content */}
              {isExpanded && (
                <div className="category-row-expanded">
                  <div className="subcategory-section">
                    <div className="subcategory-section-label">Subcategories</div>
                    <div className="subcategory-chips-group">
                      {cat.subcategories.map((sub) => (
                        <SubCategoryChip
                          key={sub.id}
                          name={sub.name}
                          disabled={busy !== null}
                          onConfirm={() => void removeSubcategory(sub.id)}
                        />
                      ))}
                      {cat.subcategories.length === 0 && (
                        <span className="metric-hint" style={{ fontStyle: "italic", fontSize: "0.8rem" }}>
                          No subcategories defined for {cat.name}.
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Inline Add Subcategory input */}
                  <div className="subcategory-add-row">
                    <input
                      className="input"
                      style={{ flex: 1, fontSize: "0.82rem", padding: "5px 10px" }}
                      placeholder={`Add subcategory to ${cat.name} (e.g. Cafe, Groceries)…`}
                      value={subdrafts[cat.id] || ""}
                      onChange={(e) => setSubdrafts((prev) => ({ ...prev, [cat.id]: e.target.value }))}
                      onKeyDown={(e) => e.key === "Enter" && void addSubcategory(cat.id)}
                    />
                    <button
                      className="btn"
                      type="button"
                      style={{ padding: "5px 12px", fontSize: "0.82rem" }}
                      disabled={busy !== null || !(subdrafts[cat.id] || "").trim()}
                      onClick={() => void addSubcategory(cat.id)}
                    >
                      {busy === `sub-${cat.id}` ? "Adding…" : "Add"}
                    </button>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
