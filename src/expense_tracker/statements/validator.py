"""Statement validation framework: independent financial arithmetic and integrity verification."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from expense_tracker.statements.parsers.base import ParsedStatementResult


@dataclass
class ValidationEquation:
    name: str
    formula: str
    expected_value: float
    calculated_value: float
    difference: float
    is_balanced: bool


@dataclass
class ValidationReport:
    status: str  # "VALIDATED", "REVIEW_REQUIRED", "VALIDATION_FAILED"
    equations: list[ValidationEquation] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


class StatementValidator:
    """Validates extracted statement data using institution-specific financial arithmetic."""

    TOLERANCE_EXACT: float = 0.05
    TOLERANCE_MINOR: float = 5.00

    def validate(self, result: ParsedStatementResult) -> ValidationReport:
        equations: list[ValidationEquation] = []
        messages: list[str] = []
        warnings: list[str] = []
        status = "VALIDATED"

        summary = result.summary
        if not summary:
            return ValidationReport(
                status="REVIEW_REQUIRED",
                messages=["No statement summary figures found to validate against."],
            )

        # Calculate transaction sums from extracted line items
        total_extracted_debits = sum(
            tx.debit_amount if tx.debit_amount is not None else (tx.amount if tx.credit_amount is None and tx.transaction_type in ("PURCHASE", "FEE", "INTEREST", "PAYMENT") else 0.0)
            for tx in result.transactions
        )
        total_extracted_credits = sum(
            tx.credit_amount if tx.credit_amount is not None else (tx.amount if tx.debit_amount is None and tx.transaction_type in ("REFUND", "TRANSFER") else 0.0)
            for tx in result.transactions
        )

        # 1. Bank Account Validation (e.g. Axis Bank)
        # Opening Balance + Deposits - Withdrawals = Closing Balance
        if result.statement_type == "BANK_ACCOUNT":
            extra = summary.extra_data
            op_bal = extra.get("opening_balance") or summary.previous_balance
            cl_bal = extra.get("closing_balance") or summary.total_due
            tot_w = extra.get("total_withdrawals") if extra.get("total_withdrawals") is not None else (summary.purchases if summary.purchases is not None else total_extracted_debits)
            tot_d = extra.get("total_deposits") if extra.get("total_deposits") is not None else (summary.payments if summary.payments is not None else total_extracted_credits)

            # A. Global Bank Balance Equation
            if op_bal is not None and cl_bal is not None:
                calc_closing = (op_bal or 0.0) + (tot_d or 0.0) - (tot_w or 0.0)
                diff = abs(calc_closing - cl_bal)
                is_balanced = diff <= self.TOLERANCE_EXACT
                eq = ValidationEquation(
                    name="Bank Balance Equation",
                    formula="Opening + Deposits - Withdrawals = Closing",
                    expected_value=cl_bal,
                    calculated_value=calc_closing,
                    difference=diff,
                    is_balanced=is_balanced,
                )
                equations.append(eq)

                if is_balanced:
                    messages.append(f"✓ Bank balance arithmetic matches exactly (Closing: ₹{cl_bal:,.2f})")
                elif diff <= self.TOLERANCE_MINOR:
                    status = "REVIEW_REQUIRED"
                    warnings.append(f"Minor discrepancy in bank closing balance: ₹{diff:.2f}")
                else:
                    status = "VALIDATION_FAILED"
                    warnings.append(f"Major bank balance mismatch: calculated ₹{calc_closing:,.2f} vs reported ₹{cl_bal:,.2f}")

            # B. Reported vs Extracted Totals Check
            if extra.get("total_withdrawals") is not None:
                w_diff = abs(total_extracted_debits - extra["total_withdrawals"])
                if w_diff <= self.TOLERANCE_EXACT:
                    messages.append(f"✓ Extracted withdrawals (₹{total_extracted_debits:,.2f}) match reported total withdrawals")
                else:
                    if status == "VALIDATED":
                        status = "REVIEW_REQUIRED"
                    warnings.append(f"Partial/mismatched withdrawals total: extracted ₹{total_extracted_debits:,.2f} vs reported ₹{extra['total_withdrawals']:,.2f}")

            if extra.get("total_deposits") is not None:
                d_diff = abs(total_extracted_credits - extra["total_deposits"])
                if d_diff <= self.TOLERANCE_EXACT:
                    messages.append(f"✓ Extracted deposits (₹{total_extracted_credits:,.2f}) match reported total deposits")
                else:
                    if status == "VALIDATED":
                        status = "REVIEW_REQUIRED"
                    warnings.append(f"Partial/mismatched deposits total: extracted ₹{total_extracted_credits:,.2f} vs reported ₹{extra['total_deposits']:,.2f}")


            # C. Step-by-step Running Balance Verification
            step_passed = 0
            step_total = 0
            cur_bal = op_bal
            for tx in result.transactions:
                if tx.running_balance is not None and cur_bal is not None:
                    step_total += 1
                    c_amt = tx.credit_amount or (tx.amount if tx.debit_amount is None and tx.transaction_type in ("REFUND", "TRANSFER") else 0.0)
                    d_amt = tx.debit_amount or (tx.amount if tx.credit_amount is None and tx.transaction_type in ("PURCHASE", "FEE", "INTEREST", "PAYMENT") else 0.0)
                    expected_next = round(cur_bal + c_amt - d_amt, 2)
                    if abs(expected_next - tx.running_balance) <= self.TOLERANCE_EXACT:
                        step_passed += 1
                    cur_bal = tx.running_balance

            if step_total > 0:
                if step_passed == step_total:
                    messages.append(f"✓ Running balance integrity: {step_passed}/{step_total} step checks passed")
                else:
                    status = "REVIEW_REQUIRED" if status != "VALIDATION_FAILED" else status
                    warnings.append(f"Running balance step discrepancy: {step_passed}/{step_total} steps verified")

        # 2. Scapia / Multi-Card Credit Card Validation
        # Previous Balance + Transactions - Payments/Refunds = New Balance (Total Due)
        elif result.institution == "SCAPIA":
            prev_b = summary.previous_balance or 0.0
            tx_sum = summary.purchases or 0.0
            pay_ref = summary.payments or 0.0
            tot_due = summary.total_due or 0.0

            calc_due = prev_b + tx_sum - abs(pay_ref) if pay_ref < 0 else prev_b + tx_sum - pay_ref
            diff = abs(calc_due - tot_due)
            is_balanced = diff <= self.TOLERANCE_EXACT

            eq = ValidationEquation(
                name="Scapia Combined Balance Equation",
                formula="Previous Balance + Transactions - Payments/Refunds = Total Due",
                expected_value=tot_due,
                calculated_value=calc_due,
                difference=diff,
                is_balanced=is_balanced,
            )
            equations.append(eq)

            if is_balanced:
                messages.append(f"✓ Scapia statement balance arithmetic matches exactly (Total Due: ₹{tot_due:,.2f})")
            elif diff <= self.TOLERANCE_MINOR:
                status = "REVIEW_REQUIRED"
                warnings.append(f"Minor discrepancy in Scapia total due: ₹{diff:.2f}")
            else:
                status = "VALIDATION_FAILED"
                warnings.append(f"Major Scapia arithmetic mismatch: calculated ₹{calc_due:,.2f} vs reported ₹{tot_due:,.2f}")

            # Check if multi-card notice applies
            if len(result.accounts) > 1:
                messages.append(f"ℹ Multi-card combined statement with {len(result.accounts)} cards. Transactions preserved with UNKNOWN card attribution.")

        # 3. Standard Credit Card Validation (e.g. Axis Credit Card)
        # Previous Balance - Payments + Purchases + Fees = Total Due
        else:
            prev_b = summary.previous_balance or 0.0
            pays = summary.payments or 0.0
            purs = summary.purchases or 0.0
            fees = summary.fees or 0.0
            tot_due = summary.total_due or 0.0

            if tot_due > 0:
                calc_due = prev_b - pays + purs + fees
                diff = abs(calc_due - tot_due)
                is_balanced = diff <= self.TOLERANCE_EXACT or diff <= self.TOLERANCE_MINOR
                eq = ValidationEquation(
                    name="Credit Card Balance Equation",
                    formula="Previous Balance - Payments + Purchases + Fees = Total Due",
                    expected_value=tot_due,
                    calculated_value=calc_due,
                    difference=diff,
                    is_balanced=is_balanced,
                )
                equations.append(eq)

                if diff <= self.TOLERANCE_EXACT:
                    messages.append(f"✓ Credit card balance arithmetic matches exactly (Total Due: ₹{tot_due:,.2f})")
                elif diff <= self.TOLERANCE_MINOR:
                    if status != "VALIDATION_FAILED":
                        status = "REVIEW_REQUIRED"
                    warnings.append(f"Minor discrepancy in credit card total due: ₹{diff:.2f}")
                else:
                    status = "VALIDATION_FAILED"
                    warnings.append(f"Credit card balance mismatch: calculated ₹{calc_due:,.2f} vs reported ₹{tot_due:,.2f}")

        # Fail-Fast: Zero-row detection if summary or sections indicate transactions exist
        if len(result.transactions) == 0:
            if (summary.purchases or 0.0) > 0 or (summary.payments or 0.0) > 0:
                status = "VALIDATION_FAILED"
                warnings.append("EXTRACTION_FAILED: Statement summary indicates activity, but 0 transaction rows were extracted")


        # Summary of extracted line items
        details = {
            "transaction_count": len(result.transactions),
            "account_count": len(result.accounts),
            "total_extracted_debits": total_extracted_debits,
            "total_extracted_credits": total_extracted_credits,
            "reported_purchases": summary.purchases,
            "reported_payments": summary.payments,
            "reported_total_due": summary.total_due,
            "equations": [
                {
                    "name": e.name,
                    "formula": e.formula,
                    "expected": e.expected_value,
                    "calculated": e.calculated_value,
                    "difference": round(e.difference, 2),
                    "is_balanced": e.is_balanced,
                }
                for e in equations
            ],
            "messages": messages,
            "warnings": warnings,
        }

        return ValidationReport(
            status=status,
            equations=equations,
            messages=messages,
            warnings=warnings,
            details=details,
        )
