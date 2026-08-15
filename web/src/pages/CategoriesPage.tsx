import { useCallback, useEffect, useState } from "react";
import { api, type CategoryTree } from "../api";
import { useConfirm } from "../hooks/useConfirm";
import { useToast } from "../hooks/useToast";

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
      <svg viewBox="0 0 24 24" aria-hidden="true" width="16" height="16">
        <path d="M3 6h18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        <path d="M8 6V4h8v2" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        <path d="M19 6l-1 14H6L5 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" fill="none" />
        <path d="M10 11v5M14 11v5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      </svg>
    </button>
  );
}

function SubCategoryChip({ name, disabled, onConfirm }: { name: string; disabled: boolean; onConfirm: () => void }) {
  const { armed, trigger } = useConfirm(onConfirm);
  return (
    <span className="sub-chip">
      {name}
      <button
        type="button"
        className={`sub-chip-x${armed ? " armed" : ""}`}
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
    setBusy("sub");
    try {
      await api.createSubcategory(categoryId, name);
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
    setBusy("type");
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

  return (
    <section className="panel section" style={{ display: "flex", flexDirection: "column" }}>
      <h2>Categories</h2>
      <p className="lead">Master list for auto-classification and review. Tag your master categories by expense type to generate insights.</p>

      <div className="settings-categories" style={{ maxWidth: 800, marginTop: 24 }}>
        <div className="toolbar" style={{ marginBottom: 20 }}>
          <input
            className="input"
            placeholder="New master category"
            value={newCategory}
            onChange={(e) => setNewCategory(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && void addCategory()}
          />
          <button
            className="btn primary"
            type="button"
            disabled={busy !== null || !newCategory.trim()}
            onClick={() => void addCategory()}
          >
            {busy === "cat" ? "Adding…" : "Add category"}
          </button>
        </div>

        <div className="category-admin">
          {categories.map((cat) => (
            <div className="category-admin-item" key={cat.id}>
              <div className="category-admin-head">
                <div>
                  <strong>{cat.name}</strong>
                  <select 
                    style={{ marginLeft: 12, padding: "2px 6px", fontSize: "0.85rem", borderRadius: 4 }}
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
                  <span className="metric-hint" style={{ display: "block", marginTop: 4 }}>
                    {cat.subcategories.length} sub · {cat.transaction_count} txs
                    {cat.is_system ? " · system" : ""}
                  </span>
                </div>
                {!cat.is_system && (
                  <CategoryDeleteButton
                    disabled={busy !== null}
                    onConfirm={() => void removeCategory(cat.id)}
                  />
                )}
              </div>
              <div className="category-admin-subs">
                {cat.subcategories.map((sub) => (
                  <SubCategoryChip
                    key={sub.id}
                    name={sub.name}
                    disabled={busy !== null}
                    onConfirm={() => void removeSubcategory(sub.id)}
                  />
                ))}
              </div>
              <div className="toolbar" style={{ marginTop: 12, marginBottom: 0 }}>
                <input
                  className="input"
                  style={{ padding: "4px 8px", fontSize: "0.9rem" }}
                  placeholder="Add subcategory"
                  value={subdrafts[cat.id] || ""}
                  onChange={(e) =>
                    setSubdrafts((prev) => ({ ...prev, [cat.id]: e.target.value }))
                  }
                  onKeyDown={(e) => e.key === "Enter" && void addSubcategory(cat.id)}
                />
                <button
                  className="btn"
                  type="button"
                  style={{ padding: "4px 12px", fontSize: "0.9rem" }}
                  disabled={busy !== null || !(subdrafts[cat.id] || "").trim()}
                  onClick={() => void addSubcategory(cat.id)}
                >
                  Add
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
