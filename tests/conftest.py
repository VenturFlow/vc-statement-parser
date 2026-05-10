"""Shared pytest fixtures."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

# Make `examples` importable as a package for the synthetic-PDF generator.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from examples.fixtures.generate import (  # noqa: E402
    StandishStatementInput,
    render_standish_pdf,
)

from vc_statement_parser.models import (  # noqa: E402
    CapitalAccountStatement,
    FundAdministrator,
    SourceMetadata,
)


@pytest.fixture(scope="session")
def standish_input() -> StandishStatementInput:
    return StandishStatementInput()


@pytest.fixture(scope="session")
def standish_pdf(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("fixtures") / "standish_synthetic.pdf"
    return render_standish_pdf(out)


@pytest.fixture()
def standish_pdf_per_test(tmp_path: Path) -> Iterator[Path]:
    out = tmp_path / "standish.pdf"
    render_standish_pdf(out)
    yield out


@pytest.fixture()
def passing_statement() -> CapitalAccountStatement:
    """A fully-populated statement that passes every invariant."""
    meta = SourceMetadata(
        administrator=FundAdministrator.STANDISH,
        extractor="test.fixture",
        parse_confidence=1.0,
        raw_text_excerpt="...",
        field_sources={},
    )
    nav_begin = Decimal("13400000.00")
    contributions = Decimal("1500000.00")
    distributions = Decimal("800000.00")
    realized = Decimal("250000.00")
    unrealized = Decimal("920000.00")
    mgmt = Decimal("125000.00")
    expenses = Decimal("45000.00")
    nav_end = nav_begin + contributions - distributions + realized + unrealized - mgmt - expenses
    paid_in = Decimal("12500000.00")
    unfunded = Decimal("12500000.00")
    cum_distributions = Decimal("4200000.00")
    return CapitalAccountStatement(
        lp_name="Acme University Endowment",
        fund_name="Vintage Capital Partners V, L.P.",
        period_start=date(2024, 1, 1),
        period_end=date(2024, 3, 31),
        as_of_date=date(2024, 3, 31),
        commitment=paid_in + unfunded,
        paid_in_capital=paid_in,
        unfunded_commitment=unfunded,
        distributions=cum_distributions,
        nav_beginning=nav_begin,
        contributions_period=contributions,
        distributions_period=distributions,
        nav_ending=nav_end,
        realized_gain_loss=realized,
        unrealized_gain_loss=unrealized,
        management_fees=mgmt,
        partnership_expenses=expenses,
        irr_net=Decimal("0.185"),
        tvpi_net=(nav_end + cum_distributions) / paid_in,
        dpi_net=cum_distributions / paid_in,
        transactions=[],
        source_metadata=meta,
    )
