"""Pydantic models for the LP capital account statement.

Field names align with ILPA Reporting Template v2.0 (January 2025; mandatory Q1 2026).
See docs/ILPA_ALIGNMENT.md for the field-by-field mapping. ILPA does not publish
a JSON Schema; we encode the field semantics here, not the copyrighted XLSX/PDF.

The `FieldSource` audit-trail pattern is borrowed from google/langextract — every
extracted field can carry a `(page, bbox, source_text)` tuple so a reviewer can
trace any number on the statement back to the exact pixel range it came from.

All models are frozen — never mutate; create new objects via `model_copy(update=...)`.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FundAdministrator(StrEnum):
    """Fund administrators with format-specific extractors. Extend in dispatcher.py."""

    STANDISH = "standish"
    GEN_II = "gen_ii"
    SSC = "ssc"  # SS&C — covers Geneva, Black Diamond, Investran exports
    CITCO = "citco"
    APEX = "apex"
    ALTER_DOMUS = "alter_domus"
    # Generic GAAP "Statement of Changes in Partners' Capital" — fund-level
    # rather than LP-level, used by auditor illustrative templates (KPMG,
    # CohnReznick, ...) and by GPs preparing audited fund financials. Many
    # LP-specific fields (commitment, paid-in, unfunded, IRR/TVPI/DPI) are
    # not present in this format and remain None on the parsed statement.
    GAAP_SCPC = "gaap_scpc"
    UNKNOWN = "unknown"


class TransactionType(StrEnum):
    """ILPA v2.0 transaction categorization."""

    CONTRIBUTION = "contribution"
    DISTRIBUTION = "distribution"
    MANAGEMENT_FEE = "management_fee"
    PARTNERSHIP_EXPENSE = "partnership_expense"
    REALIZED_GAIN_LOSS = "realized_gain_loss"
    UNREALIZED_CHANGE = "unrealized_change"
    OTHER = "other"


class FieldSource(BaseModel):
    """Source grounding for one extracted field.

    Pattern adapted from google/langextract: every numeric field on a parsed
    statement can be traced back to (page, bounding box, verbatim excerpt).
    """

    model_config = ConfigDict(frozen=True)

    page: int = Field(..., ge=1, description="1-indexed PDF page number")
    bbox: tuple[float, float, float, float] | None = Field(
        default=None,
        description="(x0, y0, x1, y1) in PDF user-space points, if known",
    )
    source_text: str = Field(
        ..., min_length=1, description="Verbatim excerpt the field was extracted from"
    )


class SourceMetadata(BaseModel):
    """Provenance for a parsed statement: which extractor ran, with what confidence."""

    model_config = ConfigDict(frozen=True)

    administrator: FundAdministrator
    extractor: str = Field(..., description="e.g. 'deterministic.standish' or 'llm.instructor'")
    parse_confidence: float = Field(..., ge=0.0, le=1.0)
    raw_text_excerpt: str = Field(default="", description="First ~500 chars of the source PDF")
    field_sources: dict[str, FieldSource] = Field(default_factory=dict)


class Transaction(BaseModel):
    """A single capital movement during the period (contribution, distribution, fee, …)."""

    model_config = ConfigDict(frozen=True)

    transaction_date: date
    type: TransactionType
    amount: Decimal = Field(..., description="Positive magnitude; sign implied by `type`")
    description: str | None = None


class CapitalAccountStatement(BaseModel):
    """LP capital account statement, ILPA Reporting Template v2.0 aligned.

    Cumulative ("life-to-date") fields are named without a `_period` suffix.
    Period-only flow fields are suffixed `_period`.
    """

    model_config = ConfigDict(frozen=True)

    # Identification — ILPA: "Limited Partner", "Fund Name"
    lp_name: str
    fund_name: str

    # Reporting period — ILPA: "Period Beginning", "Period Ending", "As Of"
    period_start: date
    period_end: date
    as_of_date: date

    # Commitment summary — ILPA: "Total Commitment", "Cumulative Capital Called",
    # "Unfunded Commitment", "Cumulative Distributions". Optional because fund-level
    # GAAP statements (Statement of Changes in Partners' Capital) only report
    # period activity, not LP-level commitment / paid-in / unfunded balances.
    commitment: Decimal | None = None
    paid_in_capital: Decimal | None = None
    unfunded_commitment: Decimal | None = None
    distributions: Decimal | None = Field(
        default=None,
        description="Cumulative life-to-date distributions",
    )

    # Period activity — ILPA: "Beginning Balance", "Capital Contributions",
    # "Distributions", "Ending Balance". These are the minimum viable shape
    # for any capital statement — required.
    nav_beginning: Decimal
    contributions_period: Decimal
    distributions_period: Decimal
    nav_ending: Decimal

    # P&L — ILPA: "Realized Gains/(Losses)", "Unrealized Gains/(Losses)"
    realized_gain_loss: Decimal
    unrealized_gain_loss: Decimal

    # Fees — ILPA: "Management Fees", "Partnership Expenses". Optional: GAAP
    # SCPC statements show fees on the Statement of Operations page, not on the
    # statement of changes in partners' capital — so an SCPC-only extraction
    # may legitimately leave these unset.
    management_fees: Decimal | None = None
    partnership_expenses: Decimal | None = None

    # Performance metrics — ILPA: "Net IRR", "Net TVPI", "Net DPI"
    irr_net: Decimal | None = None
    tvpi_net: Decimal | None = None
    dpi_net: Decimal | None = None

    # Detailed transactions for the period
    transactions: list[Transaction] = Field(default_factory=list)

    # Provenance
    source_metadata: SourceMetadata

    @model_validator(mode="after")
    def _check_period_ordering(self) -> CapitalAccountStatement:
        if self.period_end < self.period_start:
            raise ValueError("period_end must be on or after period_start")
        return self
