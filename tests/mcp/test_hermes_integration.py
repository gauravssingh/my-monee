"""End-to-end integration tests using Hermes Agent CLI with MyMonee MCP.

These tests invoke Hermes Agent in headless one-shot mode (`hermes -z`),
evaluating tool selection, calculation fidelity, response generation, and latency.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.hermes


def _hermes_available() -> bool:
    return shutil.which("hermes") is not None


@pytest.fixture(autouse=True)
def require_hermes():
    if not _hermes_available():
        pytest.skip("Hermes CLI ('hermes') is not installed or not in PATH")


def _run_hermes_query(query: str, timeout: int = 90) -> tuple[str, dict]:
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        usage_path = Path(tmp.name)

    try:
        cmd = [
            "hermes",
            "-s", "mymonee",
            "-z", query,
            "--usage-file", str(usage_path),
        ]
        t0 = time.monotonic()
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
        duration = time.monotonic() - t0

        if proc.returncode != 0:
            pytest.fail(f"Hermes query failed (exit {proc.returncode}): {proc.stderr}\n{proc.stdout}")

        usage_data = {}
        if usage_path.exists() and usage_path.stat().st_size > 0:
            try:
                usage_data = json.loads(usage_path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001, S110
                pass

        usage_data["duration_sec"] = duration
        return proc.stdout.strip(), usage_data
    finally:
        if usage_path.exists():
            usage_path.unlink()


def test_hermes_category_spending_fuel():
    """Verify Hermes queries Fuel category spending via MCP and reports correct figure."""
    answer, usage = _run_hermes_query("What was my fuel spend for August 2026?")
    assert any(num in answer for num in ("15,293", "15293")), (
        f"Expected Fuel spend ₹15,293 not found in answer: {answer}"
    )
    assert usage.get("api_calls", 0) >= 1
    assert not usage.get("failed", False)


def test_hermes_monthly_summary():
    """Verify Hermes queries total monthly spending via MCP and reports correct aggregate."""
    answer, usage = _run_hermes_query("What was my total spent in August 2026?")
    assert any(num in answer for num in ("2,82,533", "282533", "282,533")), (
        f"Expected total spend ₹2,82,533 not found in answer: {answer}"
    )
    assert usage.get("api_calls", 0) >= 1
    assert not usage.get("failed", False)


def test_hermes_category_taxonomy():
    """Verify Hermes discovers budget taxonomy categories via list_budget_categories."""
    answer, usage = _run_hermes_query("What categories do I have for food in my budget tracker?")
    assert any(sub in answer.lower() for sub in ("groceries", "restaurants", "food delivery")), (
        f"Expected Food subcategories not found in answer: {answer}"
    )
    assert usage.get("api_calls", 0) >= 1
    assert not usage.get("failed", False)
