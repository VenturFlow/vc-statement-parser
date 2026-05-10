"""Detect the fund administrator from PDF header text and route to an extractor."""

from __future__ import annotations

import re

from .models import FundAdministrator

# Fund admins identify themselves at the top of every statement (letterhead, page 1
# title block, footer). Scanning the full document body produces false positives —
# e.g. an ILPA guidance PDF that lists "Citco / Gen II / SS&C" as example vendors
# would match every signature. Limit the search window to the first ~1500 chars
# (~30 lines, comfortably covering page 1 of any real statement).
_HEADER_REGION_CHARS = 1500

# Some administrators (notably GAAP_SCPC) have headings that legitimately
# appear in tables of contents, in cross-references in financial statements,
# and in page-running headers throughout an audit report. To avoid classifying
# such "mention-only" pages as the actual statement, we additionally require
# a data-row anchor on the same page. Anchors are only checked when a heading
# match has already fired, and they are scanned across the whole page (not
# just the header region) so a long page with a header at the top still
# qualifies.
_REQUIRED_DATA_ANCHORS: dict[FundAdministrator, re.Pattern[str]] = {}

_HEADER_SIGNATURES: dict[FundAdministrator, list[re.Pattern[str]]] = {
    FundAdministrator.STANDISH: [
        re.compile(r"\bStandish(?:\s+Fund\s+Services)?\b", re.IGNORECASE),
    ],
    FundAdministrator.GEN_II: [
        re.compile(r"\bGen\s*II(?:\s+Fund\s+Services)?\b", re.IGNORECASE),
    ],
    FundAdministrator.SSC: [
        re.compile(r"\bSS\s*&\s*C\b", re.IGNORECASE),
        re.compile(r"\bGeneva\b", re.IGNORECASE),
        re.compile(r"\bBlack\s*Diamond\b", re.IGNORECASE),
        re.compile(r"\bInvestran\b", re.IGNORECASE),
    ],
    FundAdministrator.CITCO: [
        re.compile(r"\bCitco\b", re.IGNORECASE),
    ],
    FundAdministrator.APEX: [
        re.compile(r"\bApex\s+(Fund|Group)\b", re.IGNORECASE),
    ],
    FundAdministrator.ALTER_DOMUS: [
        re.compile(r"\bAlter\s+Domus\b", re.IGNORECASE),
    ],
    # Generic GAAP "Statement of Changes in Partners' Capital" used by auditor
    # illustrative templates (KPMG, CohnReznick, ...) and by GPs producing
    # fund-level financials. The apostrophe varies (straight ', curly ', or absent).
    FundAdministrator.GAAP_SCPC: [
        re.compile(
            r"\bStatement\s+of\s+[Cc]hanges\s+in\s+[Pp]artners[’']?\s+[Cc]apital\b",  # noqa: RUF001  (curly apostrophe in real PDFs)
        ),
    ],
}

# GAAP_SCPC: the heading appears in TOCs, in cross-references inside Notes,
# and in page-running headers. Require ALSO a data row anchor — the literal
# "Partners' capital, beginning/end of year" text only appears on the actual
# statement page itself.
_REQUIRED_DATA_ANCHORS[FundAdministrator.GAAP_SCPC] = re.compile(
    r"Partners[’']?\s+capital,\s+(?:beginning|end)\s+of\s+year",  # noqa: RUF001
    re.IGNORECASE,
)

# Generic LP-PCAP data anchor for the LP-specific admin formats. Admin names
# like "Gen II", "Citco", "SS&C" etc. routinely appear in vendor lists,
# steering committees, and citations inside guidance / research documents
# (the ILPA Reporting Template Guidance PDF is the canonical example: page 6
# lists "Citco / Gen II / SS&C / State Street" under "Steering Committee").
# Without an additional "this page actually looks like a capital account
# statement" anchor, the dispatcher would happily classify those mentions as
# the corresponding admin. We require AT LEAST ONE of the following structural
# tokens that real statements contain but vendor-list documents don't:
#   - "Capital Account Statement"   (fund-admin section title)
#   - "Beginning Balance" / "Ending Balance"  (NAV roll line items)
#   - "Total Commitment"            (commitment summary line)
#   - "Paid-in Capital" / "Unfunded Commitment"
_PCAP_DATA_ANCHOR = re.compile(
    r"\b(?:"
    r"Capital\s+Account\s+Statement"
    r"|Beginning\s+Balance"
    r"|Ending\s+Balance"
    r"|Total\s+Commitment"
    r"|Paid-?in\s+Capital"
    r"|Unfunded\s+Commitment"
    r")\b",
    re.IGNORECASE,
)
for _admin in (
    FundAdministrator.STANDISH,
    FundAdministrator.GEN_II,
    FundAdministrator.SSC,
    FundAdministrator.CITCO,
    FundAdministrator.APEX,
    FundAdministrator.ALTER_DOMUS,
):
    _REQUIRED_DATA_ANCHORS[_admin] = _PCAP_DATA_ANCHOR


def detect_administrator(
    text: str,
    hint: str | None = None,
    *,
    per_page_text: list[str] | None = None,
) -> FundAdministrator:
    """Detect administrator from header text. Hint takes precedence if recognized.

    The hint is normalized (lowercased, spaces → underscores, "&" stripped) and
    matched against the `FundAdministrator` enum values. If no hint matches,
    falls back to scanning the header region for a known administrator
    signature. When `per_page_text` is supplied (recommended), the first
    `_HEADER_REGION_CHARS` of EACH page are scanned — this catches statements
    embedded on later pages of a longer report (e.g. a Statement of Changes in
    Partners' Capital on page 9 of an audited annual). Without it, only the
    first `_HEADER_REGION_CHARS` of the concatenated text are scanned.
    """
    if hint is not None:
        normalized = hint.lower().strip().replace(" ", "_").replace("&", "")
        try:
            return FundAdministrator(normalized)
        except ValueError:
            pass  # fall through to header-based detection

    pages: list[str] = list(per_page_text) if per_page_text is not None else [text]
    for page in pages:
        header = page[:_HEADER_REGION_CHARS]
        for admin, patterns in _HEADER_SIGNATURES.items():
            if not any(p.search(header) for p in patterns):
                continue
            anchor = _REQUIRED_DATA_ANCHORS.get(admin)
            # Anchor (when defined) is searched across the FULL page — the
            # heading and the data row are typically far apart on a long
            # statement page.
            if anchor is not None and not anchor.search(page):
                continue
            return admin

    return FundAdministrator.UNKNOWN
