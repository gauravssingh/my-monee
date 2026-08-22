"""Scapia Federal Credit Card purchase alert parser."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from expense_tracker.parsers.base import EmailContext, ParsedTransaction
from expense_tracker.parsers.extract import combined_text, html_to_text, parse_date_near_amount

SENDER_HINT = re.compile(r"scapia|scapiacards@federalbank\.co\.in", re.I)
SUBJECT_HINT = re.compile(r"transaction was successful|refund|payment", re.I)
# Scapia bodies often insert HTML entities / zero-width spaces between labels.
AMOUNT_LABEL = re.compile(
    r"Amount\b(?:.|\n){0,40}?₹\s*([0-9,]+\.?[0-9]*)",
    re.I,
)
MERCHANT_LABEL = re.compile(
    r"Merchant\b(?:.|\n){0,20}?([A-Za-z0-9][^\n\r]{1,80})",
    re.I,
)
CARD_ENDING = re.compile(r"card ending in\s*(\d{4})", re.I)
ENTITY_OR_ZW = re.compile(r"&#\d+;|&#x[0-9a-f]+;|[\u200b\u200c\u200d\u2009\u200a\ufeff]", re.I)


def _scapia_text(email: EmailContext) -> str:
    if email.body_html:
        raw = combined_text(email.subject, html_to_text(email.body_html), None)
    else:
        raw = combined_text(email.subject, email.body_text, email.body_html)
    return ENTITY_OR_ZW.sub(" ", raw)


class ScapiaCardParser:
    name = "scapia_federal_card"
    priority = 95

    def can_parse(self, email: EmailContext) -> float:
        sender = email.sender or ""
        subject = email.subject or ""
        if re.search(r"statements@|cc\.statements@", sender, re.I) or "statement" in subject.lower():
            return 0.0  # Handled exclusively by Statement Vault, never as raw email txs
        if not SENDER_HINT.search(sender) and not SENDER_HINT.search(subject):
            text = _scapia_text(email)
            if not SENDER_HINT.search(text):
                return 0.0
        if SUBJECT_HINT.search(subject):
            return 0.95
        return 0.75

    def parse(self, email: EmailContext) -> list[ParsedTransaction]:
        text = _scapia_text(email)

        amount_match = AMOUNT_LABEL.search(text)
        if not amount_match:
            return []
        try:
            amount = Decimal(amount_match.group(1).replace(",", ""))
        except InvalidOperation:
            return []
        if amount <= 0:
            return []

        tx_date = parse_date_near_amount(text, email.received_at)
        if tx_date is None:
            return []

        card = None
        card_match = CARD_ENDING.search(text)
        if card_match:
            card = card_match.group(1)

        is_bill_payment = bool(
            re.search(
                r"\b(?:credit\s*card\s*bill\s*payment|bill\s*payment\s*successful|received your credit card bill payment|payment received towards your (?:scapia|federal|credit card))\b",
                text,
                re.I,
            )
        )
        if is_bill_payment:
            return [
                ParsedTransaction(
                    amount=amount,
                    currency="INR",
                    direction="credit",
                    transaction_date=tx_date,
                    transaction_type="transfer",
                    merchant_raw="Credit card payment",
                    payment_method="upi" if "upi" in text.lower() else "transfer",
                    card=card,
                    description=(email.subject or "Scapia bill payment")[:500],
                    extra={
                        "parser": self.name,
                        "classification_source": "rule",
                        "classification_confidence": 0.95,
                        "classification_signals": {
                            "rule": "scapia_card_bill_payment",
                            "sender": email.sender,
                        },
                        "needs_review": False,
                        "is_transfer": True,
                        "is_refund": False,
                        "excludes_from_spending": True,
                        "category_slug": "transfers",
                        "subcategory_slug": "credit-card-payment",
                    },
                )
            ]

        merchant = None
        merchant_match = MERCHANT_LABEL.search(text)
        if merchant_match:
            merchant = re.sub(r"\s+", " ", merchant_match.group(1)).strip(" .-")
            merchant = re.sub(
                r"\s+(Not you\?|Support on the Scapia|Head to Support).*$",
                "",
                merchant,
                flags=re.I,
            ).strip(" .-")
            if len(merchant) < 2 or re.search(r"support on the scapia|call\s*1800", merchant, re.I):
                merchant = None

        is_refund = bool(re.search(r"\brefund", text, re.I))
        direction = "credit" if is_refund else "debit"
        tx_type = "refund" if is_refund else "purchase"

        return [
            ParsedTransaction(
                amount=amount,
                currency="INR",
                direction=direction,
                transaction_date=tx_date,
                transaction_type=tx_type,
                merchant_raw=merchant,
                payment_method="card",
                card=card,
                description=(email.subject or "Scapia card transaction")[:500],
                extra={
                    "parser": self.name,
                    "classification_source": "rule",
                    "classification_confidence": 0.9,
                    "classification_signals": {
                        "rule": "scapia_card_refund" if is_refund else "scapia_card_purchase",
                        "sender": email.sender,
                    },
                    "needs_review": merchant is None,
                    "is_refund": is_refund,
                    "excludes_from_spending": is_refund,
                },
            )
        ]
