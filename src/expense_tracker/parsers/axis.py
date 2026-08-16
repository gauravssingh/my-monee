"""Axis Bank alert parser + credit intelligence (salary vs transfers)."""

from __future__ import annotations

import re
from decimal import Decimal

from expense_tracker.parsers.base import EmailContext, ParsedTransaction
from expense_tracker.parsers.extract import (
    combined_text,
    extract_account,
    extract_card,
    html_to_text,
    parse_amount,
    parse_date_near_amount,
)

AXIS_SENDER = re.compile(r"alerts@axis\.bank\.in|axis\.bank\.in", re.I)

# "by NEFT/CHASH00053023262/Sala" or "by ACH-DR-RASMEC KOMPALLY-NOD"
CHANNEL_REF = re.compile(
    r"\b((?:NEFT|IMPS|RTGS|ACH(?:-DR|-CR)?|UPILITE|UPI(?:/[A-Za-z0-9]+)?)\s*[-/]\s*[A-Za-z0-9/.\-& ]{2,100})",
    re.I,
)
SALARY_REF = re.compile(r"(?:NEFT|IMPS|RTGS)\s*/[A-Za-z0-9/.\- ]*?\bSala(?:ry)?\b", re.I)
CREDITED_WITH = re.compile(
    r"credited with\s*INR\s*([0-9,]+\.?[0-9]*|\.[0-9]+)",
    re.I,
)
AMOUNT_CREDITED = re.compile(
    r"Amount Credited:\s*INR\s*([0-9,]+\.?[0-9]*|\.[0-9]+)",
    re.I,
)
DEBITED_WITH = re.compile(
    r"(?:debited with|Amount Debited:)\s*INR\s*([0-9,]+\.?[0-9]*|\.[0-9]+)",
    re.I,
)
DECLINED_ALERT = re.compile(
    r"\bdeclined\b|transaction attempt.{0,100}declined|has been declined",
    re.I,
)


def is_axis_declined_alert(subject: str, text: str) -> bool:
    blob = f"{subject}\n{text}"
    return bool(DECLINED_ALERT.search(blob))


def extract_axis_merchant(text: str) -> str | None:
    """Extract merchant name from Axis Bank credit card or debit alerts."""
    # 1. Explicit 'Merchant Name:' block
    m = re.search(r"Merchant\s*Name\s*[:\-]?\s*[\n\r]*\s*([^\n\r\t]+)", text, re.I)
    if m:
        val = m.group(1).strip()
        val = re.split(r"(?:Axis\s+Bank|Credit\s+Card|Date\s*&|Available\s+Limit|Total\s+Credit|Info[:\s])", val, flags=re.I)[0].strip()
        if val and not val.lower().startswith(("axis bank", "inr", "dear ", "credit card")):
            return val

    # 2. 'spent ... at <Merchant>'
    m = re.search(r"spent\s+.*?\s+at\s+([^\n\r\t,]+?)(?:\s+on\s+\d{2}|\s+using|\s+with|\s*$)", text, re.I)
    if m:
        val = m.group(1).strip()
        val = re.split(r"(?:Axis\s+Bank|Credit\s+Card|Date\s*&|Available\s+Limit)", val, flags=re.I)[0].strip()
        if val and not val.lower().startswith(("axis bank", "inr", "credit card")):
            return val

    # 3. 'at <Merchant> on <Date>'
    m = re.search(r"\bat\s+([^\n\r\t,]+?)\s+on\s+\d{2}[-/]\d{2}[-/]\d{4}", text, re.I)
    if m:
        val = m.group(1).strip()
        if val and not val.lower().startswith(("axis bank", "inr", "credit card")):
            return val

    # 4. Info: <Merchant>
    m = re.search(r"\bInfo\s*[:\-]\s*([^\n\r\t]+)", text, re.I)
    if m:
        val = m.group(1).strip()
        val = re.split(r"(?:Axis\s+Bank|Credit\s+Card|Date\s*&|Available\s+Limit)", val, flags=re.I)[0].strip()
        if val and not val.lower().startswith(("axis bank", "inr", "credit card")):
            return val

    return None


def _clean_channel_ref(raw: str) -> str:
    value = re.sub(r"\s+", " ", raw).strip()
    value = re.split(r"\.\s+To check|\.\s+If |\.\s+Feel|\s+&nbsp;", value, maxsplit=1)[0]
    return value.strip(" .")[:120]


def extract_axis_channel_ref(text: str) -> str | None:
    # 1. Explicit 'Transaction Info:' field in Axis alert emails
    m_info = re.search(r"Transaction\s*Info\s*[:\-]?\s*[\n\r]*\s*([^\n\r\t]+)", text, re.I)
    if m_info:
        val = m_info.group(1).strip()
        val = re.split(
            r"(?:Available\s+Limit|Total\s+Credit|Date\s*&|Account\s*Number|\.\s+To\s+check|\.\s+If|\.\s+Feel|\s+&nbsp;)",
            val,
            flags=re.I,
        )[0].strip()
        if val and not val.lower().startswith(("dear ", "inr ", "axis bank")):
            return _clean_channel_ref(val)

    # 2. General channel pattern (UPI, NEFT, IMPS, RTGS, ACH)
    match = CHANNEL_REF.search(text)
    if not match:
        return None
    return _clean_channel_ref(match.group(1))


