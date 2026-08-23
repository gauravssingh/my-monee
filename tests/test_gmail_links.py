from mymonee.ingestion.gmail.links import gmail_web_url


def test_gmail_web_url_prefers_thread() -> None:
    url = gmail_web_url(thread_id="thread123", message_id="msg456")
    assert url == "https://mail.google.com/mail/u/0/#all/thread123"


def test_gmail_web_url_falls_back_to_message() -> None:
    url = gmail_web_url(message_id="msg456")
    assert url == "https://mail.google.com/mail/u/0/#all/msg456"


def test_gmail_web_url_empty() -> None:
    assert gmail_web_url() is None
