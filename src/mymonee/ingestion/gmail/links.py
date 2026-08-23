"""Build deep links into Gmail web for stored message/thread ids."""

from __future__ import annotations


def gmail_web_url(
    *,
    thread_id: str | None = None,
    message_id: str | None = None,
    account_index: int = 0,
) -> str | None:
    """
    Open the conversation (preferred) or message in Gmail web.

    Gmail's hash routes use the API thread id / message id hex values, e.g.
    https://mail.google.com/mail/u/0/#all/<threadId>
    """
    target = (thread_id or message_id or "").strip()
    if not target:
        return None
    # #all works across inbox/spam/archive better than #inbox
    return f"https://mail.google.com/mail/u/{account_index}/#all/{target}"
