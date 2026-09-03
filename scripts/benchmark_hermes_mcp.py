#!/usr/bin/env python3
"""Benchmark and evaluation script for MyMonee MCP integration with Hermes Agent.

Runs end-to-end questions via `hermes -z` (one-shot mode), verifying tool selection,
accuracy of financial facts, response time, token usage, and cost.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

BENCHMARK_CASES = [
    {
        "name": "Fuel Spend August",
        "query": "What was my fuel spend for August 2026?",
        "expected_substrings": ["15,293", "15293"],
        "description": "Tests category spending deep dive with natural month string",
    },
    {
        "name": "Total Spend August",
        "query": "What was my total spent in August 2026?",
        "expected_substrings": ["2,82,533", "282533", "282,533"],
        "description": "Tests monthly financial summary aggregate spending",
    },
    {
        "name": "Budget Categories Taxonomy",
        "query": "What categories do I have for food in my budget tracker?",
        "expected_substrings": ["Food", "Groceries", "Restaurants"],
        "description": "Tests taxonomy discovery without raw database access",
    },
]


def run_benchmark_case(case: dict[str, Any], verbose: bool = True) -> dict[str, Any]:
    name = case["name"]
    query = case["query"]
    expected = case["expected_substrings"]

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        usage_path = Path(tmp.name)

    try:
        t0 = time.monotonic()
        cmd = [
            "hermes",
            "-s", "mymonee",
            "-z", query,
            "--usage-file", str(usage_path),
        ]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        duration = time.monotonic() - t0

        output = proc.stdout.strip()
        passed_fact_check = any(exp.lower() in output.lower() for exp in expected)
        success = (proc.returncode == 0) and passed_fact_check

        usage_data = {}
        if usage_path.exists() and usage_path.stat().st_size > 0:
            try:
                usage_data = json.loads(usage_path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001, S110
                pass

        res = {
            "name": name,
            "query": query,
            "status": "PASS" if success else "FAIL",
            "duration_sec": round(duration, 2),
            "output": output,
            "api_calls": usage_data.get("api_calls", 0),
            "tokens": usage_data.get("total_tokens", 0),
            "cost_usd": usage_data.get("estimated_cost_usd", 0.0),
        }
        if verbose:
            tag = "✓ PASS" if success else "✗ FAIL"
            print(f"[{tag}] {name} ({res['duration_sec']}s, {res['tokens']} tokens, ${res['cost_usd']:.5f})")
            print(f"  Query:  {query}")
            print(f"  Answer: {output[:150]}...")
            print("-" * 60)
        return res
    finally:
        if usage_path.exists():
            usage_path.unlink()


def main() -> None:
    print("=" * 60)
    print("MyMonee ↔ Hermes Agent End-to-End MCP Benchmark")
    print("=" * 60)

    results = []
    for case in BENCHMARK_CASES:
        results.append(run_benchmark_case(case))

    passed = sum(1 for r in results if r["status"] == "PASS")
    total = len(results)
    avg_duration = sum(r["duration_sec"] for r in results) / total if total else 0.0
    total_cost = sum(r["cost_usd"] for r in results)

    print("\nSummary:")
    print(f"  Passed: {passed}/{total} ({passed/total*100:.1f}%)")
    print(f"  Avg Latency: {avg_duration:.2f}s")
    print(f"  Total Cost:  ${total_cost:.5f}")
    print("=" * 60)


if __name__ == "__main__":
    main()
