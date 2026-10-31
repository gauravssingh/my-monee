"""OAuth redirect selection: loopback locally, public origin behind a proxy.

Google matches `redirect_uri` literally against the URIs registered on the OAuth
client, and a loopback URI only exists on the machine running the server. These
tests pin the two behaviours that keep both setups working.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from mymonee.app import create_app
from mymonee.config import AppConfig, DatabaseConfig, LoggingConfig, Settings
from mymonee.ingestion.gmail import oauth as oauth_module

PUBLIC_ORIGIN = "https://my-monee.gauravs-apps.in"
PUBLIC_CALLBACK = f"{PUBLIC_ORIGIN}/oauth/callback"
LOOPBACK_CALLBACK = "http://127.0.0.1:8477/oauth/callback"

FAKE_WEB_CLIENT = {
    "web": {
        "client_id": "fake-client-id.apps.googleusercontent.com",
        "client_secret": "fake-client-secret",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": [LOOPBACK_CALLBACK],
    }
}


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    (tmp_path / "gmail_credentials.json").write_text(json.dumps(FAKE_WEB_CLIENT), encoding="utf-8")
    return Settings(
        app=AppConfig(
            data_dir=tmp_path,
            host="0.0.0.0",
            port=8477,
            public_url=PUBLIC_ORIGIN,
        ),
        database=DatabaseConfig(filename="test.db"),
        logging=LoggingConfig(file=tmp_path / "test.log"),
    )


@pytest.fixture
def fake_keychain(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Never touch the developer's real Keychain while exercising pending state."""
    store: dict[str, str] = {}

    monkeypatch.setattr(
        oauth_module.keyring,
        "set_password",
        lambda _s, account, value: store.__setitem__(account, value),
    )
    monkeypatch.setattr(
        oauth_module.keyring, "get_password", lambda _s, account: store.get(account)
    )
    monkeypatch.setattr(
        oauth_module.keyring, "delete_password", lambda _s, account: store.pop(account, None)
    )
    return store


def _redirect_uri(authorization_url: str) -> str:
    return parse_qs(urlparse(authorization_url).query)["redirect_uri"][0]


def test_proxied_authorization_uses_public_callback(
    settings: Settings, fake_keychain: dict[str, str]
) -> None:
    client = TestClient(create_app(settings))
    response = client.post("/api/gmail/auth/start", headers={"host": "my-monee.gauravs-apps.in"})

    assert response.status_code == 200
    assert _redirect_uri(response.json()["authorization_url"]) == PUBLIC_CALLBACK

    status = client.get("/api/gmail/status", headers={"host": "my-monee.gauravs-apps.in"}).json()
    assert status["redirect_uri"] == PUBLIC_CALLBACK
    assert status["redirect_uris"] == [LOOPBACK_CALLBACK, PUBLIC_CALLBACK]


def test_local_authorization_keeps_loopback_callback(
    settings: Settings, fake_keychain: dict[str, str]
) -> None:
    client = TestClient(create_app(settings))
    response = client.post("/api/gmail/auth/start", headers={"host": "127.0.0.1:8477"})

    assert response.status_code == 200
    assert _redirect_uri(response.json()["authorization_url"]) == LOOPBACK_CALLBACK


def test_callback_exchanges_code_with_the_uri_used_at_start(
    settings: Settings, fake_keychain: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    exchanged: list[str] = []

    def fake_fetch_token(flow: object, code: str = "", **_kwargs: object) -> None:
        exchanged.append(flow.redirect_uri)  # type: ignore[attr-defined]
        flow.oauth2session.token = {  # type: ignore[attr-defined]
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "token_type": "Bearer",
            "expires_in": 3600,
            "expires_at": time.time() + 3600,
        }

    monkeypatch.setattr(oauth_module.Flow, "fetch_token", fake_fetch_token)

    client = TestClient(create_app(settings))
    host = {"host": "my-monee.gauravs-apps.in"}
    started = client.post("/api/gmail/auth/start", headers=host).json()

    callback = client.get(
        "/oauth/callback", params={"code": "auth-code", "state": started["state"]}, headers=host
    )

    assert callback.status_code == 200
    assert "Gmail connected" in callback.text
    assert exchanged == [PUBLIC_CALLBACK]
