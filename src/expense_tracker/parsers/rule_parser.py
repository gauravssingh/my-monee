"""Provider-aware rule parser driven by YAML hints + shared extractors."""

from __future__ import annotations

from expense_tracker.ingestion.discovery import ProviderHint
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
    parse_amount,
    parse_date_near_amount,
)
from expense_tracker.parsers.generic import GenericHeuristicParser


class ProviderRuleParser:
    """Boosts confidence for known providers; extraction reuses generic heuristics."""

    def __init__(self, hint: ProviderHint) -> None:
        self.name = f"provider:{hint.name}"
        self.priority = hint.priority
        self._hint = hint
        self._fallback = GenericHeuristicParser()

    def can_parse(self, email: EmailContext) -> float:
        text = combined_text(email.subject, email.body_text, email.body_html)
        provider_score = self._hint.score(
            (email.sender or "").lower(),
            (email.subject or "").lower(),
            text.lower(),
        )
        if provider_score < 0.35:
            return 0.0
        if parse_amount(text) is None:
            return provider_score * 0.4
        return min(0.95, 0.55 + provider_score)

    def parse(self, email: EmailContext) -> list[ParsedTransaction]:
        parsed = self._fallback.parse(email)
        for item in parsed:
            item.extra = {**(item.extra or {}), "provider": self._hint.name, "parser": self.name}
            if not item.merchant_raw:
                item.merchant_raw = extract_merchant(
                    combined_text(email.subject, email.body_text, email.body_html)
                )
            if not item.reference_number:
                item.reference_number = extract_reference(
                    combined_text(email.subject, email.body_text, email.body_html)
                )
            if not item.card:
                item.card = extract_card(
                    combined_text(email.subject, email.body_text, email.body_html)
                )
            if not item.account:
                item.account = extract_account(
                    combined_text(email.subject, email.body_text, email.body_html)
                )
            if not item.upi_id:
                item.upi_id = extract_upi_id(
                    combined_text(email.subject, email.body_text, email.body_html)
                )
            text = combined_text(email.subject, email.body_text, email.body_html)
            item.direction = infer_direction(text)
            item.transaction_type = infer_transaction_type(text, item.direction)
            item.transaction_date = parse_date_near_amount(text, email.received_at) or item.transaction_date
        return parsed
