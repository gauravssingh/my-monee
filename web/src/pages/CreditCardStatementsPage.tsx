import { useEffect, useState } from "react";
import { api, type Account, type CreditCardStatement } from "../api";
import { useToast } from "../hooks/useToast";
import { StatementDetailModal } from "../components/StatementDetailModal";
import { UploadStatementModal } from "../components/UploadStatementModal";
import { PasswordProfileModal } from "../components/PasswordProfileModal";
import { DownloadIcon } from "../components/DownloadIcon";
import Badge from "../components/common/Badge";
import PageHeader from "../components/common/PageHeader";
import AccountBadge from "../components/common/AccountBadge";
import { IconCheck, IconAlertTriangle, IconLock, IconSparkles } from "../components/common/Icons";

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

function getStatusBadge(status: string, validationStatus?: string | null) {
  if (status === "VALIDATED" || validationStatus === "VALIDATED") {
    return <Badge variant="credit" icon={<IconCheck size={11} />}>Extracted</Badge>;
  }
  if (status === "REVIEW_REQUIRED" || validationStatus === "REVIEW_REQUIRED") {
    return <Badge variant="warn" icon={<IconAlertTriangle size={11} />}>Needs Review</Badge>;
  }
  switch (status) {
    case "READY_FOR_EXTRACTION":
    case "UNLOCKED":
      return <Badge variant="info" icon={<IconSparkles size={11} />}>Ready to Extract</Badge>;
    case "PASSWORD_REQUIRED":
      return <Badge variant="warn" icon={<IconLock size={11} />}>Needs Unlocking</Badge>;
    case "PASSWORD_FAILED":
      return <Badge variant="danger" icon={<IconAlertTriangle size={11} />}>Password Failed</Badge>;
    case "INVALID_PDF":
    case "DOWNLOAD_FAILED":
    case "UNLOCK_FAILED":
    case "VALIDATION_FAILED":
    case "EXTRACTION_FAILED":
      return <Badge variant="danger">Failed</Badge>;
    default:
      return <Badge variant="neutral">{status}</Badge>;
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

  const [batchExtracting, setBatchExtracting] = useState(false);

  const handleBatchExtract = async () => {
    setBatchExtracting(true);
    try {
      const res = await api.batchExtractStatements(150);
      showToast(
        `Batch Extracted: ${res.total_processed} processed (${res.validated_count} validated, ${res.review_count} review required)`,
        "success"
      );
      await loadData();
    } catch (err: any) {
      showToast(err.message || "Batch statement extraction failed", "error");
    } finally {
      setBatchExtracting(false);
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
      if (selectedStatus === "EXTRACTED") {
        if (s.status !== "VALIDATED" && s.validation_status !== "VALIDATED") return false;
      } else if (selectedStatus === "READY") {
        if (s.status !== "READY_FOR_EXTRACTION" && s.status !== "UNLOCKED") return false;
        if (s.validation_status === "VALIDATED") return false;
      } else if (selectedStatus === "LOCKED") {
        if (s.status !== "PASSWORD_REQUIRED" && s.status !== "PASSWORD_FAILED") return false;
      } else if (selectedStatus === "REVIEW") {
        if (s.status !== "REVIEW_REQUIRED" && s.validation_status !== "VALIDATION_FAILED" && !s.status.includes("FAILED")) return false;
      }
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

  const extractedCount = statements.filter((s) => s.status === "VALIDATED" || s.validation_status === "VALIDATED").length;
  const readyCount = statements.filter((s) => (s.status === "READY_FOR_EXTRACTION" || s.status === "UNLOCKED") && s.validation_status !== "VALIDATED").length;
  const lockedCount = statements.filter((s) => s.status === "PASSWORD_REQUIRED" || s.status === "PASSWORD_FAILED").length;
  const reviewCount = statements.filter((s) => s.status === "REVIEW_REQUIRED" || s.validation_status === "VALIDATION_FAILED" || s.status.includes("FAILED")).length;


  return (
    <>
      <PageHeader
        title="Statements Vault"
        subtitle="Discover, unlock, and manage immutable bank and credit card statement PDFs."
        actions={
          <>
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
            {readyCount > 0 && (
              <button
                type="button"
                className="btn quiet"
                onClick={handleBatchExtract}
                disabled={batchExtracting}
                title="Run deterministic parser and validation on all ready statements"
              >
                {batchExtracting ? "Extracting..." : `⚡ Batch Extract (${readyCount})`}
              </button>
            )}
            <button
              type="button"
              className="btn primary"
              onClick={() => setUploadModalOpen(true)}
            >
              Upload Statement
            </button>
          </>
        }
      />

      {/* Summary Stat Cards (Interactive Clickable Filters) */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
          gap: 14,
          marginBottom: 24,
        }}
      >
        <div
          onClick={() => setSelectedStatus("all")}
          style={{
            background: "var(--surface)",
            border: selectedStatus === "all" ? "2px solid var(--accent)" : "1px solid var(--line)",
            borderRadius: "var(--radius-md)",
            padding: "14px 18px",
            cursor: "pointer",
            transition: "all 0.15s ease",
          }}
          title="Click to view all statements"
        >
          <div style={{ fontSize: "0.72rem", textTransform: "uppercase", color: "var(--ink-muted)", fontWeight: 600 }}>Total Statements</div>
          <div style={{ fontSize: "1.5rem", fontWeight: 700, marginTop: 4 }}>{statements.length}</div>
        </div>

        <div
          onClick={() => setSelectedStatus(selectedStatus === "EXTRACTED" ? "all" : "EXTRACTED")}
          style={{
            background: "var(--surface)",
            border: selectedStatus === "EXTRACTED" ? "2px solid var(--credit)" : "1px solid var(--line)",
            borderRadius: "var(--radius-md)",
            padding: "14px 18px",
            cursor: "pointer",
            transition: "all 0.15s ease",
          }}
          title="Click to filter statements that are successfully extracted & validated"
        >
          <div style={{ fontSize: "0.72rem", textTransform: "uppercase", color: "var(--ink-muted)", fontWeight: 600 }}>Extracted & Validated</div>
          <div style={{ fontSize: "1.5rem", fontWeight: 700, marginTop: 4, color: "var(--credit)" }}>{extractedCount}</div>
        </div>

        <div
          onClick={() => setSelectedStatus(selectedStatus === "READY" ? "all" : "READY")}
          style={{
            background: "var(--surface)",
            border: selectedStatus === "READY" ? "2px solid var(--info)" : "1px solid var(--line)",
            borderRadius: "var(--radius-md)",
            padding: "14px 18px",
            cursor: "pointer",
            transition: "all 0.15s ease",
          }}
          title="Click to filter statements unlocked and ready to extract"
        >
          <div style={{ fontSize: "0.72rem", textTransform: "uppercase", color: "var(--ink-muted)", fontWeight: 600 }}>Ready to Extract</div>
          <div style={{ fontSize: "1.5rem", fontWeight: 700, marginTop: 4, color: readyCount > 0 ? "var(--info)" : "inherit" }}>{readyCount}</div>
        </div>

        <div
          onClick={() => setSelectedStatus(selectedStatus === "LOCKED" ? "all" : "LOCKED")}
          style={{
            background: "var(--surface)",
            border: selectedStatus === "LOCKED" ? "2px solid var(--warn)" : "1px solid var(--line)",
            borderRadius: "var(--radius-md)",
            padding: "14px 18px",
            cursor: "pointer",
            transition: "all 0.15s ease",
          }}
          title="Click to filter statements that require password unlocking"
        >
          <div style={{ fontSize: "0.72rem", textTransform: "uppercase", color: "var(--ink-muted)", fontWeight: 600 }}>Needs Unlocking</div>
          <div style={{ fontSize: "1.5rem", fontWeight: 700, marginTop: 4, color: lockedCount > 0 ? "var(--warn)" : "inherit" }}>{lockedCount}</div>
        </div>

        {reviewCount > 0 && (
          <div
            onClick={() => setSelectedStatus(selectedStatus === "REVIEW" ? "all" : "REVIEW")}
            style={{
              background: "var(--surface)",
              border: selectedStatus === "REVIEW" ? "2px solid var(--danger)" : "1px solid var(--line)",
              borderRadius: "var(--radius-md)",
              padding: "14px 18px",
              cursor: "pointer",
              transition: "all 0.15s ease",
            }}
            title="Click to filter statements needing review or with extraction errors"
          >
            <div style={{ fontSize: "0.72rem", textTransform: "uppercase", color: "var(--ink-muted)", fontWeight: 600 }}>Needs Review / Failed</div>
            <div style={{ fontSize: "1.5rem", fontWeight: 700, marginTop: 4, color: "var(--danger)" }}>{reviewCount}</div>
          </div>
        )}
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
            style={{ maxWidth: 200 }}
          >
            <option value="all">All Statuses</option>
            <option value="EXTRACTED">✓ Extracted & Validated</option>
            <option value="READY">⚡ Ready to Extract</option>
            <option value="LOCKED">🔒 Needs Unlocking</option>
            <option value="REVIEW">⚠ Needs Review / Failed</option>
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
                      title="Sort by Account"
                    >
                      <div style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                        <span>Account</span>
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
                        <AccountBadge
                          accountName={stmt.account_name || stmt.issuer}
                          accountType={stmt.statement_type === "BANK_ACCOUNT" ? "BANK" : "CREDIT_CARD"}
                          cardLast4={stmt.card_last4}
                          logoSize={22}
                        />
                        <div style={{ fontSize: "0.74rem", color: "var(--ink-muted)", marginTop: 2, paddingLeft: 30 }}>
                          {stmt.original_filename}
                        </div>
                      </td>
                      <td style={{ fontSize: "0.9rem", fontWeight: 600 }}>
                        {formatPeriod(stmt.statement_period_start, stmt.statement_period_end)}
                      </td>
                      <td style={{ fontSize: "0.85rem", color: "var(--ink-muted)" }}>
                        {formatDate(stmt.statement_date)}
                      </td>
                      <td style={{ fontSize: "0.85rem", color: "var(--ink-muted)" }}>
                        {formatDate(stmt.email_received_at || stmt.discovered_at)}
                      </td>
                      <td>
                        {getStatusBadge(stmt.status, stmt.validation_status)}
                      </td>
                      <td onClick={(e) => e.stopPropagation()}>
                        <a
                          href={api.statementOriginalUrl(stmt.id, false)}
                          target="_blank"
                          rel="noreferrer"
                          className="btn quiet icon-btn"
                          style={{ width: 28, height: 28, padding: 0, display: "inline-flex", alignItems: "center", justifyContent: "center" }}
                          title="Download original statement as received (Immutable source)"
                          aria-label="Download original statement as received"
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
                            title="Download password-unlocked PDF copy (Used for extraction)"
                            aria-label="Download password-unlocked PDF copy"
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
                      <AccountBadge
                        accountName={stmt.account_name || stmt.issuer}
                        accountType={stmt.statement_type === "BANK_ACCOUNT" ? "BANK" : "CREDIT_CARD"}
                        cardLast4={stmt.card_last4}
                        logoSize={22}
                      />
                      <div style={{ color: "var(--ink-muted)", fontSize: "0.76rem", marginTop: 2, paddingLeft: 30 }}>
                        {stmt.statement_period_start ? formatPeriod(stmt.statement_period_start, stmt.statement_period_end) : stmt.original_filename}
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
