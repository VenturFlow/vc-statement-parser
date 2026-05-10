"""Deterministic extractor for fund-level GAAP "Statement of Changes in Partners' Capital".

This format is what auditors (KPMG, CohnReznick, Deloitte, EY, PwC) ship in their
illustrative financial statements, and what GPs produce as their audited fund-level
year-end financials. It is *not* an LP-specific PCAP — there is one row of figures
broken across three columns (General Partner | Limited Partners | Total). We
extract the Limited Partners column and treat it as an aggregate-LP capital account.

Layout (mildly stylised — actual statements include ASC reference codes in margin):

    Private Equity, L.P.
    Statement of changes in partners' capital
    Year ended December 31, 20XX

                                          General Partner   Limited Partners    Total
    Partners' capital, beginning of year      $75,884,000       $682,957,000   $758,841,000
    Capital contributions                         250,000         24,750,000     25,000,000
    Capital distributions                        (373,000)       (36,888,000)   (37,261,000)
    Net investment loss                           (31,000)        (3,147,000)    (3,178,000)
    Net realized gain from investments            251,000         24,914,000     25,165,000
    Realized gain on distribution of                2,000            198,000        200,000
       investments
    Net unrealized gain from investments          173,000         17,100,000     17,273,000
    Net realized gain from foreign currency         4,000            396,000        400,000
       transactions
    Net unrealized gain from translation
       of assets and liabilities in                8,000            792,000        800,000
       foreign currencies
    Carried interest to general partner         8,051,000         (8,051,000)            —
    Partners' capital, end of year            $84,219,000       $703,021,000   $787,240,000

Notable quirks handled:
  * Multi-line labels — the value row may sit on the second or third line of a
    wrapped label.
  * CohnReznick PDFs split leading digits with whitespace ("$ 4 ,900,000") because
    of how reportlab kerns the dollar sign; we normalise these before parsing.
  * Em dash "—" used as a zero placeholder.
  * Placeholder year "20XX" used in illustrative templates — we substitute 2099
    so the resulting `CapitalAccountStatement` is well-formed without conflating
    illustrative data with a real reporting year.

Field mapping into the LP-PCAP model (the model has many fields the SCPC simply
doesn't carry, which is why those fields are now Optional):

  nav_beginning              ← "Partners' capital, beginning of year"
  contributions_period       ← "Capital contributions"
  distributions_period       ← abs("Capital distributions")
  realized_gain_loss         ← Σ(realized-gain rows: investments + distribution
                                 of investments + foreign currency)
  unrealized_gain_loss       ← Σ(unrealized-gain rows: investments + translation
                                 of assets and liabilities)
  partnership_expenses       ← abs("Net investment loss") + abs("Carried interest
                                 to general partner")  — we bundle the two LP-side
                                 deductions here so `nav_roll_forward` balances.
  management_fees            ← Decimal("0")  — fees are commingled into "Net
                                 investment loss" on this format and can't be
                                 separated; explicit zero means the invariant runs.
  nav_ending                 ← "Partners' capital, end of year"
  commitment / paid_in / unfunded / cumulative distributions / IRR / TVPI / DPI
                             ← None  (not present in fund-level SCPC)

Source provenance: every numeric row records the line of source text it came
from in `source_metadata.field_sources`.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from ..models import (
    CapitalAccountStatement,
    FieldSource,
    FundAdministrator,
    SourceMetadata,
)
from .base import Extractor

# Match a money cell. Accepts:
#   $84,219,000      $84,219,000.00     (373,000)     —     -    8,051,000
# The leading $ is optional; parens denote a negative; em/en/hyphen-only token = 0.
_MONEY_RE = (
    # Allow $ to appear EITHER before the leading paren ("$(120,000)") or
    # inside ("($120,000)") — both forms are common in real statements.
    r"\$?\(?\s*-?\s*\$?\s*(?:[—–\-]|\d[\d,]*(?:\.\d{1,2})?)\s*\)?"  # noqa: RUF001
)

# A row that ends in three money cells (GP | LP | Total). The label is whatever
# comes before. We allow an arbitrarily-long label so multi-line wrapped labels
# (where the values land on the continuation line) still match — the previous
# line's prefix gets attached during post-processing.
_THREE_COL_RE = re.compile(
    rf"(?P<label>.+?)\s+(?P<gp>{_MONEY_RE})\s+(?P<lp>{_MONEY_RE})\s+(?P<total>{_MONEY_RE})\s*$",
)

# Line that *does not* end in three money cells. Used to attach to a following
# 3-col row as a label prefix when the label has wrapped.
_NO_VALUES_RE = re.compile(rf"^(?:(?!{_MONEY_RE}\s*$).)*$")

# Only one canonical year per illustrative document; we substitute 20XX → 2099.
_PERIOD_RE = re.compile(
    r"Year\s+[Ee]nded\s+(?P<month>[A-Za-z]+)\s+(?P<day>\d{1,2}),?\s+(?P<year>\d{4}|20XX)",
)

_FUND_NAME_RE = re.compile(r"^(?P<name>[^\n]+,\s*L\.?P\.?)\s*$", re.MULTILINE)

# The SCPC heading appears in multiple places (table of contents, the actual
# statement page, page-running headers). The actual statement page is the one
# that ALSO contains the data row "Partners' capital, beginning of year".
_SCPC_HEADING_RE = re.compile(
    r"Statement\s+of\s+[Cc]hanges\s+in\s+[Pp]artners[’']?\s+[Cc]apital",  # noqa: RUF001  (curly apostrophe used by KPMG)
)
_SCPC_DATA_ROW_RE = re.compile(
    r"Partners[’']?\s+capital,\s+beginning\s+of\s+year",  # noqa: RUF001
    re.IGNORECASE,
)

# Canonical line-item categories for SCPC layouts. Each category lists keyword
# patterns we expect to find in the row label (case-insensitive substring match
# is sufficient — labels are stable across auditor templates).
_CATEGORY_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "nav_beginning": (
        re.compile(r"partners[’'].*?capital.*?beginning", re.IGNORECASE | re.DOTALL),  # noqa: RUF001
    ),
    "nav_ending": (
        re.compile(r"partners[’'].*?capital.*?end\s+of\s+year", re.IGNORECASE | re.DOTALL),  # noqa: RUF001
    ),
    "contributions_period": (re.compile(r"\bcapital\s+contributions\b", re.IGNORECASE),),
    "distributions_period": (re.compile(r"\bcapital\s+distributions\b", re.IGNORECASE),),
    "realized_gain_loss": (
        re.compile(r"\bnet\s+realized\s+gain", re.IGNORECASE),
        re.compile(r"\brealized\s+gain\s+on\s+distribution", re.IGNORECASE),
        # CohnReznick's compact format collapses ALL of net income (realized +
        # unrealized + investment income/loss) into a single "Pro rata
        # allocation" line. Bucket it into realized_gain_loss so the NAV
        # roll-forward identity still balances; documented in the parser.
        re.compile(r"\bpro\s+rata\s+allocation\b", re.IGNORECASE),
    ),
    "unrealized_gain_loss": (
        re.compile(r"\bnet\s+unrealized\s+gain", re.IGNORECASE),
        re.compile(r"\bunrealized\s+gain\s+from\s+translation", re.IGNORECASE),
    ),
    "partnership_expenses": (
        re.compile(r"\bnet\s+investment\s+loss\b", re.IGNORECASE),
        re.compile(r"\bcarried\s+interest\s+to\s+general\s+partner\b", re.IGNORECASE),
    ),
}

# Categories we sum across multiple rows (vs. take the single matched value).
_SUMMING_CATEGORIES = frozenset(
    {"realized_gain_loss", "unrealized_gain_loss", "partnership_expenses"}
)

# Categories whose extracted magnitude should be coerced to a positive value
# (the sign is implied by the verification identity, ILPA-aligned).
_POSITIVE_MAGNITUDE_CATEGORIES = frozenset(
    {"contributions_period", "distributions_period", "partnership_expenses"}
)


def _normalize_text(text: str) -> str:
    r"""Patch up common PDF-extraction whitespace bugs.

    Two distinct bugs are observed across auditor templates:

    1. Reportlab-generated PDFs (CohnReznick) insert stray spaces around the
       leading digit: "$ 4 ,900,000" or "9 18,000" must become "$4,900,000" /
       "918,000".

    2. Tightly-kerned multi-column tables (KPMG) drop the whitespace BETWEEN
       adjacent money cells, producing "250,00024,750,00025,000,000" as the
       three-column row. We re-insert the missing space at every "end of one
       number, start of next number" boundary by spotting `,\d{3}` immediately
       followed by what looks like the start of a new thousands-separated
       number (`\d{1,3},\d{3}`).
    """
    # Bug 0 (reportlab tightly-spaced columns): a label letter immediately
    # followed by a money token's leading "$" or digit ("transactions$1,000")
    # gets a space inserted so the row regex can find a `\s+` boundary.
    text = re.sub(r"([A-Za-z])(\$|\(\$|\(\d)", r"\1 \2", text)
    # Bug 1 (CohnReznick): "$ 1,234" → "$1,234"
    text = re.sub(r"\$\s+(\d)", r"$\1", text)
    # Bug 1 (CohnReznick): "1 ,234" → "1,234"
    text = re.sub(r"(\d)\s+,", r"\1,", text)
    # Bug 1 (CohnReznick): "1 23,456" → "123,456"  (handles 2-digit prefix)
    text = re.sub(r"(\d)\s+(\d{2},\d{3})", r"\1\2", text)
    # Bug 1 (CohnReznick): "1 2,132,000" → "12,132,000"  (stray leading digit
    # before a number that itself starts with 1-3 digits + comma). Anchored to
    # ONLY fire when preceded by the end of a previous number ("...,XYZ ") so
    # we don't accidentally merge a label digit into a value.
    text = re.sub(
        r"(?<=,\d{3}\s)(\d{1,2})\s+(\d{1,3},\d{3})",
        r"\1\2",
        text,
    )
    # Bug 2 (KPMG): "...,000NEXT..." → "...,000 NEXT...". The lookahead requires
    # the trailing `\d` to look like the start of a new comma-grouped number
    # (e.g. "24,750"), so we don't accidentally split inside "24,750,000" at
    # its internal `,750` group.
    text = re.sub(r"(,\d{3})(?=\d{1,3},\d{3})", r"\1 ", text)
    return text


def _parse_money(raw: str) -> Decimal:
    s = raw.strip().replace("$", "").replace(",", "").replace(" ", "")
    # Em / en dash / lone hyphen used as zero placeholder.
    if s in {"—", "–", "-", "(-)", "()"}:  # noqa: RUF001
        return Decimal("0")
    negative = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    if not s or s == "-":
        return Decimal("0")
    value = Decimal(s)
    return -value if negative else value


def _parse_period(text: str) -> tuple[date, date, date]:
    """Parse 'Year Ended December 31, 20XX' (or a real year) into (start, end, as_of)."""
    m = _PERIOD_RE.search(text)
    if not m:
        raise ValueError("GAAP_SCPC extractor: missing 'Year Ended ...' header line")
    year_str = m.group("year")
    # Illustrative templates (KPMG, CohnReznick) use literal "20XX" — substitute
    # 2099 so the model is well-formed and the placeholder is unambiguous.
    year = 2099 if year_str == "20XX" else int(year_str)
    month_name = m.group("month")
    day = int(m.group("day"))
    period_end = datetime.strptime(f"{month_name} {day} {year}", "%B %d %Y").date()
    period_start = (
        period_end.replace(year=period_end.year - 1, month=1, day=1)
        if (period_end.month, period_end.day) == (12, 31)
        else period_end.replace(month=1, day=1)
    )
    return period_start, period_end, period_end


def _parse_fund_name(text: str) -> str:
    """Find the first '<Name>, L.P.' line — these statements always lead with it."""
    m = _FUND_NAME_RE.search(text)
    if not m:
        raise ValueError(
            "GAAP_SCPC extractor: could not locate fund name (looking for '<Name>, L.P.')"
        )
    return m.group("name").strip()


def _categorize(label: str) -> str | None:
    label = label.strip()
    for category, patterns in _CATEGORY_PATTERNS.items():
        if any(p.search(label) for p in patterns):
            return category
    return None


def _extract_rows(text: str) -> list[tuple[str, str, str, str]]:
    """Walk the normalised text and return (full_label, gp_raw, lp_raw, total_raw) tuples.

    Multi-line labels are handled by carrying forward any line that does NOT
    end in three money cells; on the next line that DOES, we prepend the carried
    label fragment.
    """
    rows: list[tuple[str, str, str, str]] = []
    label_buffer: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line:
            label_buffer.clear()
            continue
        m = _THREE_COL_RE.match(line)
        if m is None:
            # Line doesn't end in three money cells → treat as label continuation.
            # (Don't accumulate forever: clear if line starts to look like a section header.)
            if _NO_VALUES_RE.match(line):
                label_buffer.append(line.strip())
            continue
        label_fragment = m.group("label").strip()
        full_label = " ".join([*label_buffer, label_fragment]).strip()
        rows.append((full_label, m.group("gp"), m.group("lp"), m.group("total")))
        label_buffer.clear()
    return rows


def _locate_page(snippet: str, per_page_text: list[str]) -> int:
    for idx, page_text in enumerate(per_page_text, start=1):
        if snippet in page_text:
            return idx
    return 1


class GaapScpcExtractor(Extractor):
    """Deterministic extractor for fund-level GAAP Statement of Changes in Partners' Capital."""

    administrator = FundAdministrator.GAAP_SCPC
    name = "deterministic.gaap_scpc"

    def supports(self, text: str, administrator: FundAdministrator) -> bool:
        return administrator == FundAdministrator.GAAP_SCPC

    def extract(
        self,
        source: Path | bytes,
        text: str,
        per_page_text: list[str],
    ) -> CapitalAccountStatement:
        # Find the page containing the actual SCPC table — both the heading AND
        # a "Partners' capital, beginning of year" data row must be present.
        # Otherwise we'd happily hoover up data from a TOC page or a Statement
        # of Operations / Schedule of Investments / footnote table elsewhere
        # in the same document.
        scpc_page_text: str | None = None
        for page in per_page_text:
            if _SCPC_HEADING_RE.search(page) and _SCPC_DATA_ROW_RE.search(page):
                scpc_page_text = page
                break
        if scpc_page_text is None:
            raise ValueError(
                "GAAP_SCPC extractor: could not locate the SCPC page "
                "(heading + 'Partners' capital, beginning of year' data row)"
            )

        normalised = _normalize_text(scpc_page_text)
        period_start, period_end, as_of = _parse_period(normalised)
        fund_name = _parse_fund_name(normalised)

        rows = _extract_rows(normalised)
        if not rows:
            raise ValueError(
                "GAAP_SCPC extractor: no three-column data rows found "
                "(expected 'label  GP_value  LP_value  Total_value' lines)"
            )

        # Aggregate by category — single-value categories take the latest match,
        # summing categories accumulate.
        values: dict[str, Decimal] = {}
        provenance: dict[str, str] = {}
        category_contributors: dict[str, list[str]] = {}
        for label, _gp, lp_raw, _total in rows:
            category = _categorize(label)
            if category is None:
                continue
            amount = _parse_money(lp_raw)
            if category in _POSITIVE_MAGNITUDE_CATEGORIES:
                amount = abs(amount)
            if category in _SUMMING_CATEGORIES:
                values[category] = values.get(category, Decimal("0")) + amount
                # First contributor wins for provenance — keep the most diagnostic line.
                provenance.setdefault(category, f"{label}  {lp_raw}")
            else:
                values[category] = amount
                provenance[category] = f"{label}  {lp_raw}"
            category_contributors.setdefault(category, []).append(label[:60])

        # nav_beginning / nav_ending are the minimum viable extraction for this format.
        missing = [r for r in ("nav_beginning", "nav_ending") if r not in values]
        if missing:
            found_summary = (
                ", ".join(
                    f"{c} ({', '.join(labels)})" for c, labels in category_contributors.items()
                )
                if category_contributors
                else "none"
            )
            raise ValueError(
                f"GAAP_SCPC extractor: missing required field(s) {missing!r}. "
                f"Saw {len(rows)} candidate three-column row(s); matched categories: {found_summary}. "
                "If the labels look correct, the regex in _CATEGORY_PATTERNS may need extending."
            )

        field_sources = {
            field: FieldSource(
                page=_locate_page(snippet, per_page_text),
                source_text=snippet[:200],
            )
            for field, snippet in provenance.items()
        }

        # Confidence reflects how cleanly the format mapped onto our schema.
        # Detailed KPMG-style broken-out P&L rows score higher than the
        # CohnReznick-style compact "Pro rata allocation" path, because the
        # latter bundles unrelated income items into a single aggregate that we
        # bucket into realized_gain_loss without further detail.
        used_pro_rata = any(
            "pro rata allocation" in label.lower()
            for label in category_contributors.get("realized_gain_loss", [])
        )
        confidence = 0.70 if used_pro_rata else 0.85

        meta = SourceMetadata(
            administrator=FundAdministrator.GAAP_SCPC,
            extractor=self.name,
            # Lower than Standish (0.95) because we're inferring an LP-aggregate
            # from a fund-level statement and bundling several line items.
            parse_confidence=confidence,
            raw_text_excerpt=text[:500],
            field_sources=field_sources,
        )

        return CapitalAccountStatement(
            lp_name="All Limited Partners (Aggregate)",
            fund_name=fund_name,
            period_start=period_start,
            period_end=period_end,
            as_of_date=as_of,
            # LP-specific commitment fields are not present in fund-level SCPC.
            commitment=None,
            paid_in_capital=None,
            unfunded_commitment=None,
            distributions=None,
            nav_beginning=values["nav_beginning"],
            contributions_period=values.get("contributions_period", Decimal("0")),
            distributions_period=values.get("distributions_period", Decimal("0")),
            realized_gain_loss=values.get("realized_gain_loss", Decimal("0")),
            unrealized_gain_loss=values.get("unrealized_gain_loss", Decimal("0")),
            # Management fees are commingled into "Net investment loss" on SCPCs
            # and can't be cleanly separated; explicit zero (rather than None) so
            # the nav_roll_forward invariant runs against the bundled expenses.
            management_fees=Decimal("0"),
            partnership_expenses=values.get("partnership_expenses", Decimal("0")),
            nav_ending=values["nav_ending"],
            irr_net=None,
            tvpi_net=None,
            dpi_net=None,
            transactions=[],
            source_metadata=meta,
        )
