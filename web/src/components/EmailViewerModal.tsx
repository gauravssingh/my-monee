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
        <header className="modal-header">
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
              <h2 id={titleId}>
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
            <p className="lead" style={{ margin: "4px 0 0" }}>
              {message && metaBits.length > 0 ? metaBits.join(" · ") : "Email details"}
            </p>
          </div>
          <div className="modal-actions">
            {message?.gmail_url && (
              <a className="btn quiet" href={message.gmail_url} target="_blank" rel="noreferrer">
                Open in Gmail ↗
              </a>
            )}
            <button ref={closeRef} type="button" className="btn icon-btn" onClick={onClose} aria-label="Close modal">
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
            </button>
          </div>
        </header>

        <div className="modal-body email-modal-body">
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
