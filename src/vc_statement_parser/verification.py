"""Arithmetic-invariant verification — the wedge.

Capital account statements are loaded with redundant arithmetic: opening balance
plus period activity must equal closing balance; commitment must equal paid-in
plus unfunded; TVPI must equal (NAV + cumulative distributions) / paid-in.

A statement that *looks* correct but fails one of these is either misprinted or
mis-extracted. This module surfaces every failure with the exact delta and
tolerance, so a downstream system can flag it for human review rather than
silently consuming bad data.

Tolerance is in absolute dollars for currency identities and in raw multiple
units for ratio identities. Defaults are conservative; tighten per workflow.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .models import CapitalAccountStatement

DEFAULT_DOLLAR_TOLERANCE = Decimal("1.00")  # $1 absolute delta
DEFAULT_RATIO_TOLERANCE = Decimal("0.05")  # 5 bps on TVPI/DPI multiples


@dataclass(frozen=True)
class InvariantResult:
    """One arithmetic check: did expected ≈ actual within tolerance?"""

    name: str
    description: str
    expected: Decimal
    actual: Decimal
    delta: Decimal
    tolerance: Decimal
    passed: bool


@dataclass(frozen=True)
class ValidationReport:
    """Aggregated invariant results for one statement."""

    results: tuple[InvariantResult, ...]

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.results)

    @property
    def failures(self) -> tuple[InvariantResult, ...]:
        return tuple(r for r in self.results if not r.passed)

    def __bool__(self) -> bool:
        return self.passed


def _check(
    name: str,
    description: str,
    expected: Decimal,
    actual: Decimal,
    tolerance: Decimal,
) -> InvariantResult:
    delta = actual - expected
    return InvariantResult(
        name=name,
        description=description,
        expected=expected,
        actual=actual,
        delta=delta,
        tolerance=tolerance,
        passed=abs(delta) <= tolerance,
    )


def verify(
    statement: CapitalAccountStatement,
    *,
    dollar_tolerance: Decimal = DEFAULT_DOLLAR_TOLERANCE,
    ratio_tolerance: Decimal = DEFAULT_RATIO_TOLERANCE,
) -> ValidationReport:
    """Run every applicable invariant against `statement` and return the report.

    Invariants are skipped when their inputs are missing rather than failing —
    a fund-level GAAP Statement of Changes in Partners' Capital, for example,
    legitimately lacks management_fees / partnership_expenses (which live on a
    separate Statement of Operations page) and lacks the LP-level commitment
    identity inputs entirely.
    """
    results: list[InvariantResult] = []

    # 1) NAV roll-forward:
    # nav_beginning + contributions - distributions + realized + unrealized
    #   - management_fees - partnership_expenses == nav_ending
    # Requires fees + expenses; skip if either is unknown.
    if statement.management_fees is not None and statement.partnership_expenses is not None:
        expected_nav_end = (
            statement.nav_beginning
            + statement.contributions_period
            - statement.distributions_period
            + statement.realized_gain_loss
            + statement.unrealized_gain_loss
            - statement.management_fees
            - statement.partnership_expenses
        )
        results.append(
            _check(
                name="nav_roll_forward",
                description=(
                    "NAV_begin + contributions - distributions + realized + unrealized "
                    "- management_fees - partnership_expenses == NAV_end"
                ),
                expected=expected_nav_end,
                actual=statement.nav_ending,
                tolerance=dollar_tolerance,
            )
        )

    # 2) Commitment identity: paid_in + unfunded == commitment
    if (
        statement.commitment is not None
        and statement.paid_in_capital is not None
        and statement.unfunded_commitment is not None
    ):
        results.append(
            _check(
                name="commitment_identity",
                description="paid_in_capital + unfunded_commitment == commitment",
                expected=statement.paid_in_capital + statement.unfunded_commitment,
                actual=statement.commitment,
                tolerance=dollar_tolerance,
            )
        )

    # 3) TVPI: (NAV_end + cumulative_distributions) / paid_in
    if (
        statement.tvpi_net is not None
        and statement.paid_in_capital is not None
        and statement.paid_in_capital > 0
        and statement.distributions is not None
    ):
        expected_tvpi = (statement.nav_ending + statement.distributions) / statement.paid_in_capital
        results.append(
            _check(
                name="tvpi_consistency",
                description="tvpi_net == (NAV_end + cumulative_distributions) / paid_in_capital",
                expected=expected_tvpi,
                actual=statement.tvpi_net,
                tolerance=ratio_tolerance,
            )
        )

    # 4) DPI: cumulative_distributions / paid_in
    if (
        statement.dpi_net is not None
        and statement.paid_in_capital is not None
        and statement.paid_in_capital > 0
        and statement.distributions is not None
    ):
        expected_dpi = statement.distributions / statement.paid_in_capital
        results.append(
            _check(
                name="dpi_consistency",
                description="dpi_net == cumulative_distributions / paid_in_capital",
                expected=expected_dpi,
                actual=statement.dpi_net,
                tolerance=ratio_tolerance,
            )
        )

    return ValidationReport(results=tuple(results))
