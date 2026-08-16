import { useEffect, useState } from "react";
import { api, type Account, type CreditCardStatement } from "../api";
import { useToast } from "../hooks/useToast";
import { StatementDetailModal } from "../components/StatementDetailModal";
import { UploadStatementModal } from "../components/UploadStatementModal";
import { PasswordProfileModal } from "../components/PasswordProfileModal";
import { DownloadIcon } from "../components/DownloadIcon";

function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return "—";
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
  } catch {
    return dateStr;
  }
}

function formatPeriod(startStr: string | null | undefined, endStr: string | null | undefined): string {
  if (!startStr && !endStr) return "—";
  if (startStr && endStr) {
    return `${formatDate(startStr)} – ${formatDate(endStr)}`;
  }
  return formatDate(startStr || endStr);
}

function getStatusBadge(status: string) {
  switch (status) {
    case "READY_FOR_EXTRACTION":
    case "UNLOCKED":
      return <span className="badge" style={{ background: "rgba(16, 185, 129, 0.15)", color: "var(--success, #10b981)", fontWeight: 600 }}>✓ Ready</span>;
    case "PASSWORD_REQUIRED":
      return <span className="badge" style={{ background: "rgba(245, 158, 11, 0.15)", color: "var(--warning, #f59e0b)", fontWeight: 600 }}>🔒 Locked</span>;
    case "PASSWORD_FAILED":
      return <span className="badge" style={{ background: "rgba(239, 68, 68, 0.15)", color: "var(--danger, #ef4444)", fontWeight: 600 }}>⚠ Review</span>;
    case "INVALID_PDF":
    case "DOWNLOAD_FAILED":
    case "UNLOCK_FAILED":
      return <span className="badge" style={{ background: "rgba(239, 68, 68, 0.15)", color: "var(--danger, #ef4444)", fontWeight: 600 }}>✕ {status.replace("_", " ")}</span>;
    default:
      return <span className="badge">{status}</span>;
  }
}

