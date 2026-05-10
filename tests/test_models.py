from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from vc_statement_parser.models import (
    CapitalAccountStatement,
    FieldSource,
    FundAdministrator,
    SourceMetadata,
    Transaction,
    TransactionType,
)


def test_field_source_requires_nonempty_text() -> None:
    with pytest.raises(ValidationError):
        FieldSource(page=1, source_text="")


def test_field_source_is_frozen() -> None:
    fs = FieldSource(page=1, source_text="abc")
    with pytest.raises(ValidationError):
        fs.page = 2  # type: ignore[misc]


def test_statement_is_frozen(passing_statement: CapitalAccountStatement) -> None:
    with pytest.raises(ValidationError):
        passing_statement.lp_name = "mutated"  # type: ignore[misc]


def test_statement_period_ordering() -> None:
    meta = SourceMetadata(
        administrator=FundAdministrator.UNKNOWN,
        extractor="test",
        parse_confidence=0.5,
    )
    with pytest.raises(ValidationError):
        CapitalAccountStatement(
            lp_name="x",
            fund_name="y",
            period_start=date(2024, 6, 30),
            period_end=date(2024, 3, 31),
            as_of_date=date(2024, 3, 31),
            commitment=Decimal("0"),
            paid_in_capital=Decimal("0"),
            unfunded_commitment=Decimal("0"),
            distributions=Decimal("0"),
            nav_beginning=Decimal("0"),
            contributions_period=Decimal("0"),
            distributions_period=Decimal("0"),
            nav_ending=Decimal("0"),
            realized_gain_loss=Decimal("0"),
            unrealized_gain_loss=Decimal("0"),
            management_fees=Decimal("0"),
            partnership_expenses=Decimal("0"),
            source_metadata=meta,
        )


def test_transaction_roundtrip() -> None:
    t = Transaction(
        transaction_date=date(2024, 1, 15),
        type=TransactionType.CONTRIBUTION,
        amount=Decimal("1500000.00"),
        description="Capital call #3",
    )
    assert t.type is TransactionType.CONTRIBUTION
    assert t.amount == Decimal("1500000.00")