def classify_axis_credit(channel_ref: str | None, text: str) -> dict:
    """
    Return enrichment for Axis credits.

    Salary signal (validated on 7/7 2026 samples): NEFT/.../Sala
    Other Axis credits in sample set were UPI/P2A (or similar) — treat as
    non-income money movement (own-account / P2A), not salary income.

    Income is salary only. Pay-period mapping (dashboard): late-month credit
    → next month; day 1–2 credit → current month (delayed payroll).
       """
    blob = f"{channel_ref or ''} {text}"
    if SALARY_REF.search(blob):
        return {
            "transaction_type": "income",
            "merchant_raw": "Salary",
            "payment_method": "neft",
            "is_transfer": False,
            "is_refund": False,
            "excludes_from_spending": True,  # income isn't spending
            "category_slug": "income",
            "subcategory_slug": "salary",
            "classification_source": "rule",
            "classification_confidence": 0.98,
            "classification_signals": {
                "rule": "axis_neft_sala_salary",
                "channel_ref": channel_ref,
            },
            "needs_review": False,
        }

    if re.search(r"\b(refund|reversal|chargeback|cashback)\b|/REFU\b", blob, re.I):
        return {
            "transaction_type": "refund",
            "is_transfer": False,
            "is_refund": True,
            "excludes_from_spending": False,
            "category_slug": "income",
            "subcategory_slug": "refund",
            "classification_source": "rule",
            "classification_confidence": 0.8,
            "classification_signals": {"rule": "axis_credit_refund_keyword", "channel_ref": channel_ref},
            "needs_review": True,
        }

    # Default Axis account credit → transfer / money movement, not income
    method = None
    if channel_ref:
        upper = channel_ref.upper()
        if upper.startswith("UPI"):
            method = "upi"
        elif upper.startswith("IMPS"):
            method = "imps"
        elif upper.startswith("NEFT"):
            method = "neft"
    # Prefer a readable counterparty from UPI/P2A/.../NAME/...
    merchant = channel_ref or "Account credit"
    if channel_ref and ("/P2A/" in channel_ref.upper() or "/P2M/" in channel_ref.upper()):
        parts = [p.strip() for p in channel_ref.split("/") if p.strip()]
        if len(parts) >= 3:
            merchant = parts[-1]
    return {
        "transaction_type": "transfer",
        "merchant_raw": merchant,
        "payment_method": method,
        "is_transfer": True,
        "is_refund": False,
        "excludes_from_spending": True,
        "category_slug": "transfers",
        "subcategory_slug": None,  # own-account vs P2A confirmed in review / learning
        "classification_source": "rule",
        "classification_confidence": 0.9,
        "classification_signals": {
            "rule": "axis_credit_non_salary_transfer",
            "channel_ref": channel_ref,
            "note": "Non-/Sala Axis credits treated as money movement, not income",
        },
        "needs_review": True,  # confirm own-account vs third-party until learned
    }


