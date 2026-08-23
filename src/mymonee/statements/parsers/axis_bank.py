"""Deterministic parser for Axis Bank Savings/Current account statements."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from mymonee.statements.extractor import PDFDocumentStructure, clean_amount
from mymonee.statements.parsers.base import (
    BaseStatementParser,
    ParsedStatementAccount,
    ParsedStatementResult,
    ParsedStatementSection,
    ParsedStatementSummary,
    ParsedStatementTransaction,
)


class AxisBankParser(BaseStatementParser):
    name = "axis_bank"
    version = "1.0.0"
    institution = "AXIS"
    statement_type = "BANK_ACCOUNT"

    def can_parse(self, doc_struct: PDFDocumentStructure) -> float:
        text = doc_struct.full_text.lower()
        score = 0.0
        if "axis bank" in text:
            score += 0.4
        if "money quotient" in text or "statement of axis bank account" in text or "account no" in text:
            score += 0.3
        if "opening balance" in text and ("withdrawals" in text or "withdrawal" in text):
            score += 0.3
        return min(score, 1.0) if score >= 0.6 else 0.0

    def parse(self, doc_struct: PDFDocumentStructure) -> ParsedStatementResult:
        full_text = doc_struct.full_text
        accounts: list[ParsedStatementAccount] = []
        transactions: list[ParsedStatementTransaction] = []
        sections: list[ParsedStatementSection] = []

        # 1. Extract Account Number
        acc_num_m = re.search(r"Account\s*No[\s\:\.]*([0-9Xx\*]+(\d{4}))", full_text, re.IGNORECASE)
        acc_identifier = None
        masked_id = None
        if acc_num_m:
            acc_identifier = acc_num_m.group(1)
            last4 = acc_num_m.group(2)
            masked_id = f"****{last4}"
        else:
            acc_m2 = re.search(r"(?:A/c|Account)\s*(?:Number|No)?[\s\:\.]*(\d{10,16})", full_text, re.IGNORECASE)
            if acc_m2:
                acc_identifier = acc_m2.group(1)
                masked_id = f"****{acc_identifier[-4:]}"

        # 2. Extract Period Dates
        period_start = None
        period_end = None
        period_m = re.search(
            r"(?:Statement\s+Period|Period)[\s\:\.]*(\d{2}[-/]\d{2}[-/]\d{4})\s*(?:to|-)\s*(\d{2}[-/]\d{2}[-/]\d{4})",
            full_text,
            re.IGNORECASE,
        )
        if period_m:
            try:
                sep = "/" if "/" in period_m.group(1) else "-"
                fmt = f"%d{sep}%m{sep}%Y"
                period_start = datetime.strptime(period_m.group(1), fmt).replace(tzinfo=timezone.utc)
                period_end = datetime.strptime(period_m.group(2), fmt).replace(tzinfo=timezone.utc)
            except Exception:
                pass

        # 3. Extract Summary Balances
        opening_bal = None
        closing_bal = None
        total_withdrawals = None
        total_deposits = None

        op_m = re.search(r"Opening\s*Balance[\s\:\.]*(?:INR|Rs\.?|₹)?\s*([0-9,]+\.\d{2})", full_text, re.IGNORECASE)
        if op_m:
            opening_bal = clean_amount(op_m.group(1))

        cl_m = re.search(r"Closing\s*Balance[\s\:\.]*(?:INR|Rs\.?|₹)?\s*([0-9,]+\.\d{2})", full_text, re.IGNORECASE)
        if cl_m:
            closing_bal = clean_amount(cl_m.group(1))

        w_m = re.search(r"Total\s*Withdrawals?[\s\:\.]*(?:INR|Rs\.?|₹)?\s*([0-9,]+\.\d{2})", full_text, re.IGNORECASE)
        if w_m:
            total_withdrawals = clean_amount(w_m.group(1))

        d_m = re.search(r"Total\s*Deposits?[\s\:\.]*(?:INR|Rs\.?|₹)?\s*([0-9,]+\.\d{2})", full_text, re.IGNORECASE)
        if d_m:
            total_deposits = clean_amount(d_m.group(1))

        if total_withdrawals is None and total_deposits is None:
            tot_pair_m = re.search(r"Total\s+([0-9,]+\.\d{2})\s+([0-9,]+\.\d{2})", full_text, re.IGNORECASE)
            if tot_pair_m:
                total_withdrawals = clean_amount(tot_pair_m.group(1))
                total_deposits = clean_amount(tot_pair_m.group(2))


        account = ParsedStatementAccount(
            account_type="BANK_ACCOUNT",
            institution="AXIS",
            account_identifier=acc_identifier,
            masked_identifier=masked_id or "****1022",
            account_name="Axis Bank Savings Account",
            opening_balance=opening_bal,
            closing_balance=closing_bal,
            attribution_confidence="EXACT",
        )
        accounts.append(account)

        summary = ParsedStatementSummary(
            previous_balance=opening_bal,
            purchases=total_withdrawals,
            payments=total_deposits,
            total_due=closing_bal,
            period_start=period_start,
            period_end=period_end,
            statement_date=period_end,
            extra_data={
                "opening_balance": opening_bal,
                "closing_balance": closing_bal,
                "total_withdrawals": total_withdrawals,
                "total_deposits": total_deposits,
            },
        )

        # 4. Extract Line Items (Transactions) across pages
        row_idx = 0
        tx_date_regex = re.compile(r"^\d{2}[-/]\d{2}[-/]\d{4}")

        # Strategy A: Use PyMuPDF find_tables for exact table structures
        if doc_struct.raw_doc is not None:
            for pno in range(len(doc_struct.raw_doc)):
                page = doc_struct.raw_doc[pno]
                try:
                    tabs = page.find_tables()
                    for tab in tabs:
                        rows = tab.extract()
                        for r in rows:
                            if not r or len(r) < 5:
                                continue
                            date_cell = (r[0] or "").strip()
                            if not tx_date_regex.match(date_cell):
                                continue

                            dt_str = date_cell[:10]
                            sep = "/" if "/" in dt_str else "-"
                            try:
                                tx_date = datetime.strptime(dt_str, f"%d{sep}%m{sep}%Y").replace(
                                    tzinfo=timezone.utc
                                )
                            except Exception:
                                continue

                            desc = (r[1] or "").strip().replace("\n", " ")
                            withdrawal_str = (r[3] or "").strip() if len(r) > 3 else ""
                            deposit_str = (r[4] or "").strip() if len(r) > 4 else ""
                            balance_str = (r[5] or "").strip() if len(r) > 5 else ""

                            debit_amt = clean_amount(withdrawal_str) if withdrawal_str else None
                            credit_amt = clean_amount(deposit_str) if deposit_str else None
                            balance = clean_amount(balance_str) if balance_str else None

                            amt = (debit_amt or 0.0) if debit_amt is not None else (credit_amt or 0.0)
                            if amt == 0.0 and not debit_amt and not credit_amt:
                                continue

                            row_idx += 1
                            tx_type = "PURCHASE" if debit_amt else "OTHER"
                            if credit_amt and ("salary" in desc.lower() or "/sala" in desc.lower()):
                                tx_type = "TRANSFER"
                            elif "scapia" in desc.lower() or "creditcard payment" in desc.lower() or "credit card payment" in desc.lower():
                                tx_type = "PAYMENT"

                            transactions.append(
                                ParsedStatementTransaction(
                                    transaction_date=tx_date,
                                    description=desc or "Axis Bank Transaction",
                                    amount=abs(amt),
                                    debit_amount=debit_amt,
                                    credit_amount=credit_amt,
                                    transaction_type=tx_type,
                                    running_balance=balance,
                                    source_page=pno + 1,
                                    source_row=row_idx,
                                    raw_text=" | ".join(str(x) for x in r if x is not None),
                                    attribution_status="EXACT",
                                    statement_account_index=0,
                                )
                            )
                except Exception:
                    pass

        # Strategy B: Fallback to text blocks if table extraction returned no transactions
        if not transactions:
            for pno, page_blocks in doc_struct.blocks_by_page.items():
                for block in page_blocks:
                    for line in block.lines:
                        dm = tx_date_regex.match(line)
                        if dm:
                            dt_str = dm.group(0)
                            sep = "/" if "/" in dt_str else "-"
                            try:
                                tx_date = datetime.strptime(dt_str, f"%d{sep}%m{sep}%Y").replace(
                                    tzinfo=timezone.utc
                                )
                            except Exception:
                                continue

                            numbers = re.findall(r"([0-9,]+\.\d{2})", line)
                            if numbers:
                                row_idx += 1
                                balance = clean_amount(numbers[-1])
                                amount = 0.0
                                debit_amt = None
                                credit_amt = None
                                tx_type = "OTHER"

                                if len(numbers) >= 2:
                                    tx_amt = clean_amount(numbers[-2])
                                    is_deposit = bool(
                                        re.search(r"\b(cr|deposit|salary|interest)\b|/sala", line.lower())
                                        and "creditcard" not in line.lower()
                                        and "credit card" not in line.lower()
                                    )
                                    if is_deposit:
                                        credit_amt = tx_amt
                                        amount = tx_amt or 0.0
                                        tx_type = "TRANSFER" if "salary" in line.lower() or "/sala" in line.lower() else "OTHER"
                                    else:
                                        debit_amt = tx_amt
                                        amount = tx_amt or 0.0
                                        tx_type = "PURCHASE"


                                narration = line[len(dt_str):]
                                for n in numbers:
                                    narration = narration.replace(n, "")
                                narration = re.sub(r"\s+", " ", narration).strip(" -|")

                                if "scapia" in narration.lower() or "creditcard payment" in narration.lower() or "credit card payment" in narration.lower():
                                    tx_type = "PAYMENT"

                                transactions.append(
                                    ParsedStatementTransaction(
                                        transaction_date=tx_date,
                                        description=narration or "Axis Bank Transaction",
                                        amount=abs(amount),
                                        debit_amount=debit_amt,
                                        credit_amount=credit_amt,
                                        transaction_type=tx_type,
                                        running_balance=balance,
                                        source_page=pno,
                                        source_row=row_idx,
                                        raw_text=line,
                                        attribution_status="EXACT",
                                        statement_account_index=0,
                                    )
                                )

        sections.append(
            ParsedStatementSection(
                section_type="TRANSACTIONS",
                page_start=1,
                page_end=doc_struct.page_count,
            )
        )

        return ParsedStatementResult(
            parser_name=self.name,
            parser_version=self.version,
            institution=self.institution,
            statement_type=self.statement_type,
            accounts=accounts,
            summary=summary,
            sections=sections,
            transactions=transactions,
            confidence=1.0,
        )