export default function CreditCardStatementsPage() {
  const [statements, setStatements] = useState<CreditCardStatement[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [discovering, setDiscovering] = useState(false);

  // Filters
  const [selectedAccountId, setSelectedAccountId] = useState<string>("all");
  const [selectedType, setSelectedType] = useState<string>("all");
  const [selectedStatus, setSelectedStatus] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState<string>("");

  // Modals
  const [selectedStatement, setSelectedStatement] = useState<CreditCardStatement | null>(null);
  const [detailModalOpen, setDetailModalOpen] = useState(false);
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [passwordProfileModalOpen, setPasswordProfileModalOpen] = useState(false);
  const [passwordProfileAccount, setPasswordProfileAccount] = useState<Account | null>(null);

  const [sortField, setSortField] = useState<"account" | "period" | "date" | "received">("received");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("desc");

  const { showToast } = useToast();

  const loadData = async () => {
    setLoading(true);
    try {
      const [stmtsRes, accsRes] = await Promise.all([
        api.statements({ limit: 200 }),
        api.accounts(),
      ]);
      setStatements(stmtsRes.statements);
      setAccounts(accsRes.accounts.filter((a) => a.account_type === "CREDIT_CARD" || a.account_type === "BANK" || a.is_liability));
    } catch (err: any) {
      showToast(err.message || "Failed to load statements", "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleSort = (field: "account" | "period" | "date" | "received") => {
    if (sortField === field) {
      setSortDirection((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDirection("desc");
    }
  };

  const handleDiscover = async () => {
    setDiscovering(true);
    try {
      const res = await api.discoverStatements(150);
      showToast(`Discovered ${res.discovered_count} statement(s) from Gmail`, "success");
      await loadData();
    } catch (err: any) {
      showToast(err.message || "Statement discovery failed", "error");
    } finally {
      setDiscovering(false);
    }
  };

  const filteredStatements = statements.filter((s) => {
    if (selectedAccountId !== "all" && s.account_id !== selectedAccountId) {
      return false;
    }
    if (selectedType !== "all") {
      if (selectedType === "CREDIT_CARD" && s.statement_type !== "CREDIT_CARD") return false;
      if (selectedType === "BANK_ACCOUNT" && s.statement_type !== "BANK_ACCOUNT") return false;
    }
    if (selectedStatus !== "all") {
      if (selectedStatus === "READY" && s.status !== "READY_FOR_EXTRACTION" && s.status !== "UNLOCKED") return false;
      if (selectedStatus === "LOCKED" && s.status !== "PASSWORD_REQUIRED" && s.status !== "PASSWORD_FAILED") return false;
      if (selectedStatus === "FAILED" && !s.status.includes("FAILED")) return false;
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const text = `${s.issuer} ${s.account_name || ""} ${s.card_last4 || ""} ${s.original_filename} ${s.statement_type || ""}`.toLowerCase();
      if (!text.includes(q)) return false;
    }
    return true;
  });

  const sortedStatements = [...filteredStatements].sort((a, b) => {
    let cmp = 0;
    if (sortField === "account") {
      const nameA = (a.account_name || a.issuer || "").toLowerCase();
      const nameB = (b.account_name || b.issuer || "").toLowerCase();
      cmp = nameA.localeCompare(nameB);
    } else if (sortField === "received") {
      const recA = a.email_received_at || a.discovered_at || a.created_at || "";
      const recB = b.email_received_at || b.discovered_at || b.created_at || "";
      cmp = recA.localeCompare(recB);
    } else if (sortField === "period") {
      const dateA = a.statement_period_start || a.statement_period_end || "";
      const dateB = b.statement_period_start || b.statement_period_end || "";
      cmp = dateA.localeCompare(dateB);
    } else if (sortField === "date") {
      const dateA = a.statement_date || "";
      const dateB = b.statement_date || "";
      cmp = dateA.localeCompare(dateB);
    }
    return sortDirection === "asc" ? cmp : -cmp;
  });

  const readyCount = statements.filter((s) => s.status === "READY_FOR_EXTRACTION" || s.status === "UNLOCKED").length;
  const lockedCount = statements.filter((s) => s.status === "PASSWORD_REQUIRED" || s.status === "PASSWORD_FAILED").length;

  return (
    <>
      <header className="page-header">
        <div>
          <h1>Statements Vault</h1>
          <p className="lead">Discover, unlock, and manage immutable bank and credit card statement PDFs.</p>
        </div>
        <div className="page-actions" style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
          <button
            type="button"
            className="btn quiet"
            onClick={() => {
              setPasswordProfileAccount(accounts[0] || null);
              setPasswordProfileModalOpen(true);
            }}
          >
            ⚙ Password Profiles
          </button>
          <button
            type="button"
            className="btn quiet"
            onClick={handleDiscover}
            disabled={discovering}
          >
            {discovering ? "Scanning Gmail..." : "Discover from Gmail"}
          </button>
          <button
            type="button"
            className="btn primary"
            onClick={() => setUploadModalOpen(true)}
          >
            Upload Statement
          </button>
        </div>
      </header>

      {/* Summary Stat Cards */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
          gap: 16,
          marginBottom: 24,
        }}
      >
        <div style={{ background: "var(--surface)", border: "1px solid var(--line)", borderRadius: "var(--radius-md)", padding: "16px 20px" }}>
          <div style={{ fontSize: "0.75rem", textTransform: "uppercase", color: "var(--ink-muted)", fontWeight: 600 }}>Total Ingested</div>
          <div style={{ fontSize: "1.6rem", fontWeight: 700, marginTop: 4 }}>{statements.length}</div>
        </div>
        <div style={{ background: "var(--surface)", border: "1px solid var(--line)", borderRadius: "var(--radius-md)", padding: "16px 20px" }}>
          <div style={{ fontSize: "0.75rem", textTransform: "uppercase", color: "var(--ink-muted)", fontWeight: 600 }}>Ready for Extraction</div>
          <div style={{ fontSize: "1.6rem", fontWeight: 700, marginTop: 4, color: "var(--success, #10b981)" }}>{readyCount}</div>
        </div>
        <div style={{ background: "var(--surface)", border: "1px solid var(--line)", borderRadius: "var(--radius-md)", padding: "16px 20px" }}>
          <div style={{ fontSize: "0.75rem", textTransform: "uppercase", color: "var(--ink-muted)", fontWeight: 600 }}>Password Locked</div>
          <div style={{ fontSize: "1.6rem", fontWeight: 700, marginTop: 4, color: lockedCount > 0 ? "var(--warning, #f59e0b)" : "inherit" }}>{lockedCount}</div>
        </div>
      </div>

      {/* Filters & Search Controls */}
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
          marginBottom: 16,
        }}
      >
        <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center", flex: 1 }}>
          <input
            type="text"
            className="input"
            placeholder="Search statements..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{ maxWidth: 240 }}
          />

          <select
            className="input"
            value={selectedType}
            onChange={(e) => setSelectedType(e.target.value)}
            style={{ maxWidth: 180 }}
          >
            <option value="all">All Types</option>
            <option value="CREDIT_CARD">💳 Credit Card</option>
            <option value="BANK_ACCOUNT">🏦 Bank Statement</option>
          </select>

          <select
            className="input"
            value={selectedAccountId}
            onChange={(e) => setSelectedAccountId(e.target.value)}
            style={{ maxWidth: 220 }}
          >
            <option value="all">All Accounts</option>
            {accounts.map((acc) => (
              <option key={acc.id} value={acc.id}>
                {acc.name} {acc.card_last4 ? `(•••• ${acc.card_last4})` : acc.account_number_masked ? `(${acc.account_number_masked})` : ""}
              </option>
            ))}
          </select>

          <select
            className="input"
            value={selectedStatus}
            onChange={(e) => setSelectedStatus(e.target.value)}
            style={{ maxWidth: 180 }}
          >
            <option value="all">All Statuses</option>
            <option value="READY">✓ Ready</option>
            <option value="LOCKED">🔒 Password Locked</option>
            <option value="FAILED">⚠ Failed / Review</option>
          </select>
        </div>
      </div>

      {/* Main Statements Table */}
      <div className="section table-wrap">
        {loading && statements.length === 0 ? (
          <div className="empty" style={{ padding: 40 }}>Loading statements from vault...</div>
        ) : (
          <>
            {/* Desktop Table View */}
            <div className="tx-table-desktop">
              <table>
                <thead>
                  <tr>
                    <th
                      style={{ cursor: "pointer", userSelect: "none" }}
                      onClick={() => handleSort("account")}
                      title="Sort by Account / Card"
                    >
                      <div style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                        <span>Account / Card</span>
                        <span style={{ fontSize: "0.75rem", opacity: sortField === "account" ? 1 : 0.3 }}>
                          {sortField === "account" ? (sortDirection === "asc" ? "▲" : "▼") : "⇅"}
                        </span>
                      </div>
                    </th>
                    <th
                      style={{ cursor: "pointer", userSelect: "none" }}
                      onClick={() => handleSort("period")}
                      title="Sort by Statement Period"
                    >
                      <div style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                        <span>Statement Period</span>
                        <span style={{ fontSize: "0.75rem", opacity: sortField === "period" ? 1 : 0.3 }}>
                          {sortField === "period" ? (sortDirection === "asc" ? "▲" : "▼") : "⇅"}
                        </span>
                      </div>
                    </th>
                    <th
                      style={{ cursor: "pointer", userSelect: "none" }}
                      onClick={() => handleSort("date")}
                      title="Sort by Statement Date"
                    >
                      <div style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                        <span>Statement Date</span>
                        <span style={{ fontSize: "0.75rem", opacity: sortField === "date" ? 1 : 0.3 }}>
                          {sortField === "date" ? (sortDirection === "asc" ? "▲" : "▼") : "⇅"}
                        </span>
                      </div>
                    </th>
                    <th
                      style={{ cursor: "pointer", userSelect: "none" }}
                      onClick={() => handleSort("received")}
                      title="Sort by Date Statement Email Was Received"
                    >
                      <div style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                        <span>Received On</span>
                        <span style={{ fontSize: "0.75rem", opacity: sortField === "received" ? 1 : 0.3 }}>
                          {sortField === "received" ? (sortDirection === "asc" ? "▲" : "▼") : "⇅"}
                        </span>
                      </div>
                    </th>
                    <th>Status</th>
                    <th>Original</th>
                    <th>Unlocked</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedStatements.map((stmt) => (
                    <tr
                      key={stmt.id}
                      style={{ cursor: "pointer" }}
                      onClick={() => {
                        setSelectedStatement(stmt);
                        setDetailModalOpen(true);
                      }}
                    >
                      <td>
                        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                          <span style={{ fontWeight: 600 }}>
                            {stmt.account_name || stmt.issuer}
                          </span>
                          <span
                            className="badge"
                            style={{
                              fontSize: "0.68rem",
                              padding: "2px 6px",
                              background: stmt.statement_type === "BANK_ACCOUNT" ? "rgba(59, 130, 246, 0.12)" : "rgba(139, 92, 246, 0.12)",
                              color: stmt.statement_type === "BANK_ACCOUNT" ? "var(--accent)" : "#8b5cf6",
                              border: "none",
                            }}
                          >
                            {stmt.statement_type === "BANK_ACCOUNT" ? "Bank" : "Card"}
                          </span>
                        </div>
                        <div style={{ fontSize: "0.76rem", color: "var(--ink-muted)", marginTop: 2 }}>
                          {stmt.statement_type === "BANK_ACCOUNT"
                            ? (stmt.card_last4 ? `A/C ending ${stmt.card_last4}` : stmt.original_filename)
                            : (stmt.card_last4 ? `Card ending ${stmt.card_last4}` : stmt.original_filename)}
                        </div>
                      </td>
                      <td style={{ fontSize: "0.88rem" }}>
                        {formatPeriod(stmt.statement_period_start, stmt.statement_period_end)}
                      </td>
                      <td style={{ fontSize: "0.88rem" }}>
                        {formatDate(stmt.statement_date)}
                      </td>
                      <td style={{ fontSize: "0.85rem", color: "var(--ink-muted)" }}>
                        {formatDate(stmt.email_received_at || stmt.discovered_at)}
                      </td>
                      <td>
                        {getStatusBadge(stmt.status)}
                      </td>
                      <td onClick={(e) => e.stopPropagation()}>
                        <a
                          href={api.statementOriginalUrl(stmt.id, false)}
                          target="_blank"
                          rel="noreferrer"
                          className="btn quiet icon-btn"
                          style={{ width: 28, height: 28, padding: 0, display: "inline-flex", alignItems: "center", justifyContent: "center" }}
                          title="Download / View Original PDF"
                          aria-label="Download / View Original PDF"
                        >
                          <DownloadIcon size={14} />
                        </a>
                      </td>
                      <td onClick={(e) => e.stopPropagation()}>
                        {stmt.has_unlocked_file ? (
                          <a
                            href={api.statementUnlockedUrl(stmt.id, false)}
                            target="_blank"
                            rel="noreferrer"
                            className="btn quiet icon-btn"
                            style={{ width: 28, height: 28, padding: 0, display: "inline-flex", alignItems: "center", justifyContent: "center" }}
                            title="Download / View Unlocked PDF"
                            aria-label="Download / View Unlocked PDF"
                          >
                            <DownloadIcon size={14} />
                          </a>
                        ) : (
                          <span style={{ fontSize: "0.78rem", color: "var(--ink-muted)" }}>—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                  {filteredStatements.length === 0 && (
                    <tr>
                      <td colSpan={7} className="empty" style={{ padding: 32 }}>
                        No statements found matching criteria.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            {/* Mobile Card Layout */}
            <div className="tx-cards-mobile" style={{ marginTop: 8 }}>
              {sortedStatements.map((stmt) => (
                <article
                  key={stmt.id}
                  className="tx-card"
                  onClick={() => {
                    setSelectedStatement(stmt);
                    setDetailModalOpen(true);
                  }}
                >
                  <div className="tx-card-header">
                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <span className="tx-card-merchant">{stmt.account_name || stmt.issuer}</span>
                        <span
                          className="badge"
                          style={{
                            fontSize: "0.65rem",
                            padding: "1px 5px",
                            background: stmt.statement_type === "BANK_ACCOUNT" ? "rgba(59, 130, 246, 0.12)" : "rgba(139, 92, 246, 0.12)",
                            color: stmt.statement_type === "BANK_ACCOUNT" ? "var(--accent)" : "#8b5cf6",
                            border: "none",
                          }}
                        >
                          {stmt.statement_type === "BANK_ACCOUNT" ? "Bank" : "Card"}
                        </span>
                      </div>
                      <div style={{ color: "var(--ink-muted)", fontSize: "0.76rem", marginTop: 2 }}>
                        {stmt.statement_type === "BANK_ACCOUNT"
                          ? (stmt.card_last4 ? `A/C ending ${stmt.card_last4}` : stmt.original_filename)
                          : (stmt.card_last4 ? `Card ending ${stmt.card_last4}` : stmt.original_filename)}
                        {stmt.statement_period_start ? ` · ${formatPeriod(stmt.statement_period_start, stmt.statement_period_end)}` : ""}
                      </div>
                    </div>
                    <div>{getStatusBadge(stmt.status)}</div>
                  </div>
                  <div className="tx-card-footer" style={{ borderTop: "1px solid var(--line)", paddingTop: 8, marginTop: 8, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontSize: "0.78rem", color: "var(--ink-muted)" }}>
                      Received: {formatDate(stmt.email_received_at || stmt.discovered_at)}
                    </span>
                    <div className="tx-card-actions" onClick={(e) => e.stopPropagation()} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <a
                        href={api.statementOriginalUrl(stmt.id, false)}
                        target="_blank"
                        rel="noreferrer"
                        className="btn quiet icon-btn"
                        style={{ width: 28, height: 28, padding: 0, display: "inline-flex", alignItems: "center", justifyContent: "center" }}
                        title="Download Original PDF"
                        aria-label="Download Original PDF"
                      >
                        <DownloadIcon size={14} />
                      </a>
                      {stmt.has_unlocked_file && (
                        <a
                          href={api.statementUnlockedUrl(stmt.id, false)}
                          target="_blank"
                          rel="noreferrer"
                          className="btn quiet icon-btn"
                          style={{ width: 28, height: 28, padding: 0, display: "inline-flex", alignItems: "center", justifyContent: "center" }}
                          title="Download Unlocked PDF"
                          aria-label="Download Unlocked PDF"
                        >
                          <DownloadIcon size={14} />
                        </a>
                      )}
                    </div>
                  </div>
                </article>
              ))}
              {filteredStatements.length === 0 && (
                <div className="empty" style={{ padding: 24 }}>No statements found.</div>
              )}
            </div>
          </>
        )}
      </div>

      <StatementDetailModal
        open={detailModalOpen}
        statement={selectedStatement}
        onClose={() => setDetailModalOpen(false)}
        onStatementUpdated={(updated) => {
          setSelectedStatement(updated);
          setStatements((prev) => prev.map((s) => (s.id === updated.id ? updated : s)));
        }}
      />

      <UploadStatementModal
        open={uploadModalOpen}
        accounts={accounts}
        defaultAccountId={selectedAccountId !== "all" ? selectedAccountId : undefined}
        onClose={() => setUploadModalOpen(false)}
        onUploaded={(newStmt) => {
          setStatements((prev) => [newStmt, ...prev]);
        }}
      />

      <PasswordProfileModal
        open={passwordProfileModalOpen}
        account={passwordProfileAccount}
        accounts={accounts}
        onClose={() => setPasswordProfileModalOpen(false)}
        onSaved={() => loadData()}
      />
    </>
  );
}
