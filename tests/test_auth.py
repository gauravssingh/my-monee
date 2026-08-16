from __future__ import annotations

from pathlib import Path
from fastapi.testclient import TestClient

from expense_tracker.app import create_app
from expense_tracker.config import AppConfig, DatabaseConfig, LoggingConfig, Settings


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        app=AppConfig(data_dir=tmp_path),
        database=DatabaseConfig(filename="test.db"),
        logging=LoggingConfig(file=tmp_path / "test.log"),
    )


def test_auth_lifecycle(tmp_path: Path):
    app = create_app(_settings(tmp_path))
    client = TestClient(app)

    # 1. Check initial status -> not configured
    res = client.get("/api/auth/status")
    assert res.status_code == 200
    data = res.json()
    assert data["configured"] is False

    # 2. Setup PIN "123456"
    res = client.post("/api/auth/setup", json={"pin": "123456"})
    assert res.status_code == 200
    token = res.json()["token"]
    assert token is not None

    # 3. Check status with token
    res = client.get("/api/auth/status", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["configured"] is True
    assert res.json()["authenticated"] is True

    # 4. Login with wrong PIN -> 401
    res = client.post("/api/auth/login", json={"pin": "000000"})
    assert res.status_code == 401

    # 5. Login with correct PIN -> 200
    res = client.post("/api/auth/login", json={"pin": "123456"})
    assert res.status_code == 200
    new_token = res.json()["token"]
    assert new_token is not None

    # 6. Change PIN
    res = client.post("/api/auth/change-pin", json={"old_pin": "123456", "new_pin": "654321"})
    assert res.status_code == 200

    # 7. Old PIN fails, new PIN succeeds
    assert client.post("/api/auth/login", json={"pin": "123456"}).status_code == 401
    assert client.post("/api/auth/login", json={"pin": "654321"}).status_code == 200


def test_configured_pin_is_enforced_on_data_routes(tmp_path: Path):
    """The lock screen must be backed by real server-side enforcement, not just
    a client-side gate — a configured PIN should block every /api/* data route
    (except /api/auth/* and /api/health) until a valid session token is presented."""
    app = create_app(_settings(tmp_path))
    client = TestClient(app)

    # Before any PIN is configured, data routes are open (no lock to enforce yet).
    assert client.get("/api/overview").status_code == 200
    assert client.get("/api/health").status_code == 200

    token = client.post("/api/auth/setup", json={"pin": "123456"}).json()["token"]
    client.cookies.clear()  # setup's response set a session cookie — drop it to test as logged-out

    # Now that a PIN is configured, an unauthenticated request must be rejected.
    res = client.get("/api/overview")
    assert res.status_code == 401

    # /api/auth/* and /api/health stay reachable so the lock screen itself can load.
    assert client.get("/api/auth/status").status_code == 200
    assert client.get("/api/health").status_code == 200

    # A valid session token (via Bearer header or cookie) restores access.
    res = client.get("/api/overview", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200

    client.cookies.set("mymonee_session", token)
    assert client.get("/api/overview").status_code == 200
