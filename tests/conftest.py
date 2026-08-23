from __future__ import annotations

from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from mymonee.app import create_app
from mymonee.config import AppConfig, DatabaseConfig, LoggingConfig, Settings
from mymonee.db.session import get_session_factory, init_db


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    return Settings(
        app=AppConfig(data_dir=tmp_path),
        database=DatabaseConfig(filename="test.db"),
        logging=LoggingConfig(file=tmp_path / "test.log"),
    )


@pytest.fixture
def db_session(test_settings: Settings) -> Generator[Session, None, None]:
    init_db(test_settings)
    session_factory = get_session_factory()
    with session_factory() as session:
        yield session


@pytest.fixture
def client(test_settings: Settings) -> TestClient:
    app = create_app(test_settings)
    return TestClient(app)
