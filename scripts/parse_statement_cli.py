#!/usr/bin/env python3
"""CLI utility to parse and inspect every transaction entry and summary from a statement PDF."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add src to path
repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root / "src"))

from expense_tracker.statements.extractor import load_pdf_structure
from expense_tracker.statements.parsers.registry import get_statement_parser_registry
from expense_tracker.statements.validator import StatementValidator


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse and print all entries from a statement PDF.")
    parser.add_argument("pdf_path", type=str, help="Path to statement PDF file")
    parser.add_argument("--issuer", type=str, default=None, help="Expected issuer (e.g. AXIS, SCAPIA, HDFC)")
    args = parser.parse_args()

    pdf_file = Path(args.pdf_path).expanduser().resolve()
    if not pdf_file.exists():
        print(f"Error: File not found at {pdf_file}")
        sys.exit(1)

    print(f"\n=======================================================")
    print(f"  MyMonee Statement Parser CLI")
    print(f"  File: {pdf_file.name}")
    print(f"=======================================================\n")

    registry = get_statement_parser_registry()
    res = registry.detect_and_parse(str(pdf_file), expected_issuer=args.issuer)


    print(f"Parser Used:      {res.parser_name} v{res.parser_version}")
    print(f"Statement Type:   {res.statement_type}")
    print(f"Institution:      {res.institution}")

    # Accounts
    print(f"\n--- Accounts Detected ({len(res.accounts)}) ---")
    for acc in res.accounts:
        net_str = f" [{acc.card_network}]" if acc.card_network else ""
        lim_str = f" | Limit: ₹{acc.credit_limit:,.2f}" if acc.credit_limit is not None else ""
        print(f"  • {acc.account_name} ({acc.masked_identifier or acc.account_identifier}){net_str}{lim_str}")

    # Summary
    if res.summary:
        s = res.summary
        print(f"\n--- Statement Summary ---")
        if s.period_start and s.period_end:
            print(f"  Period:            {s.period_start.strftime('%d %b %Y')} – {s.period_end.strftime('%d %b %Y')}")
        if s.statement_date:
            print(f"  Statement Date:    {s.statement_date.strftime('%d %b %Y')}")
        if s.due_date:
            print(f"  Payment Due Date:  {s.due_date.strftime('%d %b %Y')}")
        if s.previous_balance is not None:
            print(f"  Previous/Opening:  ₹{s.previous_balance:,.2f}")
        if s.payments is not None:
            print(f"  Payments/Deposits: ₹{s.payments:,.2f}")
        if s.purchases is not None:
            print(f"  Purchases/Debits:  ₹{s.purchases:,.2f}")
        if s.fees is not None:
            print(f"  Fees/Interest:     ₹{s.fees:,.2f}")
        if s.total_due is not None:
            print(f"  Total Due/Closing: ₹{s.total_due:,.2f}")
        if s.minimum_due is not None:
            print(f"  Minimum Due:       ₹{s.minimum_due:,.2f}")

    # Line Items
    print(f"\n--- Extracted Transactions ({len(res.transactions)}) ---")
    if not res.transactions:
        print("  (No transactions extracted)")
    else:
        print(f"  {'#':<4} {'Date':<12} {'Type':<10} {'Amount':>14} {'Balance':>14}  {'Description'}")
        print("  " + "-" * 85)
        for i, tx in enumerate(res.transactions, 1):
            dt_str = tx.transaction_date.strftime("%d-%m-%Y")
            type_str = "CR" if tx.credit_amount is not None else "DR"
            amt_str = f"₹{tx.amount:,.2f}"
            bal_str = f"₹{tx.running_balance:,.2f}" if tx.running_balance is not None else "—"
            print(f"  {i:<4} {dt_str:<12} {type_str:<10} {amt_str:>14} {bal_str:>14}  {tx.description[:45]}")

    # Validation Report
    validator = StatementValidator()
    val_report = validator.validate(res)
    print(f"\n--- Arithmetic Validation Report ---")
    print(f"  Status: {val_report.status}")
    for eq in val_report.equations:
        bal_str = "✓ MATCH" if eq.is_balanced else f"✕ MISMATCH (Diff: ₹{eq.difference:.2f})"
        print(f"  Equation:   {eq.name}")
        print(f"  Formula:    {eq.formula}")
        print(f"  Expected:   ₹{eq.expected_value:,.2f}")
        print(f"  Calculated: ₹{eq.calculated_value:,.2f}")
        print(f"  Result:     {bal_str}")

    if val_report.messages:
        print(f"\n  Checks:")
        for msg in val_report.messages:
            print(f"    {msg}")

    if val_report.warnings:
        print(f"\n  Warnings / Issues:")
        for w in val_report.warnings:
            print(f"    ⚠️  {w}")


    print("\n=======================================================\n")


if __name__ == "__main__":
    main()
