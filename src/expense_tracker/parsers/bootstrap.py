"""Register built-in parsers once at startup."""

from __future__ import annotations

import logging

from expense_tracker.ingestion.discovery import load_discovery_rules
from expense_tracker.parsers.axis import AxisBankParser
from expense_tracker.parsers.generic import GenericHeuristicParser
from expense_tracker.parsers.phonepe import PhonePeParser
from expense_tracker.parsers.registry import registry
from expense_tracker.parsers.rule_parser import ProviderRuleParser
from expense_tracker.parsers.scapia import ScapiaCardParser

logger = logging.getLogger(__name__)
_bootstrapped = False


def bootstrap_parsers(*, force: bool = False) -> None:
    global _bootstrapped
    if _bootstrapped and not force:
        return
    if force:
        registry._plugins = []
    registry.register(AxisBankParser())
    registry.register(ScapiaCardParser())
    registry.register(PhonePeParser())
    registry.register(GenericHeuristicParser())
    rules = load_discovery_rules()
    for hint in rules.providers:
        registry.register(ProviderRuleParser(hint))
    _bootstrapped = True
    logger.debug("Bootstrapped %d parser plugins: %s", len(registry._plugins), [p.name for p in registry._plugins])

