import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api, type Transaction, type GmailMessageView } from "../api";
import { formatMoney, formatDateTime } from "../format";
import { useBackdropClose, useModalChrome } from "../hooks/useModalChrome";

type Props = {
  merchantId: string | null;
  merchantName: string;
  onClose: () => void;
};

export default function MerchantDetailsModal({ merchantId, merchantName, onClose }: Props) {
  const titleId = useId();
  const closeRef = useRef<HTMLButtonElement>(null);
  
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  
  const [selectedTx, setSelectedTx] = useState<Transaction | null>(null);
  const [emailLoading, setEmailLoading] = useState(false);
  const [emailMessage, setEmailMessage] = useState<GmailMessageView | null>(null);

  useModalChrome(!!merchantId, onClose, closeRef);
  const onBackdropClick = useBackdropClose(!!merchantId, onClose);

  useEffect(() => {
    if (!merchantId) {
      setSelectedTx(null);
      setEmailMessage(null);
      return;
    }
    setLoading(true);
    api.transactions({ merchant_id: merchantId })
      .then((res) => setTransactions(res.items))
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [merchantId]);

  useEffect(() => {
    if (!selectedTx || !selectedTx.source_email_id) {
      setEmailMessage(null);
      return;
    }
    setEmailLoading(true);
    api.fetchGmailMessage(selectedTx.source_email_id)
      .then((res) => setEmailMessage(res))
      .catch((err: Error) => setError(err.message))
      .finally(() => setEmailLoading(false));
  }, [selectedTx]);

  if (!merchantId) return null;

  const htmlDoc = emailMessage?.body_html
    ? `<!DOCTYPE html><html><head><meta charset="utf-8" />
       <base target="_blank" rel="noopener noreferrer" />
       <style>
         body { font-family: "Source Sans 3", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
                color: #15202b; margin: 18px 20px; line-height: 1.5; word-break: break-word;
                font-size: 15px; }
         img { max-width: 100%; height: auto; }
         a { color: #0c6e5c; }
       </style></head><body>${emailMessage.body_html}</body></html>`
    : null;

  return createPortal(
    <div
      className="modal-backdrop"
      role="presentation"
      onClick={onBackdropClick}
    >
      <div
        className="modal-panel"
        role="dialog"
        aria-labelledby={titleId}
        aria-modal="true"
        style={{ width: "90%", maxWidth: 800, maxHeight: "90vh", overflowY: "auto" }}
        onClick={(e) => e.stopPropagation()}
      >
        <header className="modal-header" style={{ padding: "24px 32px", borderBottom: "1px solid var(--line)", alignItems: "flex-start" }}>
          <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
            <div style={{ width: 44, height: 44, borderRadius: "50%", background: "var(--accent-soft)", color: "var(--accent)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
              <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="21" x2="9" y2="9"/></svg>
            </div>
            <div>
              <h2 id={titleId} style={{ margin: 0, fontSize: "1.25rem", fontWeight: 700, color: "var(--ink)" }}>{merchantName}</h2>
              <p style={{ margin: "4px 0 0 0", color: "var(--ink-muted)", fontSize: "0.875rem" }}>Transactions and receipts for this merchant.</p>
            </div>
          </div>
          <div className="modal-actions" style={{ alignSelf: "flex-start", marginTop: 4 }}>
            <button ref={closeRef} type="button" className="btn icon-btn" onClick={onClose} aria-label="Close modal">
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
            </button>
          </div>
        </header>
        
        <div className="modal-body" style={{ display: "flex", flexDirection: "column", gap: 24, padding: "32px" }}>
          {error && <div className="error">{error}</div>}
          
          {loading ? (
            <div className="empty">Loading transactions...</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
              <div style={{ maxHeight: selectedTx ? "200px" : "60vh", overflowY: "auto", borderBottom: selectedTx ? "1px solid var(--line)" : "none" }}>
                <table className="table">
                  <thead>
                    <tr>
                      <th style={{ textAlign: "left" }}>Date</th>
                      <th style={{ textAlign: "right" }}>Amount</th>
                      <th style={{ textAlign: "left" }}>Category</th>
                      <th style={{ textAlign: "left" }}>Description</th>
                      <th style={{ textAlign: "left" }}>Source</th>
                    </tr>
                  </thead>
                  <tbody>
                    {transactions.map(t => (
                      <tr 
                        key={t.id} 
                        className={`selectable ${selectedTx?.id === t.id ? "tx-selected" : ""}`}
                        onClick={() => setSelectedTx(t)}
                        style={{ cursor: "pointer" }}
                      >
                        <td>{formatDateTime(t.transaction_date || "")}</td>
                        <td style={{ textAlign: "right", fontWeight: 500 }}>{formatMoney(t.amount || 0, t.currency || "INR")}</td>
                        <td>{t.category || "Uncategorized"}</td>
                        <td style={{ color: "var(--ink-muted)" }}>{t.description || t.merchant_raw}</td>
                        <td>{t.source}</td>
                      </tr>
                    ))}
                    {transactions.length === 0 && (
                      <tr>
                        <td colSpan={5} className="empty">No transactions found.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              
              {selectedTx && (
                <div style={{ display: "flex", flexDirection: "column", gap: 12, flex: 1, minHeight: 400 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <h3 style={{ margin: 0, fontSize: "1.1rem" }}>{emailMessage?.subject || "Receipt"}</h3>
                    <button 
                      className="btn quiet icon-btn" 
                      title="Close Preview" 
                      onClick={() => setSelectedTx(null)}
                      style={{ padding: "6px", display: "flex", alignItems: "center", justifyContent: "center" }}
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 15l-6-6-6 6"/></svg>
                    </button>
                  </div>
                  
                  {emailLoading ? (
                    <div className="empty">Loading receipt...</div>
                  ) : htmlDoc ? (
                    <iframe 
                      srcDoc={htmlDoc} 
                      style={{ width: "100%", height: "400px", border: "1px solid var(--line)", borderRadius: 8, background: "white" }} 
                      title="Receipt preview" 
                    />
                  ) : (
                    <div className="empty">No receipt found for this transaction.</div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>,
    document.body
  );
}