class AxisBankParser:
    name = "axis_bank_alerts"
    priority = 90

    def can_parse(self, email: EmailContext) -> float:
        sender = email.sender or ""
        subject = email.subject or ""
        if not AXIS_SENDER.search(sender):
            return 0.0
        text = combined_text(email.subject, email.body_text, email.body_html)
        if is_axis_declined_alert(subject, text):
            return 0.98
        if re.search(
            r"credit transaction alert|debit transaction alert|was credited|was debited|"
            r"credited with|Amount Credited|Amount Debited|spent on credit card",
            text,
            re.I,
        ):
            return 0.95
        if parse_amount(text):
            return 0.6
        return 0.0

    def parse(self, email: EmailContext) -> list[ParsedTransaction]:
        text = combined_text(email.subject, email.body_text, email.body_html)
        subject = email.subject or ""

        if is_axis_declined_alert(subject, text):
            amount = parse_amount(text)
            if amount is None or amount <= 0:
                return []
            tx_date = parse_date_near_amount(text, email.received_at)
            if tx_date is None:
                return []
            return [
                ParsedTransaction(
                    amount=amount,
                    currency="INR",
                    direction="debit",
                    transaction_date=tx_date,
                    transaction_type="not_a_transaction",
                    merchant_raw="Declined card attempt",
                    payment_method="card",
                    account=extract_account(text),
                    card=extract_card(text),
                    description=(subject[:500] or "Declined transaction"),
                    extra={
                        "parser": self.name,
                        "not_a_transaction": True,
                        "classification_source": "rule",
                        "classification_confidence": 1.0,
                        "classification_signals": {"rule": "axis_declined_transaction"},
                        "needs_review": False,
                        "is_transfer": False,
                        "is_refund": False,
                        "excludes_from_spending": True,
                    },
                )
            ]

        direction = "credit"
        amount: Decimal | None = None

        if re.search(r"credit transaction alert|was credited|Amount Credited|credited with", text, re.I):
            direction = "credit"
            for pat in (CREDITED_WITH, AMOUNT_CREDITED):
                m = pat.search(text)
                if m:
                    amount = Decimal(m.group(1).replace(",", ""))
                    break
        elif re.search(r"debit transaction alert|was debited|Amount Debited|debited with", text, re.I):
            direction = "debit"
            m = DEBITED_WITH.search(text)
            if m:
                amount = Decimal(m.group(1).replace(",", ""))
        elif re.search(r"spent on credit card", subject, re.I):
            direction = "debit"
            amount = parse_amount(text)

        if amount is None:
            amount = parse_amount(text)
        if amount is None or amount <= 0:
            return []

        tx_date = parse_date_near_amount(text, email.received_at)
        if tx_date is None:
            return []

        channel_ref = extract_axis_channel_ref(text)
        
        merchant_raw = None
        payment_method = "card" if "credit card" in subject.lower() else None

        if channel_ref and direction == "debit":
            upper_ref = channel_ref.upper()
            if upper_ref.startswith("UPI"):
                payment_method = "upi"
                parts = [p.strip() for p in channel_ref.split("/") if p.strip()]
                if len(parts) >= 3:
                    merchant_raw = parts[-1]
            elif "ACH-DR" in upper_ref or "ACH" in upper_ref:
                payment_method = "ach"
                if "RASMEC" in upper_ref:
                    merchant_raw = "ACH-DR-RASMEC KOMPALLY-NOD"
                else:
                    merchant_raw = channel_ref

        if not merchant_raw:
            merchant_raw = extract_axis_merchant(text)
            if not merchant_raw and email.body_html:
                merchant_raw = extract_axis_merchant(html_to_text(email.body_html))

        enrichment: dict = {
            "transaction_type": "purchase" if direction == "debit" else "other",
            "merchant_raw": merchant_raw,
            "payment_method": payment_method,
            "is_transfer": False,
            "is_refund": False,
            "excludes_from_spending": False,
            "classification_source": "unknown",
            "classification_confidence": 0.0,
            "classification_signals": {"parser": self.name},
            "needs_review": True,
        }

        if direction == "credit":
            enrichment.update(classify_axis_credit(channel_ref, text))
        elif "RASMEC" in text.upper() or (channel_ref and "RASMEC" in channel_ref.upper()):
            enrichment.update(
                {
                    "transaction_type": "purchase",
                    "merchant_raw": "ACH-DR-RASMEC KOMPALLY-NOD",
                    "payment_method": "ach",
                    "is_transfer": False,
                    "is_refund": False,
                    "excludes_from_spending": False,
                    "category_slug": "loans",
                    "subcategory_slug": "car",
                    "classification_source": "rule",
                    "classification_confidence": 0.95,
                    "classification_signals": {"rule": "axis_ach_rasmec_car_loan"},
                    "needs_review": False,
                }
            )
        elif re.search(r"credit.?card payment|by CreditCard|cc[- ]?payment", text, re.I):
            enrichment.update(
                {
                    "transaction_type": "transfer",
                    "merchant_raw": "Credit card payment",
                    "is_transfer": True,
                    "excludes_from_spending": True,
                    "category_slug": "transfers",
                    "subcategory_slug": "credit-card-payment",
                    "classification_source": "rule",
                    "classification_confidence": 0.92,
                    "classification_signals": {"rule": "axis_cc_payment"},
                    "needs_review": False,
                }
            )

        desc = subject[:500] if subject else None
        if channel_ref and (not desc or "Transaction Alert" in desc or "alert" in desc.lower()):
            desc = f"Transaction Info: {channel_ref}"

        upi_rrn_match = re.search(r"\b(\d{12})\b", channel_ref or "")
        upi_rrn = upi_rrn_match.group(1) if upi_rrn_match else None

        return [
            ParsedTransaction(
                amount=amount,
                currency="INR",
                direction=direction,
                transaction_date=tx_date,
                transaction_type=enrichment["transaction_type"],
                merchant_raw=enrichment.get("merchant_raw"),
                payment_method=enrichment.get("payment_method"),
                account=extract_account(text),
                card=extract_card(text),
                reference_number=channel_ref,
                bank_reference=channel_ref,
                description=desc,
                extra={
                    "parser": self.name,
                    "channel_ref": channel_ref,
                    "upi_rrn": upi_rrn,
                    **{
                        k: enrichment[k]
                        for k in enrichment
                        if k.startswith("classification")
                        or k.endswith("_slug")
                        or k
                        in {
                            "needs_review",
                            "is_transfer",
                            "is_refund",
                            "excludes_from_spending",
                        }
                    },
                },
            )
        ]
