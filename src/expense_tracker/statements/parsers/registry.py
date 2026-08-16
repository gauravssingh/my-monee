"""Registry for deterministic statement parsers."""

from __future__ import annotations

import logging
from typing import Sequence

from expense_tracker.statements.extractor import PDFDocumentStructure, load_pdf_structure
from expense_tracker.statements.parsers.axis_bank import AxisBankParser
from expense_tracker.statements.parsers.axis_credit_card import AxisCreditCardParser
from expense_tracker.statements.parsers.base import BaseStatementParser, ParsedStatementResult
from expense_tracker.statements.parsers.scapia import ScapiaParser

logger = logging.getLogger(__name__)


class StatementParserRegistry:
    """Registry that manages statement parsers and selects the best matching parser."""

    def __init__(self, parsers: Sequence[BaseStatementParser] | None = None):
        if parsers is None:
            self._parsers: list[BaseStatementParser] = [
                ScapiaParser(),
                AxisBankParser(),
                AxisCreditCardParser(),
            ]
        else:
            self._parsers = list(parsers)

    def register(self, parser: BaseStatementParser) -> None:
        self._parsers.append(parser)

    def detect_and_parse(
        self, pdf_path_or_bytes: str | bytes, expected_issuer: str | None = None
    ) -> ParsedStatementResult:
        doc_struct = load_pdf_structure(pdf_path_or_bytes)
        best_parser: BaseStatementParser | None = None
        best_score = 0.0

        for p in self._parsers:
            score = p.can_parse(doc_struct)
            if expected_issuer and expected_issuer.upper() in p.institution.upper():
                score += 0.2
            if score > best_score:
                best_score = score
                best_parser = p

        if best_parser and best_score >= 0.4:
            logger.info(f"Selected parser '{best_parser.name}' with score {best_score:.2f}")
            result = best_parser.parse(doc_struct)
            result.confidence = best_score
            return result

        # Fallback / Generic parsing if no specific parser matched with high confidence
        logger.warning("No specific parser matched with high confidence; using generic Scapia/Axis fallback")
        if "axis" in doc_struct.full_text.lower():
            if "opening balance" in doc_struct.full_text.lower() or "money quotient" in doc_struct.full_text.lower():
                return AxisBankParser().parse(doc_struct)
            return AxisCreditCardParser().parse(doc_struct)

        return ScapiaParser().parse(doc_struct)


_default_registry = StatementParserRegistry()


def get_statement_parser_registry() -> StatementParserRegistry:
    return _default_registry
