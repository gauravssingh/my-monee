"""Dedicated parser for PhonePe transaction receipt emails."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from decimal import Decimal

from expense_tracker.parsers.base import EmailContext, ParsedTransaction
from expense_tracker.parsers.extract import combined_text

logger = logging.getLogger(__name__)

PHONEPE_SENDER = re.compile(r"noreply@phonepe\.com|phonepe\.com", re.I)
SUCCESS_SUBJECT = re.compile(r"(?:Payment|Recharge)\s+(?:for|of)\s+.*?is\s+successful", re.I)
AUTOPAY_REMINDER = re.compile(r"AutoPay will be debited|GST invoice|statement", re.I)
DATE_PATTERN = re.compile(r"\b([A-Za-z]{3}\s+\d{1,2},\s+\d{4})\b")


class PhonePeParser:
    name = "phonepe"
    priority = 85

    def can_parse(self, email: EmailContext) -> float:
        sender = email.sender or ""
        subject = email.subject or ""
        if not PHONEPE_SENDER.search(sender):
            return 0.0
        if AUTOPAY_REMINDER.search(subject):
            return 0.90  # Handle as non-transaction reminder
        if SUCCESS_SUBJECT.search(subject) or "is successful" in subject.lower():
            return 0.95
        return 0.50

    def parse(self, email: EmailContext) -> list[ParsedTransaction]:
        text = combined_text(email.subject, email.body_text, email.body_html)
        subject = email.subject or ""

        # 1. Informational AutoPay reminders, GST invoices, statements
        if AUTOPAY_REMINDER.search(subject):
            return []

        # 2. Extract Amount
        amount: Decimal | None = None
        m_amt = re.search(r"(?:Amount|Bill/Recharge Amount)\s*:\s*₹?\s*([0-9,]+(?:\.[0-9]+)?)", text, re.I)
        if m_amt:
            amount = Decimal(m_amt.group(1).replace(",", ""))
        if amount is None or amount <= 0:
            m_subj_amt = re.search(r"of\s+₹\s*([0-9,]+(?:\.[0-9]+)?)\s+is\s+successful", subject, re.I)
            if m_subj_amt:
                amount = Decimal(m_subj_amt.group(1).replace(",", ""))

        if amount is None or amount <= 0:
            return []

        # 3. Extract Date
        tx_date: datetime | None = None
        m_date = DATE_PATTERN.search(text)
        if m_date:
            try:
                tx_date = datetime.strptime(m_date.group(1), "%b %d, %Y").replace(tzinfo=timezone.utc)
            except Exception:
                tx_date = None
        if tx_date is None:
            tx_date = email.received_at

        if tx_date is None:
            return []

        # 4. Extract Merchant / Provider
        merchant_raw: str | None = None
        m_prov = re.search(r"Provider\s*:\s*([^\n\r]+?)(?:\s+Hi\s+|\s+If\s+you|\s+Cheers|\s*$)", text, re.I)
        if m_prov:
            val = m_prov.group(1).strip()
            if val and not val.lower().startswith("partners never"):
                merchant_raw = val

        if not merchant_raw:
            m_subj_merch = re.search(r"(?:Payment for|Recharge for)\s+(.*?)\s+of\s+₹", subject, re.I)
            if m_subj_merch:
                raw_val = m_subj_merch.group(1).strip()
                raw_val = re.sub(r"\s+(Fastag|Gas|E-Challan|DTH|Mobile)\s*$", "", raw_val, flags=re.I).strip()
                if raw_val:
                    merchant_raw = raw_val

        if not merchant_raw:
            merchant_raw = "PhonePe"

        # 5. Extract Category and map to internal taxonomy
        m_cat = re.search(r"Category\s*:\s*([^\n\r]+?)(?:\s+Provider|\s+Hi|\s*$)", text, re.I)
        raw_category = m_cat.group(1).strip().lower() if m_cat else ""
        
        category_slug = "utilities"
        subcategory_slug = None
        if "gas" in raw_category or "gas" in merchant_raw.lower():
            category_slug = "utilities"
            subcategory_slug = "gas"
        elif "fastag" in raw_category or "fastag" in merchant_raw.lower():
            category_slug = "car"
            subcategory_slug = "fastag"
        elif "challan" in raw_category or "challan" in merchant_raw.lower():
            category_slug = "car"
            subcategory_slug = "fines"
        elif "dth" in raw_category or "mobile" in raw_category or "recharge" in subject.lower():
            category_slug = "utilities"
            subcategory_slug = "mobile"
        elif "electricity" in raw_category:
            category_slug = "utilities"
            subcategory_slug = "electricity"

        # 6. Extract Bank Account last digits
        account: str | None = None
        m_acc = re.search(r"Bank Account\s*:\s*X*(\d{2,6})", text, re.I)
        if m_acc:
            account = m_acc.group(1)

        # 7. Extract Reference Numbers
        bank_ref: str | None = None
        m_bank_ref = re.search(r"Bank Ref\. No\.\s*:\s*([A-Za-z0-9]+)", text, re.I)
        if m_bank_ref:
            bank_ref = m_bank_ref.group(1).strip()

        txn_id: str | None = None
        m_txn_id = re.search(r"Txn\.\s*ID\s*:\s*([A-Za-z0-9]+)", text, re.I)
        if m_txn_id:
            txn_id = m_txn_id.group(1).strip()

        reference_number = bank_ref or txn_id

        return [
            ParsedTransaction(
                amount=amount,
                currency="INR",
                direction="debit",
                transaction_date=tx_date,
                transaction_type="purchase",
                merchant_raw=merchant_raw,
                payment_method="upi",
                account=account,
                card=None,
                upi_id=None,
                reference_number=reference_number,
                bank_reference=txn_id or bank_ref,
                description=subject,
                extra={
                    "parser": self.name,
                    "provider": merchant_raw,
                    "phonepe_txn_id": txn_id,
                    "category_slug": category_slug,
                    "subcategory_slug": subcategory_slug,
                    "classification_source": "rule",
                    "classification_confidence": 0.95,
                    "classification_signals": {"rule": "phonepe_receipt", "category": raw_category or "bill"},
                    "needs_review": False,
                    "is_transfer": False,
                    "is_refund": False,
                    "excludes_from_spending": False,
                },
            )
        ]
