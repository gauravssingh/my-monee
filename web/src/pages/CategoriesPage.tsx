import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type CategoryTree } from "../api";
import { useConfirm } from "../hooks/useConfirm";
import { useToast } from "../hooks/useToast";

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
        padding: "2px 8px",
        borderRadius: 4,
        background: armed ? "var(--debit-soft, #fef2f2)" : "var(--surface, #f8fafc)",
        border: `1px solid ${armed ? "var(--danger, #ef4444)" : "var(--line, #e2e8f0)"}`,
        fontSize: "0.8125rem",
        color: armed ? "var(--danger, #ef4444)" : "var(--ink, #1e293b)",
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

export default function CategoriesPage() {
  const [categories, setCategories] = useState<CategoryTree[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [newCategory, setNewCategory] = useState("");
  const [filterQuery, setFilterQuery] = useState("");
  const [selectedType, setSelectedType] = useState("all");
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

  async function addCategory() {
    const name = newCategory.trim();
    if (!name) return;
    setBusy("cat");
    try {
      await api.createCategory(name);
      setNewCategory("");
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
    <section className="panel section" style={{ display: "flex", flexDirection: "column", height: "100%", maxHeight: "calc(100vh - 180px)" }}>
      <div style={{ marginBottom: 16 }}>
        <h2 style={{ margin: "0 0 4px" }}>Categories &amp; Hierarchy</h2>
        <p className="lead" style={{ margin: 0, fontSize: "0.875rem" }}>
          Master taxonomy used for classification and spending insights ({categories.length} master categories).
        </p>
      </div>

      {/* Add Category and Search Toolbars */}
      <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 16 }}>
        <div style={{ display: "flex", gap: 8 }}>
          <input
            className="input"
            style={{ flex: 1 }}
            placeholder="Add new master category…"
            value={newCategory}
            onChange={(e) => setNewCategory(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && void addCategory()}
          />
          <button
            className="btn primary"
            type="button"
            disabled={busy !== null || !newCategory.trim()}
            onClick={() => void addCategory()}
            style={{ whiteSpace: "nowrap" }}
          >
            {busy === "cat" ? "Adding…" : "Add Category"}
          </button>
        </div>

        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <input
            className="input"
            style={{ flex: 1, fontSize: "0.875rem", padding: "6px 10px" }}
            placeholder="Filter categories or subcategories…"
            value={filterQuery}
            onChange={(e) => setFilterQuery(e.target.value)}
          />
          <div className="segmented" style={{ flexShrink: 0 }}>
            {EXPENSE_TYPES.map((t) => (
              <button
                key={t.value}
                type="button"
                className={`segmented-btn${selectedType === t.value ? " active" : ""}`}
                onClick={() => setSelectedType(t.value)}
                style={{ fontSize: "0.75rem", padding: "4px 8px" }}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Categories List */}
      <div
        style={{
          flex: 1,
          overflowY: "auto",
          display: "flex",
          flexDirection: "column",
          gap: 12,
          paddingRight: 4,
          minHeight: 0,
        }}
      >
        {filteredCategories.length === 0 && (
          <div style={{ padding: 24, textAlign: "center", color: "var(--ink-muted)", fontSize: "0.875rem" }}>
            No categories match your filter.
          </div>
        )}

        {filteredCategories.map((cat) => (
          <div
            key={cat.id}
            style={{
              padding: "12px 14px",
              borderRadius: 8,
              border: "1px solid var(--line, #e2e8f0)",
              background: "var(--surface, #ffffff)",
              display: "flex",
              flexDirection: "column",
              gap: 8,
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <strong style={{ fontSize: "0.9375rem", color: "var(--ink)" }}>{cat.name}</strong>
                <select
                  style={{
                    padding: "2px 6px",
                    fontSize: "0.75rem",
                    borderRadius: 4,
                    border: "1px solid var(--line)",
                    background: "var(--bg)",
                    color: "var(--ink-muted)",
                    cursor: "pointer",
                  }}
                  value={cat.expense_type || "discretionary"}
                  onChange={(e) => void updateExpenseType(cat.id, e.target.value)}
                  disabled={busy !== null}
                >
                  <option value="essential">Essential</option>
                  <option value="discretionary">Discretionary</option>
                  <option value="financial">Financial</option>
                  <option value="investment">Investment</option>
                  <option value="transfer">Transfer</option>
                </select>
                <span style={{ fontSize: "0.75rem", color: "var(--ink-muted)" }}>
                  {cat.transaction_count} txs {cat.is_system ? "· system" : ""}
                </span>
              </div>
              {!cat.is_system && (
                <CategoryDeleteButton
                  disabled={busy !== null}
                  onConfirm={() => void removeCategory(cat.id)}
                />
              )}
            </div>

            {/* Subcategories */}
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
              {cat.subcategories.map((sub) => (
                <SubCategoryChip
                  key={sub.id}
                  name={sub.name}
                  disabled={busy !== null}
                  onConfirm={() => void removeSubcategory(sub.id)}
                />
              ))}
              {cat.subcategories.length === 0 && (
                <span style={{ fontSize: "0.75rem", color: "var(--ink-muted)", fontStyle: "italic" }}>
                  No subcategories
                </span>
              )}
            </div>

            {/* Inline Add Subcategory */}
            <div style={{ display: "flex", gap: 6, marginTop: 4 }}>
              <input
                className="input"
                style={{ flex: 1, fontSize: "0.8125rem", padding: "4px 8px" }}
                placeholder={`Add subcategory to ${cat.name}…`}
                value={subdrafts[cat.id] || ""}
                onChange={(e) => setSubdrafts((prev) => ({ ...prev, [cat.id]: e.target.value }))}
                onKeyDown={(e) => e.key === "Enter" && void addSubcategory(cat.id)}
              />
              <button
                className="btn"
                type="button"
                style={{ padding: "4px 10px", fontSize: "0.8125rem", height: "auto" }}
                disabled={busy !== null || !(subdrafts[cat.id] || "").trim()}
                onClick={() => void addSubcategory(cat.id)}
              >
                {busy === `sub-${cat.id}` ? "…" : "Add"}
              </button>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
