"""vc-statement-parser — parse LP capital account statements into ILPA-aligned, verified JSON.

Public API:
    parse_statement(file, admin_hint=None) -> CapitalAccountStatement
    verify(statement, tolerance=...) -> ValidationReport
"""

from __future__ import annotations

from .models import (
    CapitalAccountStatement,
    FieldSource,
    FundAdministrator,
    SourceMetadata,
    Transaction,
    TransactionType,
)
from .parse import parse_statement
from .verification import InvariantResult, ValidationReport, verify

__all__ = [
    "CapitalAccountStatement",
    "FieldSource",
    "FundAdministrator",
    "InvariantResult",
    "SourceMetadata",
    "Transaction",
    "TransactionType",
    "ValidationReport",
    "parse_statement",
    "verify",
]

__version__ = "0.1.0"
