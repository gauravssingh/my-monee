import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type ClassificationRuleItem } from "../../api";
import { useToast } from "../../hooks/useToast";
import Badge from "../common/Badge";

export default function ClassificationRulesSettings() {
  const [rules, setRules] = useState<ClassificationRuleItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const { showToast } = useToast();

  const loadRules = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.rules();
      setRules(res.rules || []);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load classification rules";
      showToast(msg, "error");
    } finally {
      setLoading(false);
    }
  }, [showToast]);

  useEffect(() => {
    loadRules();
  }, [loadRules]);

  const toggleRuleActive = async (rule: ClassificationRuleItem) => {
    try {
      await api.updateRule(rule.id, { is_active: !rule.is_active });
      setRules((prev) =>
        prev.map((r) => (r.id === rule.id ? { ...r, is_active: !r.is_active } : r))
      );
      showToast(
        `Rule for "${rule.merchant_normalized || rule.name}" ${!rule.is_active ? "enabled" : "disabled"}`,
        "success"
      );
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to update rule";
      showToast(msg, "error");
    }
  };

  const handleDeleteRule = async (rule: ClassificationRuleItem) => {
    if (!window.confirm(`Delete rule for "${rule.merchant_normalized || rule.name || 'this merchant'}"?`)) {
      return;
    }
    try {
      await api.deleteRule(rule.id);
      setRules((prev) => prev.filter((r) => r.id !== rule.id));
      showToast("Classification rule deleted", "success");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to delete rule";
      showToast(msg, "error");
    }
  };

  const filteredRules = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return rules;
    return rules.filter(
      (r) =>
        (r.merchant_normalized && r.merchant_normalized.toLowerCase().includes(q)) ||
        (r.name && r.name.toLowerCase().includes(q)) ||
        r.category_name.toLowerCase().includes(q) ||
        (r.subcategory_name && r.subcategory_name.toLowerCase().includes(q))
    );
  }, [rules, search]);

  const activeCount = rules.filter((r) => r.is_active).length;
  const totalHits = rules.reduce((sum, r) => sum + (r.hit_count || 0), 0);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {/* Metrics Row */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 16 }}>
        <div style={{ background: "var(--surface)", border: "1px solid var(--line)", borderRadius: "var(--radius-md)", padding: "16px 20px" }}>
          <div style={{ fontSize: "0.78rem", color: "var(--ink-muted)", textTransform: "uppercase", letterSpacing: "0.04em", fontWeight: 600 }}>
            Total Rules
          </div>
          <div style={{ fontSize: "1.6rem", fontWeight: 700, marginTop: 4 }}>{rules.length}</div>
        </div>
        <div style={{ background: "var(--surface)", border: "1px solid var(--line)", borderRadius: "var(--radius-md)", padding: "16px 20px" }}>
          <div style={{ fontSize: "0.78rem", color: "var(--ink-muted)", textTransform: "uppercase", letterSpacing: "0.04em", fontWeight: 600 }}>
            Active Rules
          </div>
          <div style={{ fontSize: "1.6rem", fontWeight: 700, marginTop: 4, color: "var(--success)" }}>{activeCount}</div>
        </div>
        <div style={{ background: "var(--surface)", border: "1px solid var(--line)", borderRadius: "var(--radius-md)", padding: "16px 20px" }}>
          <div style={{ fontSize: "0.78rem", color: "var(--ink-muted)", textTransform: "uppercase", letterSpacing: "0.04em", fontWeight: 600 }}>
            Auto-Classifications
          </div>
          <div style={{ fontSize: "1.6rem", fontWeight: 700, marginTop: 4, color: "var(--primary)" }}>{totalHits}</div>
        </div>
      </div>

      {/* Rules Card */}
      <div style={{ background: "var(--surface)", border: "1px solid var(--line)", borderRadius: "var(--radius-md)", overflow: "hidden" }}>
        <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--line)", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
          <div>
            <h3 style={{ margin: 0, fontSize: "1.05rem", fontWeight: 600 }}>Learned Merchant Rules</h3>
            <p style={{ margin: "4px 0 0", fontSize: "0.84rem", color: "var(--ink-muted)" }}>
              Deterministic merchant-to-category rules established from manual classifications.
            </p>
          </div>
          <div>
            <input
              type="text"
              placeholder="Search rules…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{
                background: "var(--surface-muted)",
                border: "1px solid var(--line)",
                borderRadius: "var(--radius-sm)",
                padding: "7px 12px",
                fontSize: "0.85rem",
                width: 220,
              }}
            />
          </div>
        </div>

        {loading ? (
          <div style={{ padding: "40px", textAlign: "center", color: "var(--ink-muted)" }}>Loading rules…</div>
        ) : filteredRules.length === 0 ? (
          <div style={{ padding: "40px", textAlign: "center", color: "var(--ink-muted)" }}>
            {search ? "No classification rules matching your search." : "No classification rules recorded yet. Categorizing transactions in Needs Review will automatically establish rules."}
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.88rem", textAlign: "left" }}>
              <thead>
                <tr style={{ background: "var(--surface-muted)", borderBottom: "1px solid var(--line)", color: "var(--ink-muted)", fontSize: "0.78rem", textTransform: "uppercase" }}>
                  <th style={{ padding: "12px 16px" }}>Merchant Match</th>
                  <th style={{ padding: "12px 16px" }}>Assigned Category</th>
                  <th style={{ padding: "12px 16px" }}>Auto-Applied</th>
                  <th style={{ padding: "12px 16px" }}>Status</th>
                  <th style={{ padding: "12px 16px", textAlign: "right" }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredRules.map((rule) => (
                  <tr key={rule.id} style={{ borderBottom: "1px solid var(--line)", opacity: rule.is_active ? 1 : 0.6 }}>
                    <td style={{ padding: "12px 16px", fontWeight: 600 }}>
                      {rule.merchant_normalized || rule.name || "Any Match"}
                      {rule.upi_id && (
                        <div style={{ fontSize: "0.75rem", color: "var(--ink-muted)", fontWeight: 400, marginTop: 2 }}>
                          UPI: {rule.upi_id}
                        </div>
                      )}
                    </td>
                    <td style={{ padding: "12px 16px" }}>
                      <span style={{ fontWeight: 500 }}>{rule.category_name}</span>
                      {rule.subcategory_name && (
                        <span style={{ color: "var(--ink-muted)", fontSize: "0.8rem", marginLeft: 6 }}>
                          / {rule.subcategory_name}
                        </span>
                      )}
                    </td>
                    <td style={{ padding: "12px 16px" }}>
                      <Badge variant="neutral">{rule.hit_count} hits</Badge>
                    </td>
                    <td style={{ padding: "12px 16px" }}>
                      <button
                        type="button"
                        onClick={() => toggleRuleActive(rule)}
                        className={`btn small ${rule.is_active ? "primary" : "quiet"}`}
                        style={{ fontSize: "0.75rem", padding: "3px 10px" }}
                      >
                        {rule.is_active ? "Active" : "Disabled"}
                      </button>
                    </td>
                    <td style={{ padding: "12px 16px", textAlign: "right" }}>
                      <button
                        type="button"
                        onClick={() => handleDeleteRule(rule)}
                        className="btn small quiet"
                        style={{ color: "var(--danger)", padding: "3px 8px" }}
                        title="Delete rule"
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
