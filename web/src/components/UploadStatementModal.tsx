import { useState, useId, useRef } from "react";
import { createPortal } from "react-dom";
import { api, type Account, type CreditCardStatement } from "../api";
import { useToast } from "../hooks/useToast";
import { useBackdropClose, useModalChrome } from "../hooks/useModalChrome";

export function UploadStatementModal({
  open,
  accounts,
  defaultAccountId,
  onClose,
  onUploaded,
}: {
  open: boolean;
  accounts: Account[];
  defaultAccountId?: string | null;
  onClose: () => void;
  onUploaded?: (stmt: CreditCardStatement) => void;
}) {
  const titleId = useId();
  const closeRef = useRef<HTMLButtonElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { showToast } = useToast();

  const [file, setFile] = useState<File | null>(null);
  const [selectedAccountId, setSelectedAccountId] = useState<string>(defaultAccountId || "");
  const [statementDate, setStatementDate] = useState<string>("");
  const [uploading, setUploading] = useState(false);

  useModalChrome(open, onClose, closeRef);
  const onBackdropClick = useBackdropClose(open, onClose);

  if (!open) return null;

  const creditCardAccounts = accounts.filter((a) => a.account_type === "CREDIT_CARD" || a.is_liability);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) {
      showToast("Please select a PDF statement file to upload", "error");
      return;
    }

    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      if (selectedAccountId) {
        formData.append("account_id", selectedAccountId);
      }
      if (statementDate) {
        formData.append("statement_date", statementDate);
      }

      const stmt = await api.uploadStatement(formData);
      showToast(
        stmt.status === "READY_FOR_EXTRACTION"
          ? "Statement uploaded and unlocked successfully!"
          : "Statement uploaded (Password required)",
        "success"
      );
      if (onUploaded) onUploaded(stmt);
      onClose();
    } catch (err: any) {
      showToast(err.message || "Failed to upload statement", "error");
    } finally {
      setUploading(false);
    }
  };

  return createPortal(
    <div className="modal-backdrop" role="presentation" onClick={onBackdropClick}>
      <form
        className="modal-panel"
        aria-labelledby={titleId}
        onClick={(e) => e.stopPropagation()}
        onSubmit={handleSubmit}
        style={{
          width: "100%",
          maxWidth: 520,
          display: "flex",
          flexDirection: "column",
          maxHeight: "90dvh",
          boxSizing: "border-box",
        }}
      >
        <div className="sheet-handle" onClick={onClose} aria-label="Dismiss sheet" />

        <header className="modal-header" style={{ flexShrink: 0, borderBottom: "1px solid var(--line)", paddingBottom: 16 }}>
          <div>
            <h2 id={titleId} style={{ margin: 0, fontSize: "1.2rem" }}>
              Upload Statement (Bank / Card)
            </h2>
            <p className="lead" style={{ margin: "4px 0 0", fontSize: "0.85rem", color: "var(--ink-muted)" }}>
              Add a PDF statement to your secure local Statement Vault.
            </p>
          </div>
          <div className="modal-actions">
            <button ref={closeRef} type="button" className="btn icon-btn" onClick={onClose} aria-label="Close modal">
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
            </button>
          </div>
        </header>

        <div className="modal-body" style={{ display: "flex", flexDirection: "column", gap: 16, flex: "1 1 0%", minHeight: 0, overflowY: "auto", padding: "20px 24px" }}>
          <div className="field">
            <label className="label">Credit Card Account</label>
            <select
              className="input"
              value={selectedAccountId}
              onChange={(e) => setSelectedAccountId(e.target.value)}
            >
              <option value="">Auto-detect / Unlinked</option>
              {creditCardAccounts.map((acc) => (
                <option key={acc.id} value={acc.id}>
                  {acc.name} {acc.card_last4 ? `(•••• ${acc.card_last4})` : ""}
                </option>
              ))}
            </select>
          </div>

          <div className="field">
            <label className="label">PDF Statement File <span style={{ color: "var(--accent)" }}>*</span></label>
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,application/pdf"
              style={{ display: "none" }}
              onChange={(e) => {
                const selected = e.target.files?.[0];
                if (selected) setFile(selected);
              }}
            />
            <div
              onClick={() => fileInputRef.current?.click()}
              style={{
                border: "2px dashed var(--line)",
                borderRadius: "var(--radius-md)",
                padding: "24px 16px",
                textAlign: "center",
                cursor: "pointer",
                background: file ? "rgba(16, 185, 129, 0.04)" : "var(--surface)",
                borderColor: file ? "var(--success, #10b981)" : "var(--line)",
                transition: "all 0.15s ease",
              }}
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ margin: "0 auto 8px", color: file ? "var(--success, #10b981)" : "var(--ink-muted)" }}><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/><path d="M12 18v-6"/><path d="m9 15 3-3 3 3"/></svg>
              <div style={{ fontWeight: 600, fontSize: "0.9rem" }}>
                {file ? file.name : "Click to select a PDF statement"}
              </div>
              <div style={{ fontSize: "0.78rem", color: "var(--ink-muted)", marginTop: 4 }}>
                {file ? `${(file.size / 1024).toFixed(1)} KB` : "Supports encrypted & unencrypted statements"}
              </div>
            </div>
          </div>

          <div className="field">
            <label className="label">Statement Date (Optional)</label>
            <input
              type="date"
              className="input"
              value={statementDate}
              onChange={(e) => setStatementDate(e.target.value)}
            />
          </div>
        </div>

        <footer className="modal-footer" style={{ flexShrink: 0, padding: "12px 24px", borderTop: "1px solid var(--line)" }}>
          <button type="button" className="btn quiet" onClick={onClose} disabled={uploading}>
            Cancel
          </button>
          <button type="submit" className="btn primary" disabled={uploading || !file}>
            {uploading ? "Processing & Vaulting..." : "Upload & Vault"}
          </button>
        </footer>
      </form>
    </div>,
    document.body
  );
}
