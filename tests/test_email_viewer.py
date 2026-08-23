from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from mymonee.app import create_app
from mymonee.config import AppConfig, DatabaseConfig, LoggingConfig, Settings
from mymonee.db.models import Email
from mymonee.db.session import get_session_factory


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        app=AppConfig(data_dir=tmp_path),
        database=DatabaseConfig(filename="test.db"),
        logging=LoggingConfig(file=tmp_path / "test.log"),
    )


def test_fetch_message_requires_local_index(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    client = TestClient(app)
    # Not connected / not in index
    missing = client.get("/api/gmail/messages/does-not-exist")
    assert missing.status_code in {400, 404}


def test_fetch_message_404_when_not_indexed_even_if_connected_mocked(
    tmp_path: Path, monkeypatch
) -> None:
    settings = _settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    monkeypatch.setattr(
        "mymonee.api.routes.gmail.is_connected",
        lambda _settings: True,
    )

    response = client.get("/api/gmail/messages/unknown-id")
    assert response.status_code == 404


def test_fetch_message_success_path(tmp_path: Path, monkeypatch) -> None:
    from datetime import datetime, timezone

    from mymonee.ingestion.gmail.client import GmailMessage

    settings = _settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    session = get_session_factory()()
    session.add(
        Email(
            id="msg-1",
            thread_id="thr-1",
            sender="alerts@example.com",
            subject="Txn",
            parse_status="parsed",
        )
    )
    session.commit()
    session.close()

    monkeypatch.setattr(
        "mymonee.api.routes.gmail.is_connected",
        lambda _settings: True,
    )

    class FakeSource:
        def get_message(self, message_id: str) -> GmailMessage:
            assert message_id == "msg-1"
            return GmailMessage(
                id="msg-1",
                thread_id="thr-1",
                sender="alerts@example.com",
                subject="Payment of Rs.100",
                snippet="snippet",
                received_at=datetime(2026, 5, 10, tzinfo=timezone.utc),
                label_ids=["INBOX"],
                headers={},
                body_text="Rs.100 spent at MERCHANT",
                body_html="<p>Rs.100 spent at MERCHANT</p>",
            )

    monkeypatch.setattr(
        "mymonee.api.routes.gmail.GmailApiSource",
        lambda _settings: FakeSource(),
    )

    response = client.get("/api/gmail/messages/msg-1")
    assert response.status_code == 200
    body = response.json()
    assert body["subject"] == "Payment of Rs.100"
    assert body["body_html"] is not None
    assert body["stored_locally"] is False
    assert "mail.google.com" in body["gmail_url"]
