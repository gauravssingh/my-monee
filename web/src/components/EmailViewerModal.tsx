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
        <header className="email-modal-header">
          <div className="email-modal-heading">
            <h2 id={titleId}>{message?.subject || (loading ? "Loading email…" : "Email")}</h2>
            {message && metaBits.length > 0 && (
              <p className="email-modal-meta">{metaBits.join(" · ")}</p>
            )}
            {transactionId && (
              <button
                type="button"
                className="email-tx-id"
                title="Copy transaction ID"
                onClick={() => void copyTransactionId()}
              >
                <span className="email-tx-id-label">ID</span>
                <code>{transactionId}</code>
                <span className="email-tx-id-action">{copied ? "Copied" : "Copy"}</span>
              </button>
            )}
          </div>
          <div className="email-modal-actions">
            {message?.gmail_url && (
              <a className="btn quiet" href={message.gmail_url} target="_blank" rel="noreferrer">
                Gmail
              </a>
            )}
            <button ref={closeRef} className="btn" type="button" onClick={onClose}>
              Close
            </button>
          </div>
        </header>

        <div className="email-modal-body">
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
