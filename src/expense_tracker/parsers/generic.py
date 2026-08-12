"""Generic heuristic parser for transaction notification emails."""

from __future__ import annotations

from expense_tracker.parsers.base import EmailContext, ParsedTransaction
from expense_tracker.parsers.extract import (
    combined_text,
    extract_account,
    extract_card,
    extract_merchant,
    extract_reference,
    extract_upi_id,
    infer_direction,
    infer_transaction_type,
    parse_all_amounts,
    parse_date_near_amount,
)


class GenericHeuristicParser:
    name = "generic_heuristic"
    priority = 10

    def can_parse(self, email: EmailContext) -> float:
        text = combined_text(email.subject, email.body_text, email.body_html)
        amounts = parse_all_amounts(text)
        if not amounts:
            return 0.0
        directionish = infer_direction(text)
        score = 0.55
        if extract_reference(text):
            score += 0.15
        if extract_merchant(text):
            score += 0.1
        if directionish:
            score += 0.05
        return min(score, 0.85)

    def parse(self, email: EmailContext) -> list[ParsedTransaction]:
        text = combined_text(email.subject, email.body_text, email.body_html)
        amounts = parse_all_amounts(text)
        if not amounts:
            return []

        # Prefer the first typical notification amount (usually the transaction amount, not the balance)
        amount = amounts[0]
        direction = infer_direction(text)
        tx_type = infer_transaction_type(text, direction)
        tx_date = parse_date_near_amount(text, email.received_at)
        if tx_date is None:
            return []

        return [
            ParsedTransaction(
                amount=amount,
                currency="INR",
                direction=direction,
                transaction_date=tx_date,
                transaction_type=tx_type,
                merchant_raw=extract_merchant(text),
                payment_method="upi" if extract_upi_id(text) or "upi" in text.lower() else None,
                account=extract_account(text),
                card=extract_card(text),
                upi_id=extract_upi_id(text),
                reference_number=extract_reference(text),
                description=(email.subject or "")[:500] or None,
                extra={"parser": self.name, "amount_candidates": [str(a) for a in amounts]},
            )
        ]
