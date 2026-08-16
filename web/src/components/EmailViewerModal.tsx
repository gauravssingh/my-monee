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
        style={{ display: "flex", flexDirection: "column", height: "min(880px, 90vh)" }}
      >
        <div className="sheet-handle" onClick={onClose} aria-label="Dismiss sheet" />

        <header className="modal-header" style={{ position: "sticky", top: 0, zIndex: 10, background: "var(--surface)", padding: "14px 18px 12px" }}>
          <div style={{ minWidth: 0, flex: 1 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
              <h2 id={titleId} style={{ fontSize: "1.1rem", fontWeight: 700, margin: 0, wordBreak: "break-word" }}>
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
                  <code>{transactionId.slice(0, 8)}…</code>
                  <span className="email-tx-id-action">{copied ? "Copied" : "Copy"}</span>
                </button>
              )}
            </div>
            <p className="lead" style={{ margin: "3px 0 0", fontSize: "0.82rem", color: "var(--ink-muted)" }}>
              {message && metaBits.length > 0 ? metaBits.join(" · ") : "Email details"}
            </p>
          </div>
          <div className="modal-actions" style={{ marginLeft: 8, flexShrink: 0 }}>
            <button ref={closeRef} type="button" className="btn icon-btn" onClick={onClose} aria-label="Close modal">
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
            </button>
          </div>
        </header>

        <div className="modal-body email-modal-body" style={{ flex: 1, padding: 0, overflow: "hidden", display: "flex", flexDirection: "column" }}>
          {loading && <p className="email-modal-status" style={{ padding: 20 }}>Fetching from Gmail…</p>}
          {error && <p className="error" style={{ margin: 16 }}>{error}</p>}
          {!loading && !error && message && (
            htmlDoc ? (
              <iframe
                className="email-frame"
                title="Email contents"
                sandbox=""
                srcDoc={htmlDoc}
                style={{ flex: 1, width: "100%", height: "100%", border: "none" }}
              />
            ) : (
              <pre className="email-text" style={{ flex: 1, margin: 0, padding: 16, overflowY: "auto" }}>
                {message.body_text || message.snippet || "No body"}
              </pre>
            )
          )}
        </div>

        <footer
          className="modal-footer"
          style={{
            position: "sticky",
            bottom: 0,
            zIndex: 10,
            background: "var(--surface)",
            borderTop: "1px solid var(--line)",
            padding: "10px 16px calc(10px + var(--sab))",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: 10,
          }}
        >
          {message?.gmail_url ? (
            <a
              className="btn quiet"
              href={message.gmail_url}
              target="_blank"
              rel="noreferrer"
              style={{ fontSize: "0.85rem", padding: "8px 14px" }}
            >
              Open in Gmail ↗
            </a>
          ) : <div />}

          <button
            type="button"
            className="btn primary"
            onClick={onClose}
            style={{ padding: "8px 20px", fontSize: "0.88rem", fontWeight: 600 }}
          >
            Done
          </button>
        </footer>
      </div>
    </div>,
    document.body,
  );
}
