from __future__ import annotations

import logging
from pathlib import Path

import pytest

from mymonee.config import AppConfig, DatabaseConfig, LoggingConfig, Settings
from mymonee.logging_setup import RedactingFilter, setup_logging


def test_redacting_filter_masks_credentials() -> None:
    redactor = RedactingFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="Connecting with password: secretpassword123 and token: my_secret_token_abc",
        args=(),
        exc_info=None,
    )
    assert redactor.filter(record) is True
    assert "secretpassword123" not in record.msg
    assert "my_secret_token_abc" not in record.msg
    assert "[REDACTED]" in record.msg


def test_redacting_filter_masks_card_numbers() -> None:
    redactor = RedactingFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=20,
        msg="Transaction charged to card 4111 2222 3333 4444 on merchant POS",
        args=(),
        exc_info=None,
    )
    assert redactor.filter(record) is True
    assert "4111" not in record.msg
    assert "2222" not in record.msg
    assert "****-****-****-4444" in record.msg


def test_redacting_filter_masks_bearer_and_api_keys() -> None:
    redactor = RedactingFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=30,
        msg="Authorization: Bearer ya29.a0AfH6SMBabc123456789 and Google key AIzaSyD9876543210123456789012345678",
        args=(),
        exc_info=None,
    )
    assert redactor.filter(record) is True
    assert "ya29.a0AfH6SMBabc123456789" not in record.msg
    assert "AIzaSyD9876543210123456789012345678" not in record.msg
    assert "[REDACTED_TOKEN]" in record.msg
    assert "[REDACTED_API_KEY]" in record.msg


def test_redacting_filter_fails_closed_on_formatting_error() -> None:
    redactor = RedactingFilter()
    # Missing 1 argument for 2 placeholders triggers TypeError in getMessage()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=40,
        msg="Secret token is %s and password is %s",
        args=("only_one_arg",),
        exc_info=None,
    )
    # Should not raise exception and should fail closed (redact rather than leaking raw record)
    assert redactor.filter(record) is True
    assert record.msg == "[redacted log record formatting error]"
    assert record.args == ()


def test_setup_logging_configuration(tmp_path: Path) -> None:
    log_file = tmp_path / "app.log"
    settings = Settings(
        app=AppConfig(data_dir=tmp_path),
        database=DatabaseConfig(filename="test.db"),
        logging=LoggingConfig(level="DEBUG", file=log_file),
    )

    setup_logging(settings)
    root = logging.getLogger()
    assert root.level == logging.DEBUG
    assert len(root.handlers) >= 2  # console + file

    test_logger = logging.getLogger("mymonee.test_logger")
    test_logger.debug("Debug message for testing")

    # Verify file was written
    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert "mymonee.test_logger" in content
    assert "Debug message for testing" in content


def test_setup_logging_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    settings = Settings(
        app=AppConfig(data_dir=tmp_path),
        database=DatabaseConfig(filename="test.db"),
        logging=LoggingConfig(level="DEBUG", file=tmp_path / "test.log"),
    )
    setup_logging(settings)
    root = logging.getLogger()
    assert root.level == logging.WARNING
