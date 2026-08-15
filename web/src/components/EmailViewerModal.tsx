import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { GmailMessageView } from "../api";
import { formatDate } from "../format";
import { useBackdropClose, useModalChrome } from "../hooks/useModalChrome";

type Props = {
  open: boolean;
  loading: boolean;
  error: string | null;
  message: GmailMessageView | null;
  transactionId?: string | null;
  onClose: () => void;
};

export default function EmailViewerModal({
  open,
  loading,
  error,
  message,
  transactionId,
  onClose,
}: Props) {
  const titleId = useId();
  const closeRef = useRef<HTMLButtonElement>(null);
  const [copied, setCopied] = useState(false);

  useModalChrome(open, onClose, closeRef);
  const onBackdropClick = useBackdropClose(open, onClose);

  useEffect(() => {
    if (open) setCopied(false);
  }, [open, message?.id, transactionId]);

  if (!open) return null;

  const htmlDoc = message?.body_html
    ? `<!DOCTYPE html><html><head><meta charset="utf-8" />
       <base target="_blank" rel="noopener noreferrer" />
       <style>
         body { font-family: "Source Sans 3", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
                color: #15202b; margin: 18px 20px; line-height: 1.5; word-break: break-word;
                font-size: 15px; }
         img { max-width: 100%; height: auto; }
         a { color: #0c6e5c; }
       </style></head><body>${message.body_html}</body></html>`
    : null;

  async function copyTransactionId() {
    if (!transactionId) return;
    try {
      await navigator.clipboard.writeText(transactionId);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1100);
    } catch {
      window.prompt("Copy transaction ID", transactionId);
    }
  }

  const metaBits = [
    message?.sender || null,
    message?.received_at ? formatDate(message.received_at) : null,
  ].filter(Boolean);

  return createPortal(
    <div className="modal-backdrop" role="presentation" onClick={onBackdropClick}>
      <div
        className="modal-panel email-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onClick={(e) => e.stopPropagation()}
      >
        <header className="modal-header" style={{ padding: "24px 32px", borderBottom: "1px solid var(--line)", alignItems: "flex-start" }}>
          <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
            <div style={{ width: 44, height: 44, borderRadius: "50%", background: "var(--accent-soft)", color: "var(--accent)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
              <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>
            </div>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <h2 id={titleId} style={{ margin: 0, fontSize: "1.25rem", fontWeight: 700, color: "var(--ink)" }}>
                  {message?.subject || (loading ? "Loading email…" : "Email")}
                </h2>
                {transactionId && (
                  <button
                    type="button"
                    className="email-tx-id"
                    title="Copy transaction ID"
                    onClick={() => void copyTransactionId()}
                    style={{ margin: 0 }}
                  >
                    <span className="email-tx-id-label">ID</span>
                    <code>{transactionId}</code>
                    <span className="email-tx-id-action">{copied ? "Copied" : "Copy"}</span>
                  </button>
                )}
              </div>
              <p style={{ margin: "4px 0 0 0", color: "var(--ink-muted)", fontSize: "0.875rem" }}>
                {message && metaBits.length > 0 ? metaBits.join(" · ") : "Email details"}
              </p>
            </div>
          </div>
          <div className="modal-actions" style={{ alignSelf: "flex-start", marginTop: 4 }}>
            {message?.gmail_url && (
              <a className="btn quiet" href={message.gmail_url} target="_blank" rel="noreferrer" style={{ marginRight: 8 }}>
                Open in Gmail
              </a>
            )}
            <button ref={closeRef} type="button" className="btn icon-btn" onClick={onClose} aria-label="Close modal">
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
            </button>
          </div>
        </header>

        <div className="email-modal-body" style={{ display: "flex", flexDirection: "column", gap: 24, padding: "32px" }}>
          {loading && <p className="email-modal-status">Fetching from Gmail…</p>}
          {error && <p className="error">{error}</p>}
          {!loading && !error && message && (
            htmlDoc ? (
              <iframe
                className="email-frame"
                title="Email contents"
                sandbox=""
                srcDoc={htmlDoc}
              />
            ) : (
              <pre className="email-text">{message.body_text || message.snippet || "No body"}</pre>
            )
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}
