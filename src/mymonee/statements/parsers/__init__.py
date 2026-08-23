"""Statement parsers package."""

from mymonee.statements.parsers.axis_bank import AxisBankParser
from mymonee.statements.parsers.axis_credit_card import AxisCreditCardParser
from mymonee.statements.parsers.base import (
    BaseStatementParser,
    ParsedStatementAccount,
    ParsedStatementResult,
    ParsedStatementSection,
    ParsedStatementSummary,
    ParsedStatementTransaction,
)
from mymonee.statements.parsers.registry import (
    StatementParserRegistry,
    get_statement_parser_registry,
)
from mymonee.statements.parsers.scapia import ScapiaParser

__all__ = [
    "AxisBankParser",
    "AxisCreditCardParser",
    "BaseStatementParser",
    "ParsedStatementAccount",
    "ParsedStatementResult",
    "ParsedStatementSection",
    "ParsedStatementSummary",
    "ParsedStatementTransaction",
    "ScapiaParser",
    "StatementParserRegistry",
    "get_statement_parser_registry",
]
