from __future__ import annotations

from decimal import Decimal

from vc_statement_parser.models import CapitalAccountStatement
from vc_statement_parser.verification import verify


def test_passing_statement_passes_every_invariant(
    passing_statement: CapitalAccountStatement,
) -> None:
    report = verify(passing_statement)
    assert report.passed
    assert bool(report) is True
    names = {r.name for r in report.results}
    assert {
        "nav_roll_forward",
        "commitment_identity",
        "tvpi_consistency",
        "dpi_consistency",
    } <= names
    assert report.failures == ()


def test_nav_roll_forward_failure(passing_statement: CapitalAccountStatement) -> None:
    bad = passing_statement.model_copy(
        update={"nav_ending": passing_statement.nav_ending + Decimal("1000")}
    )
    report = verify(bad)
    assert not report.passed
    nav_check = next(r for r in report.results if r.name == "nav_roll_forward")
    assert not nav_check.passed
    assert nav_check.delta == Decimal("1000")


def test_commitment_identity_failure(passing_statement: CapitalAccountStatement) -> None:
    bad = passing_statement.model_copy(
        update={"commitment": passing_statement.commitment + Decimal("100")}
    )
    report = verify(bad)
    failure_names = {r.name for r in report.failures}
    assert "commitment_identity" in failure_names


def test_tvpi_inconsistency_flagged(passing_statement: CapitalAccountStatement) -> None:
    bad = passing_statement.model_copy(update={"tvpi_net": Decimal("3.50")})
    report = verify(bad)
    failure_names = {r.name for r in report.failures}
    assert "tvpi_consistency" in failure_names


def test_skips_ratio_checks_when_metric_missing(passing_statement: CapitalAccountStatement) -> None:
    bad = passing_statement.model_copy(update={"tvpi_net": None, "dpi_net": None})
    report = verify(bad)
    names = {r.name for r in report.results}
    assert "tvpi_consistency" not in names
    assert "dpi_consistency" not in names
    assert report.passed


def test_tolerance_respected(passing_statement: CapitalAccountStatement) -> None:
    # Within $1 tolerance — should still pass.
    nudged = passing_statement.model_copy(
        update={"nav_ending": passing_statement.nav_ending + Decimal("0.50")}
    )
    assert verify(nudged).passed
