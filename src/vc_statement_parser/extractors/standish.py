"""Deterministic extractor for the Standish synthetic fixture format.

The synthetic format is produced by `examples/fixtures/generate.py`. The same
patterns are tolerant enough to recognise the public layout structure but real
Standish statements will need iteration — see CONTRIBUTING.md for how to extend.
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
    Transaction,
    TransactionType,
)
from .base import Extractor

# A money cell may be parenthesized for negatives, may have a $ prefix, thousands
# commas, and decimals. Order matters: optional `(` precedes optional `$` to handle
# the conventional accounting form `($800,000.00)`.
_MONEY_RE = r"\(?\s*-?\s*\$?\s*[\d,]+(?:\.\d{1,2})?\s*\)?"
_PCT_RE = r"-?\d+(?:\.\d+)?\s*%"
_MULT_RE = r"-?\d+(?:\.\d+)?\s*x"


def _parse_money(raw: str) -> Decimal:
    s = raw.strip().replace("$", "").replace(",", "").replace(" ", "")
    negative = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    if not s:
        raise ValueError(f"empty money string: {raw!r}")
    value = Decimal(s)
    return -value if negative else value


def _parse_pct(raw: str) -> Decimal:
    return Decimal(raw.strip().rstrip("%").strip()) / Decimal("100")


def _parse_multiple(raw: str) -> Decimal:
    return Decimal(raw.strip().rstrip("xX").strip())


def _find(text: str, label: str, value_re: str) -> tuple[str, str] | None:
    """Return (matched_value, full_match) for the first `label ... value_re` line."""
    pattern = re.compile(rf"{label}\s*[:\-]?\s*({value_re})", re.IGNORECASE)
    m = pattern.search(text)
    if not m:
        return None
    return m.group(1), m.group(0)


def _require(text: str, label: str, value_re: str) -> tuple[str, str]:
    found = _find(text, label, value_re)
    if found is None:
        raise ValueError(f"could not find {label!r} in statement text")
    return found


def _parse_long_date(raw: str) -> date:
    """Parse strings like 'January 1, 2024' or '2024-01-15'."""
    raw = raw.strip()
    for fmt in ("%B %d, %Y", "%Y-%m-%d", "%m/%d/%Y", "%b %d, %Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unrecognized date format: {raw!r}")


_PERIOD_RE = re.compile(
    r"Period\s*[:\-]?\s*(?P<start>[A-Za-z]+\s+\d+,\s+\d{4})"
    r"\s*[–—\-]\s*"  # noqa: RUF001  (en/em-dash variants seen in real PDFs)
    r"(?P<end>[A-Za-z]+\s+\d+,\s+\d{4})",
    re.IGNORECASE,
)

_TRANSACTION_LINE_RE = re.compile(
    r"^\s*(?P<date>\d{4}-\d{2}-\d{2})\s+"
    r"(?P<type>Contribution|Distribution|Mgmt\s+Fee|Expenses?|Realized|Unrealized)\s+"
    r"(?P<amount>" + _MONEY_RE + r")\s*$",
    re.IGNORECASE | re.MULTILINE,
)

_TYPE_MAP: dict[str, TransactionType] = {
    "contribution": TransactionType.CONTRIBUTION,
    "distribution": TransactionType.DISTRIBUTION,
    "mgmt fee": TransactionType.MANAGEMENT_FEE,
    "expense": TransactionType.PARTNERSHIP_EXPENSE,
    "expenses": TransactionType.PARTNERSHIP_EXPENSE,
    "realized": TransactionType.REALIZED_GAIN_LOSS,
    "unrealized": TransactionType.UNREALIZED_CHANGE,
}


class StandishExtractor(Extractor):
    administrator = FundAdministrator.STANDISH
    name = "deterministic.standish"

    def supports(self, text: str, administrator: FundAdministrator) -> bool:
        return administrator == FundAdministrator.STANDISH

    def extract(
        self,
        source: Path | bytes,
        text: str,
        per_page_text: list[str],
    ) -> CapitalAccountStatement:
        lp_match = re.search(r"Limited Partner\s*[:\-]\s*(.+)", text)
        fund_match = re.search(r"Fund\s*[:\-]\s*(.+)", text)
        if not lp_match or not fund_match:
            raise ValueError("Standish extractor: missing LP or Fund header")

        period = _PERIOD_RE.search(text)
        if not period:
            raise ValueError("Standish extractor: missing Period line")
        period_start = _parse_long_date(period.group("start"))
        period_end = _parse_long_date(period.group("end"))

        as_of_match = _require(text, "As of Date", r"[A-Za-z]+\s+\d+,\s+\d{4}")
        as_of_date = _parse_long_date(as_of_match[0])

        commitment, _ = _require(text, "Total Commitment", _MONEY_RE)
        paid_in, _ = _require(text, "Paid-in Capital", _MONEY_RE)
        unfunded, _ = _require(text, "Unfunded Commitment", _MONEY_RE)
        cum_distributions, _ = _require(text, "Cumulative Distributions", _MONEY_RE)

        nav_begin, nav_begin_match = _require(text, r"Beginning Balance(?:\s*\(NAV\))?", _MONEY_RE)
        contributions, _ = _require(text, "Capital Contributions", _MONEY_RE)
        # Match standalone "Distributions:", excluding "Cumulative Distributions:".
        distributions_period, _ = _require(text, r"(?<!Cumulative\s)Distributions", _MONEY_RE)
        realized, _ = _require(text, r"Realized Gains/?\(Losses\)", _MONEY_RE)
        unrealized, _ = _require(text, r"Unrealized Gains/?\(Losses\)", _MONEY_RE)
        mgmt_fees, _ = _require(text, "Management Fees", _MONEY_RE)
        partnership_expenses, _ = _require(text, "Partnership Expenses", _MONEY_RE)
        nav_end, nav_end_match = _require(text, r"Ending Balance(?:\s*\(NAV\))?", _MONEY_RE)

        irr = _find(text, "Net IRR", _PCT_RE)
        tvpi = _find(text, "Net TVPI", _MULT_RE)
        dpi = _find(text, "Net DPI", _MULT_RE)

        transactions = self._parse_transactions(text)

        # Build source-grounding metadata for two example anchor fields.
        field_sources: dict[str, FieldSource] = {}
        for label, match in (("nav_beginning", nav_begin_match), ("nav_ending", nav_end_match)):
            page = _locate_page(match, per_page_text)
            field_sources[label] = FieldSource(page=page, source_text=match.strip())

        meta = SourceMetadata(
            administrator=FundAdministrator.STANDISH,
            extractor=self.name,
            parse_confidence=0.95,
            raw_text_excerpt=text[:500],
            field_sources=field_sources,
        )

        # ILPA-aligned: distributions_period, management_fees, partnership_expenses
        # are stored as POSITIVE magnitudes (sign carried by the verification identity,
        # not the field). Statements that show them in parentheses or with leading
        # minus are normalised here. Realized/unrealized G/L stay signed.
        return CapitalAccountStatement(
            lp_name=lp_match.group(1).strip(),
            fund_name=fund_match.group(1).strip(),
            period_start=period_start,
            period_end=period_end,
            as_of_date=as_of_date,
            commitment=_parse_money(commitment),
            paid_in_capital=_parse_money(paid_in),
            unfunded_commitment=_parse_money(unfunded),
            distributions=abs(_parse_money(cum_distributions)),
            nav_beginning=_parse_money(nav_begin),
            contributions_period=abs(_parse_money(contributions)),
            distributions_period=abs(_parse_money(distributions_period)),
            realized_gain_loss=_parse_money(realized),
            unrealized_gain_loss=_parse_money(unrealized),
            management_fees=abs(_parse_money(mgmt_fees)),
            partnership_expenses=abs(_parse_money(partnership_expenses)),
            nav_ending=_parse_money(nav_end),
            irr_net=_parse_pct(irr[0]) if irr else None,
            tvpi_net=_parse_multiple(tvpi[0]) if tvpi else None,
            dpi_net=_parse_multiple(dpi[0]) if dpi else None,
            transactions=transactions,
            source_metadata=meta,
        )

    @staticmethod
    def _parse_transactions(text: str) -> list[Transaction]:
        results: list[Transaction] = []
        for m in _TRANSACTION_LINE_RE.finditer(text):
            type_key = m.group("type").lower().strip()
            t_type = _TYPE_MAP.get(type_key, TransactionType.OTHER)
            results.append(
                Transaction(
                    transaction_date=_parse_long_date(m.group("date")),
                    type=t_type,
                    amount=abs(_parse_money(m.group("amount"))),
                    description=m.group("type").strip(),
                )
            )
        return results


def _locate_page(snippet: str, per_page_text: list[str]) -> int:
    for idx, page_text in enumerate(per_page_text, start=1):
        if snippet in page_text:
            return idx
    return 1
