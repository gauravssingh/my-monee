"""Configurable email discovery rules (not sender-only)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from expense_tracker.config import providers_dir
from expense_tracker.ingestion.gmail.client import GmailMessage, is_excluded_recipient_headers


@dataclass
class ProviderHint:
    name: str
    priority: int = 50
    sender_patterns: list[re.Pattern[str]] = field(default_factory=list)
    subject_patterns: list[re.Pattern[str]] = field(default_factory=list)
    body_patterns: list[re.Pattern[str]] = field(default_factory=list)

    def score(self, sender: str, subject: str, body: str) -> float:
        score = 0.0
        if any(p.search(sender) for p in self.sender_patterns):
            score += 0.45
        if any(p.search(subject) for p in self.subject_patterns):
            score += 0.35
        if any(p.search(body) for p in self.body_patterns):
            score += 0.25
        return min(score, 1.0)


def is_excluded_recipient(message: GmailMessage | object) -> bool:
    """Check if the email recipient is explicitly an excluded address (e.g. gauravsingh86@gmail.com without dots)."""
    if hasattr(message, "is_excluded_recipient") and callable(message.is_excluded_recipient):
        return message.is_excluded_recipient()
    headers = getattr(message, "headers", None) or {}
    return is_excluded_recipient_headers(headers if isinstance(headers, dict) else None)


@dataclass
class DiscoveryRules:
    query_terms: list[str]
    include_subject_patterns: list[re.Pattern[str]]
    include_body_patterns: list[re.Pattern[str]]
    exclude_subject_patterns: list[re.Pattern[str]]
    exclude_sender_patterns: list[re.Pattern[str]]
    providers: list[ProviderHint] = field(default_factory=list)

    def build_gmail_query(self, *, after_date: str | None = None, newer_than_days: int | None = None) -> str:
        terms = [f'"{t}"' if " " in t else t for t in self.query_terms]
        # Prefer OR of distinctive finance terms; Gmail has query length limits so keep concise
        core = " OR ".join(terms[:12])
        parts = [f"({core})"]
        if after_date:
            parts.append(f"after:{after_date}")
        elif newer_than_days is not None:
            parts.append(f"newer_than:{newer_than_days}d")
        return " ".join(parts)

    def is_financial_candidate(self, message: GmailMessage | object) -> tuple[bool, str]:
        if is_excluded_recipient(message):
            return False, "excluded_recipient"

        sender = (getattr(message, "sender", None) or "").lower()
        subject = (getattr(message, "subject", None) or "").lower()
        body = (
            getattr(message, "body_text", None)
            or getattr(message, "snippet", None)
            or ""
        ).lower()

        for pattern in self.exclude_sender_patterns:
            if pattern.search(sender):
                return False, "excluded_sender"
        for pattern in self.exclude_subject_patterns:
            if pattern.search(subject):
                return False, "excluded_subject"

        subject_hit = any(p.search(subject) for p in self.include_subject_patterns)
        body_hit = any(p.search(body) for p in self.include_body_patterns)
        provider_hit = any(p.score(sender, subject, body) >= 0.35 for p in self.providers)

        if subject_hit or body_hit or provider_hit:
            reason = (
                "provider_hint"
                if provider_hit and not (subject_hit or body_hit)
                else "subject_or_body"
            )
            return True, reason
        return False, "no_financial_signal"

    def detect_provider(self, message: GmailMessage | object) -> tuple[str | None, float]:
        sender = (getattr(message, "sender", None) or "").lower()
        subject = (getattr(message, "subject", None) or "").lower()
        body = (getattr(message, "body_text", None) or "").lower()
        best_name: str | None = None
        best_score = 0.0
        for provider in sorted(self.providers, key=lambda p: p.priority, reverse=True):
            score = provider.score(sender, subject, body)
            if score > best_score:
                best_score = score
                best_name = provider.name
        if best_score < 0.35:
            return None, best_score
        return best_name, best_score


def _compile_list(patterns: list[str] | None) -> list[re.Pattern[str]]:
    return [re.compile(p, re.IGNORECASE) for p in (patterns or [])]


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data if isinstance(data, dict) else {}


def load_discovery_rules(directory: Path | None = None) -> DiscoveryRules:
    base_dir = directory or providers_dir()
    discovery_path = base_dir / "discovery.yaml"
    raw = _load_yaml(discovery_path) if discovery_path.exists() else {}

    providers: list[ProviderHint] = []
    for path in sorted(base_dir.glob("*.yaml")):
        if path.name == "discovery.yaml":
            continue
        pdata = _load_yaml(path)
        if not pdata.get("name"):
            continue
        providers.append(
            ProviderHint(
                name=str(pdata["name"]),
                priority=int(pdata.get("priority", 50)),
                sender_patterns=_compile_list(pdata.get("sender_patterns")),
                subject_patterns=_compile_list(pdata.get("subject_patterns")),
                body_patterns=_compile_list(pdata.get("body_patterns")),
            )
        )

    return DiscoveryRules(
        query_terms=list(raw.get("query_terms") or ["transaction", "debited", "UPI", "₹"]),
        include_subject_patterns=_compile_list(raw.get("include_subject_patterns")),
        include_body_patterns=_compile_list(raw.get("include_body_patterns")),
        exclude_subject_patterns=_compile_list(raw.get("exclude_subject_patterns")),
        exclude_sender_patterns=_compile_list(raw.get("exclude_sender_patterns")),
        providers=providers,
    )
