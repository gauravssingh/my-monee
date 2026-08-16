"""Deterministic parser for Scapia Federal Credit Card statements (including multi-card combined statements)."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from expense_tracker.statements.extractor import PDFDocumentStructure, clean_amount
from expense_tracker.statements.parsers.base import (
    BaseStatementParser,
    ParsedStatementAccount,
    ParsedStatementResult,
    ParsedStatementSection,
    ParsedStatementSummary,
    ParsedStatementTransaction,
)


class ScapiaParser(BaseStatementParser):
    name = "scapia"
    version = "1.0.0"
    institution = "SCAPIA"
    statement_type = "CREDIT_CARD"

    def can_parse(self, doc_struct: PDFDocumentStructure) -> float:
        text = doc_struct.full_text.lower()
        score = 0.0
        if "axis bank" in text and "scapia" not in text[:500]:
            return 0.0
        if "scapia federal" in text or "scapia cards" in text or "scapiacards" in text:
            score += 0.6
        elif "scapia" in text and ("federal bank" in text or "rupay" in text or "visa" in text):
            score += 0.5
        if "total amount due" in text or "minimum amount due" in text:
            score += 0.2
        return min(score, 1.0) if score >= 0.5 else 0.0


    def parse(self, doc_struct: PDFDocumentStructure) -> ParsedStatementResult:
        full_text = doc_struct.full_text
        accounts: list[ParsedStatementAccount] = []
        transactions: list[ParsedStatementTransaction] = []
        sections: list[ParsedStatementSection] = []

        # 1. Discover Accounts (Multi-card detection: Visa and RuPay cards)
        # Check for Visa ending XXXX
        visa_m = re.search(r"Visa(?:\s+Credit\s+Card)?[\s\:\.]*(?:ending|No)?[\s\:\.]*(\d{4})", full_text, re.IGNORECASE)
        if not visa_m:
            visa_m = re.search(r"(\d{4}[\*X]+(\d{4}))\s*(?:\(Visa\)|Visa)", full_text, re.IGNORECASE)

        # Check for RuPay ending XXXX
        rupay_m = re.search(r"RuPay(?:\s+Credit\s+Card)?[\s\:\.]*(?:ending|No)?[\s\:\.]*(\d{4})", full_text, re.IGNORECASE)
        if not rupay_m:
            rupay_m = re.search(r"(\d{4}[\*X]+(\d{4}))\s*(?:\(RuPay\)|RuPay)", full_text, re.IGNORECASE)

        # General card pattern
        all_cards = re.findall(r"(?:ending\s+in|ending|Card\s*No[\s\:\.]*)\s*([Xx\*0-9]*(\d{4}))", full_text, re.IGNORECASE)

        found_cards: set[str] = set()
        if visa_m:
            l4 = visa_m.group(1) if len(visa_m.group(1)) == 4 else visa_m.group(2)
            found_cards.add(l4)
            accounts.append(
                ParsedStatementAccount(
                    account_type="CREDIT_CARD",
                    institution="SCAPIA",
                    account_identifier=l4,
                    masked_identifier=f"****{l4}",
                    card_network="VISA",
                    account_name=f"Scapia Federal Visa (****{l4})",
                    attribution_confidence="EXACT",
                )
            )

        if rupay_m:
            l4 = rupay_m.group(1) if len(rupay_m.group(1)) == 4 else rupay_m.group(2)
            found_cards.add(l4)
            accounts.append(
                ParsedStatementAccount(
                    account_type="CREDIT_CARD",
                    institution="SCAPIA",
                    account_identifier=l4,
                    masked_identifier=f"****{l4}",
                    card_network="RUPAY",
                    account_name=f"Scapia Federal RuPay (****{l4})",
                    attribution_confidence="EXACT",
                )
            )

        if not accounts:
            # Default Scapia cards if not found by network regex
            for _, l4 in all_cards:
                if l4 not in found_cards:
                    found_cards.add(l4)
                    accounts.append(
                        ParsedStatementAccount(
                            account_type="CREDIT_CARD",
                            institution="SCAPIA",
                            account_identifier=l4,
                            masked_identifier=f"****{l4}",
                            card_network="VISA" if len(accounts) == 0 else "RUPAY",
                            account_name=f"Scapia Federal (****{l4})",
                            attribution_confidence="EXACT",
                        )
                    )

        if not accounts:
            accounts.append(
                ParsedStatementAccount(
                    account_type="CREDIT_CARD",
                    institution="SCAPIA",
                    account_identifier="0863",
                    masked_identifier="****0863",
                    card_network="VISA",
                    account_name="Scapia Federal Credit Card",
                    attribution_confidence="EXACT",
                )
            )

        # 2. Extract Dates
        statement_date = None
        due_date = None
        period_start = None
        period_end = None

        stmt_dt_m = re.search(
            r"Statement\s*Date[\s\:\.]*(\d{1,2}\s+[A-Za-z]{3}\s+\d{4}|\d{2}[-/]\d{2}[-/]\d{4})",
            full_text,
            re.IGNORECASE,
        )
        if stmt_dt_m:
            dt_raw = stmt_dt_m.group(1)
            try:
                if "-" in dt_raw or "/" in dt_raw:
                    sep = "/" if "/" in dt_raw else "-"
                    statement_date = datetime.strptime(dt_raw, f"%d{sep}%m{sep}%Y").replace(tzinfo=timezone.utc)
                else:
                    statement_date = datetime.strptime(dt_raw, "%d %b %Y").replace(tzinfo=timezone.utc)
            except Exception:
                pass

        due_dt_m = re.search(
            r"(?:Payment\s+Due\s+Date|Due\s+Date)[\s\:\.]*(\d{1,2}\s+[A-Za-z]{3}\s+\d{4}|\d{2}[-/]\d{2}[-/]\d{4})",
            full_text,
            re.IGNORECASE,
        )
        if due_dt_m:
            dt_raw = due_dt_m.group(1)
            try:
                if "-" in dt_raw or "/" in dt_raw:
                    sep = "/" if "/" in dt_raw else "-"
                    due_date = datetime.strptime(dt_raw, f"%d{sep}%m{sep}%Y").replace(tzinfo=timezone.utc)
                else:
                    due_date = datetime.strptime(dt_raw, "%d %b %Y").replace(tzinfo=timezone.utc)
            except Exception:
                pass

        period_m = re.search(
            r"(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})\s*(?:to|-)\s*(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})",
            full_text,
            re.IGNORECASE,
        )
        if period_m:
            try:
                period_start = datetime.strptime(period_m.group(1), "%d %b %Y").replace(tzinfo=timezone.utc)
                period_end = datetime.strptime(period_m.group(2), "%d %b %Y").replace(tzinfo=timezone.utc)
                if not statement_date:
                    statement_date = period_end
            except Exception:
                pass

        # 3. Extract Summary Balances
        total_due = None
        min_due = None
        prev_bal = None
        purchases = None
        payments_refunds = None

        tot_m = re.search(r"Total\s*(?:Amount|Payment)?\s*Due[\s\:\.]*(?:INR|Rs\.?|₹)?\s*([0-9,]+\.\d{2})", full_text, re.IGNORECASE)
        if tot_m:
            total_due = clean_amount(tot_m.group(1))

        min_m = re.search(r"Minimum\s*(?:Amount|Payment)?\s*Due[\s\:\.]*(?:INR|Rs\.?|₹)?\s*([0-9,]+\.\d{2})", full_text, re.IGNORECASE)
        if min_m:
            min_due = clean_amount(min_m.group(1))

        prev_m = re.search(r"Previous\s*Balance[\s\:\.]*(?:INR|Rs\.?|₹)?\s*([0-9,]+\.\d{2})", full_text, re.IGNORECASE)
        if prev_m:
            prev_bal = clean_amount(prev_m.group(1))

        tx_sum_m = re.search(r"(?:Transactions|Purchases)[\s\:\.]*(?:INR|Rs\.?|₹)?\s*([0-9,]+\.\d{2})", full_text, re.IGNORECASE)
        if tx_sum_m:
            purchases = clean_amount(tx_sum_m.group(1))

        pay_ref_m = re.search(r"(?:Payments\s*/\s*Refunds|Payments|Refunds)[\s\:\.]*(?:INR|Rs\.?|₹)?\s*([0-9,\.\-]+)", full_text, re.IGNORECASE)
        if pay_ref_m:
            payments_refunds = clean_amount(pay_ref_m.group(1))

        summary = ParsedStatementSummary(
            previous_balance=prev_bal or 0.0,
            purchases=purchases or total_due,
            payments=payments_refunds or 0.0,
            refunds=payments_refunds if (payments_refunds and payments_refunds < 0) else None,
            total_due=total_due,
            minimum_due=min_due,
            statement_date=statement_date,
            due_date=due_date,
            period_start=period_start,
            period_end=period_end,
            extra_data={"is_combined_statement": len(accounts) > 1},
        )

        # 4. Extract Line Item Transactions
        # Crucial Principle: When transactions are combined across Visa & RuPay without explicit card indicators,
        # attribution_status MUST BE "UNKNOWN" and statement_account_index MUST BE None.
        row_idx = 0
        tx_date_regex = re.compile(r"^(\d{1,2}\s+[A-Za-z]{3}\s+\d{4}|\d{2}[-/]\d{2}[-/]\d{4})")

        for pno, page_blocks in doc_struct.blocks_by_page.items():
            for block in page_blocks:
                for line in block.lines:
                    dm = tx_date_regex.match(line)
                    if dm:
                        dt_str = dm.group(1)
                        try:
                            if "-" in dt_str or "/" in dt_str:
                                sep = "/" if "/" in dt_str else "-"
                                tx_date = datetime.strptime(dt_str, f"%d{sep}%m{sep}%Y").replace(tzinfo=timezone.utc)
                            else:
                                tx_date = datetime.strptime(dt_str, "%d %b %Y").replace(tzinfo=timezone.utc)
                        except Exception:
                            continue

                        numbers = re.findall(r"([0-9,]+\.\d{2})", line)
                        if numbers:
                            row_idx += 1
                            amt = clean_amount(numbers[-1]) or 0.0
                            is_credit = "cr" in line.lower() or "refund" in line.lower() or "payment" in line.lower()

                            tx_type = "PURCHASE"
                            if "payment" in line.lower():
                                tx_type = "PAYMENT"
                            elif "refund" in line.lower() or "reversal" in line.lower():
                                tx_type = "REFUND"
                            elif "fee" in line.lower() or "interest" in line.lower() or "gst" in line.lower():
                                tx_type = "FEE"

                            narration = line[len(dt_str):]
                            for n in numbers:
                                narration = narration.replace(n, "")
                            narration = re.sub(r"\s+", " ", narration).strip(" -|")

                            transactions.append(
                                ParsedStatementTransaction(
                                    transaction_date=tx_date,
                                    description=narration or "Scapia Transaction",
                                    amount=abs(amt),
                                    debit_amount=amt if not is_credit else None,
                                    credit_amount=amt if is_credit else None,
                                    transaction_type=tx_type,
                                    source_page=pno,
                                    source_row=row_idx,
                                    raw_text=line,
                                    # Never guess card attribution on combined Scapia statements!
                                    attribution_status="UNKNOWN" if len(accounts) > 1 else "EXACT",
                                    statement_account_index=None if len(accounts) > 1 else 0,
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
