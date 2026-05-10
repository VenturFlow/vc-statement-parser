from __future__ import annotations

import pytest

from vc_statement_parser.dispatcher import detect_administrator
from vc_statement_parser.models import FundAdministrator

# Each fixture is a header that includes BOTH the admin signature AND a
# PCAP data anchor (e.g. "Capital Account Statement", "Beginning Balance",
# "Total Commitment") — the dispatcher requires both, otherwise a vendor-
# list mention or a research-paper citation would falsely match.
_PCAP = "Capital Account Statement\nTotal Commitment: $25,000,000"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (f"STANDISH FUND SERVICES\n{_PCAP}", FundAdministrator.STANDISH),
        (f"Issued by Gen II Fund Services LLC\n{_PCAP}", FundAdministrator.GEN_II),
        (f"Powered by SS&C Geneva\n{_PCAP}", FundAdministrator.SSC),
        (f"Black Diamond Wealth Platform\n{_PCAP}", FundAdministrator.SSC),
        (f"Citco Fund Services (USA) Inc.\n{_PCAP}", FundAdministrator.CITCO),
        (f"Apex Group Ltd.\n{_PCAP}", FundAdministrator.APEX),
        (f"Alter Domus US LLC\n{_PCAP}", FundAdministrator.ALTER_DOMUS),
        (f"Generic Fund Admin Co.\n{_PCAP}", FundAdministrator.UNKNOWN),
    ],
)
def test_header_signature_detection(text: str, expected: FundAdministrator) -> None:
    assert detect_administrator(text) is expected


def test_hint_overrides_text() -> None:
    # Text says Citco but the user explicitly hints Standish — hint wins.
    # No PCAP anchor needed when a hint is supplied.
    assert (
        detect_administrator("Citco Fund Services", hint="standish") is FundAdministrator.STANDISH
    )


def test_unknown_hint_falls_through_to_text() -> None:
    # When the hint is unrecognised AND the text has both the signature AND
    # a PCAP anchor, header-detection still fires.
    assert (
        detect_administrator(f"Citco Fund Services\n{_PCAP}", hint="not-a-real-admin")
        is FundAdministrator.CITCO
    )


def test_hint_normalization() -> None:
    assert detect_administrator("", hint="Gen II") is FundAdministrator.GEN_II
    assert detect_administrator("", hint="alter domus") is FundAdministrator.ALTER_DOMUS


def test_admin_name_in_body_does_not_false_positive() -> None:
    """Admin names appearing past the header region must not match.

    Regression for a bug discovered when running the parser against the public
    ILPA Reporting Template Guidance PDF — the body of the document lists "Citco
    / Gen II / SS&C" as example vendors, which used to falsely flag the document
    as a Gen II statement.
    """
    # 2 KB of unrelated header text, then a vendor list deep in the body.
    preamble = "ILPA Reporting Template Guidance\n" + ("filler line " * 200) + "\n"
    body = "Citco Fund Administrator Gen II Fund Administrator SS&C Fund Administrator"
    assert detect_administrator(preamble + body) is FundAdministrator.UNKNOWN


def test_real_ilpa_guidance_text_does_not_false_positive() -> None:
    """Excerpt taken from the actual ILPA v1.1 guidance PDF (page 6 vendor list).

    The vendor list ("Citco / Gen II / SS&C") appears on page 6 of the actual PDF,
    well past any reasonable header region. The synthetic preamble below pads to
    >1500 chars to mirror that.
    """
    # Pad with realistic-looking guidance prose so the vendor list ends up past the
    # 1500-char header window.
    preamble_paragraph = (
        "The ILPA Reporting Template was developed to promote uniform reporting "
        "practices in the private equity industry as part of the Transparency "
        "Initiative. The Template details monies paid to the fund manager, "
        "affiliates, and third parties, and reflects feedback from over 120 "
        "individuals and organizations including LP groups, GPs, trade bodies, "
        "consultants, advisors, fund administrators, and accountants.\n"
    )
    text = (
        "ILPA Reporting Template Guidance (Version 1.1)\n"
        "Overview\n"
        + (preamble_paragraph * 5)
        + "VII. Template Endorsement\n"
        + (preamble_paragraph * 5)
        + "Certares GP Reverence Capital GP Citco Fund Administrator "
        "Gen II Fund Administator SEI Fund Administrator SS&C Fund Administrator"
    )
    assert len(text) > 1500, "test fixture must exceed header window"
    assert detect_administrator(text) is FundAdministrator.UNKNOWN


