"""End-to-end parse + verify against the synthetic Standish fixture."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from vc_statement_parser import parse_statement, verify
from vc_statement_parser.models import FundAdministrator, TransactionType
from vc_statement_parser.parse import NoExtractorAvailableError


def test_parse_synthetic_standish_pdf(standish_pdf: Path) -> None:
    statement = parse_statement(standish_pdf)
    assert statement.lp_name == "Acme University Endowment"
    assert statement.fund_name == "Vintage Capital Partners V, L.P."
    assert statement.period_start == date(2024, 1, 1)
    assert statement.period_end == date(2024, 3, 31)
    assert statement.commitment == Decimal("25000000.00")
    assert statement.paid_in_capital == Decimal("12500000.00")
    assert statement.unfunded_commitment == Decimal("12500000.00")
    assert statement.nav_beginning == Decimal("13400000.00")
    assert statement.nav_ending == Decimal("15100000.00")
    assert statement.source_metadata.administrator is FundAdministrator.STANDISH
    assert statement.source_metadata.extractor == "deterministic.standish"
    assert "nav_beginning" in statement.source_metadata.field_sources


def test_parse_then_verify_passes(standish_pdf: Path) -> None:
    statement = parse_statement(standish_pdf)
    report = verify(statement)
    assert report.passed, [r.name for r in report.failures]


def test_parse_picks_up_transactions(standish_pdf: Path) -> None:
    statement = parse_statement(standish_pdf)
    types = {t.type for t in statement.transactions}
    assert TransactionType.CONTRIBUTION in types
    assert TransactionType.DISTRIBUTION in types
    assert TransactionType.MANAGEMENT_FEE in types


def test_parse_accepts_bytes(standish_pdf: Path) -> None:
    statement = parse_statement(standish_pdf.read_bytes())
    assert statement.lp_name == "Acme University Endowment"


def test_parse_with_admin_hint(standish_pdf: Path) -> None:
    statement = parse_statement(standish_pdf, admin_hint="standish")
    assert statement.source_metadata.administrator is FundAdministrator.STANDISH


def test_unknown_admin_without_llm_raises(tmp_path: Path) -> None:
    # Build a PDF with no admin signature.
    from reportlab.pdfgen import canvas  # noqa: PLC0415  (lazy: optional [fixtures] extra)

    pdf_path = tmp_path / "blank.pdf"
    c = canvas.Canvas(str(pdf_path))
    c.drawString(72, 720, "An anonymous statement that no admin claims.")
    c.showPage()
    c.save()

    with pytest.raises(NoExtractorAvailableError):
        parse_statement(pdf_path, use_llm_fallback=False)