def test_gaap_scpc_signature_detected() -> None:
    """Auditor-style fund-level statements (KPMG, CohnReznick) match GAAP_SCPC.

    The dispatcher requires BOTH the heading AND the data-row anchor on the
    same page — see test_gaap_scpc_toc_only_does_not_match below.
    """
    # Curly apostrophe (KPMG style) - test fixture intentionally uses real Unicode.
    kpmg_style = (
        "Private Equity, L.P.\n"
        "Statement of changes in partners’ capital\n"  # noqa: RUF001
        "Year ended December 31, 20XX\n"
        "Partners’ capital, beginning of year $75,884,000 $682,957,000 $758,841,000\n"  # noqa: RUF001
    )
    assert detect_administrator(kpmg_style) is FundAdministrator.GAAP_SCPC


def test_gaap_scpc_toc_only_does_not_match() -> None:
    """A table-of-contents page that merely lists 'Statement of Changes in
    Partners' Capital' as a section heading must NOT be classified as GAAP_SCPC.

    Regression for the CohnReznick-style 29-page audit report where the SCPC
    heading appears on the TOC, on every page header, and only ONCE alongside
    the actual data — only the actual data page should match.
    """
    toc_page = (
        "INDEX\n"
        "Page\n"
        "Statement of Assets and Liabilities 3\n"
        "Schedule of Investments 4\n"
        "Statement of Operations 5\n"
        "Statement of Changes in Partners' Capital 6\n"
        "Statement of Cash Flows 7\n"
    )
    other_page = "ASC 820-10 fair value disclosure unrelated content."
    assert (
        detect_administrator(
            toc_page + "\n" + other_page,
            per_page_text=[toc_page, other_page],
        )
        is FundAdministrator.UNKNOWN
    )


def test_admin_name_in_vendor_list_does_not_match_without_pcap_anchor() -> None:
    """Regression for a real bug: the ILPA Reporting Template Guidance v2 PDF
    has "Gen II" inside a Steering Committee vendor list at char 600 of page 6
    — well within the 1500-char header window. Restricting the window alone
    isn't enough; we also require an LP-PCAP data anchor (e.g. "Capital
    Account Statement" / "Beginning Balance" / "Total Commitment") to confirm
    the page actually IS a statement, not a citation.
    """
    # Excerpted from the actual page-6 layout of the ILPA v2 guidance PDF.
    page = (
        "Reporting Template Guidance | 6\n"
        "Steering Committee\n"
        "ORGANIZATION ORGANIZATION TYPE\n"
        "CalPERS LP\n"
        "CDPQ LP\n"
        "Commonwealth of Pennsylvania Public School LP\n"
        "State of Wisconsin Investment Board LP\n"
        "Teacher Retirement System of Texas LP\n"
        "Certares GP\n"
        "Reverence Capital GP\n"
        "Citco Fund Administrator\n"
        "Gen II Fund Administator\n"
        "SEI Fund Administrator\n"
        "SS&C Fund Administrator\n"
        "State Street Fund Administrator\n"
    )
    assert detect_administrator(page, per_page_text=[page]) is FundAdministrator.UNKNOWN


def test_real_pcap_admin_still_matches_with_anchor() -> None:
    """Confirm the new PCAP-anchor requirement doesn't break legit statements.

    Any of the structural tokens — "Capital Account Statement", "Beginning
    Balance", "Total Commitment" — should be enough alongside the admin name.
    """
    page = (
        "STANDISH FUND SERVICES\n"
        "Capital Account Statement\n"
        "Limited Partner: Acme Endowment\n"
        "Total Commitment: $25,000,000\n"
    )
    assert detect_administrator(page, per_page_text=[page]) is FundAdministrator.STANDISH


def test_gaap_scpc_matches_real_statement_page_among_many() -> None:
    """Confirm the dispatcher picks the correct page in a multi-page document."""
    toc_page = "INDEX\nStatement of Changes in Partners' Capital 6\n"
    other_page = "Some unrelated balance sheet content with numbers."
    real_scpc_page = (
        "Private Equity Fund, L.P.\n"
        "Statement of Changes in Partners' Capital\n"
        "Year Ended December 31, 20XX\n"
        "Partners' capital, beginning of year $4,900,000 $71,381,000 $76,281,000\n"
        "Capital contributions 2,000 918,000 920,000\n"
    )
    assert (
        detect_administrator(
            toc_page + other_page + real_scpc_page,
            per_page_text=[toc_page, other_page, real_scpc_page],
        )
        is FundAdministrator.GAAP_SCPC
    )
