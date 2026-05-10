"""LLM fallback extractor — OpenAI-compatible Chat Completions API.

Activated when no deterministic extractor recognises the administrator. The LLM
returns a Pydantic model directly via `instructor` (no JSON-string parsing).
Each numeric field is grounded in a `(page, source_text)` pair so the
verification layer can cross-check arithmetic against the original PDF text.

This extractor speaks the OpenAI Chat Completions protocol and works with ANY
provider that implements the same surface — meaning users are not locked to
a single vendor and can pick whichever fits their cost / latency / privacy
profile. Notable compatible providers:

  * OpenAI               default; just set OPENAI_API_KEY
  * OpenRouter           OPENAI_BASE_URL=https://openrouter.ai/api/v1
                         (free tier available on selected models)
  * Groq                 OPENAI_BASE_URL=https://api.groq.com/openai/v1
                         (free tier; very low latency)
  * Together AI          OPENAI_BASE_URL=https://api.together.xyz/v1
  * DeepSeek             OPENAI_BASE_URL=https://api.deepseek.com/v1
  * Fireworks AI         OPENAI_BASE_URL=https://api.fireworks.ai/inference/v1
  * Ollama (local)       OPENAI_BASE_URL=http://localhost:11434/v1
                         (free, runs entirely on your machine)
  * LM Studio (local)    OPENAI_BASE_URL=http://localhost:1234/v1   (free)
  * vLLM / LiteLLM proxy / any other OpenAI-compatible gateway

Configuration is via environment variables:

  OPENAI_API_KEY        Required. (Local providers like Ollama accept any
                        non-empty value, e.g. "ollama".)
  OPENAI_BASE_URL       Optional. Defaults to OpenAI's endpoint.
  VC_PARSER_LLM_MODEL   Optional. Defaults to "gpt-4o-mini" (cheap & capable).
                        Override with whichever model your provider exposes,
                        e.g. "llama-3.3-70b-versatile" on Groq, or
                        "llama3.2" on Ollama.

Imports `instructor` and `openai` lazily so the core package stays usable
without the LLM extras (`pip install vc-statement-parser[llm]`).
"""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from ..models import (
    CapitalAccountStatement,
    FieldSource,
    FundAdministrator,
    SourceMetadata,
    Transaction,
    TransactionType,
)

DEFAULT_MODEL = "gpt-4o-mini"


class _ExtractedTransaction(BaseModel):
    model_config = ConfigDict(frozen=True)
    transaction_date: date
    type: str
    amount: Decimal
    description: str | None = None


class _ExtractedFields(BaseModel):
    """LLM-facing schema. Mirrors `CapitalAccountStatement` minus `source_metadata`,
    plus optional per-field source-text grounding."""

    model_config = ConfigDict(frozen=True)

    lp_name: str
    fund_name: str
    period_start: date
    period_end: date
    as_of_date: date
    commitment: Decimal
    paid_in_capital: Decimal
    unfunded_commitment: Decimal
    distributions: Decimal
    nav_beginning: Decimal
    contributions_period: Decimal
    distributions_period: Decimal
    nav_ending: Decimal
    realized_gain_loss: Decimal
    unrealized_gain_loss: Decimal
    management_fees: Decimal
    partnership_expenses: Decimal
    irr_net: Decimal | None = None
    tvpi_net: Decimal | None = None
    dpi_net: Decimal | None = None
    transactions: list[_ExtractedTransaction] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0)
    citations: dict[str, str] = Field(
        default_factory=dict,
        description="Map of field name to verbatim source-text excerpt from the PDF.",
    )


_SYSTEM_PROMPT = """You extract LP capital account statement data into structured JSON.

Rules:
- Sign convention: distributions and fees are positive magnitudes - do NOT negate.
- Cumulative ("life-to-date") fields use no `_period` suffix; period-only flow fields use `_period`.
- Performance ratios: TVPI/DPI as decimal multiples (1.54 not "1.54x"); IRR as decimal (0.185 not 18.5%).
- For each numeric field, populate `citations[field_name]` with the verbatim line from the PDF.
- Set `confidence` to your honest 0-1 estimate of extraction quality.
- Align field names to ILPA Reporting Template v2.0.
"""


class LLMExtractionUnavailableError(RuntimeError):
    """Raised when LLM extras aren't installed or no API key is set."""


# Backwards-compatibility alias for the original name; deprecated.
LLMExtractionUnavailable = LLMExtractionUnavailableError


def extract_with_llm(
    source: Path | bytes,
    text: str,
    administrator: FundAdministrator,
    *,
    model: str | None = None,
    base_url: str | None = None,
    max_tokens: int = 4096,
) -> CapitalAccountStatement:
    """Run the LLM-backed extractor against any OpenAI-compatible endpoint.

    Args:
        source: PDF source (unused here; included for extractor-protocol parity).
        text: Full extracted PDF text to feed the model.
        administrator: Detected administrator (passed as a hint into the prompt).
        model: Override the model. Defaults to `$VC_PARSER_LLM_MODEL` or
            `"gpt-4o-mini"`. Use whatever the configured provider exposes.
        base_url: Override the API endpoint. Defaults to `$OPENAI_BASE_URL`
            (or the OpenAI default when unset). Set this to point at any
            OpenAI-compatible provider — see the module docstring for a list.
        max_tokens: Cap on response tokens.

    Raises:
        LLMExtractionUnavailableError: if the `[llm]` extras aren't installed
            or `OPENAI_API_KEY` is not set.
    """
    try:
        import instructor  # noqa: PLC0415  (lazy import — optional [llm] extra)
        from openai import OpenAI  # noqa: PLC0415  (lazy import — optional [llm] extra)
    except ImportError as e:  # pragma: no cover - exercised in optional install paths
        raise LLMExtractionUnavailableError(
            "Install LLM extras: `pip install 'vc-statement-parser[llm]'`"
        ) from e

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise LLMExtractionUnavailableError(
            "OPENAI_API_KEY environment variable is not set. Point at any "
            "OpenAI-compatible provider (OpenAI, OpenRouter, Groq, Together, "
            "Ollama, LM Studio, vLLM, ...) by also setting OPENAI_BASE_URL — "
            "see vc_statement_parser.extractors.llm module docs."
        )

    resolved_base_url = base_url or os.getenv("OPENAI_BASE_URL") or None
    resolved_model = model or os.getenv("VC_PARSER_LLM_MODEL") or DEFAULT_MODEL

    client = instructor.from_openai(OpenAI(api_key=api_key, base_url=resolved_base_url))
    extracted: _ExtractedFields = client.chat.completions.create(
        model=resolved_model,
        max_tokens=max_tokens,
        response_model=_ExtractedFields,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (f"Administrator hint: {administrator.value}\n\nPDF TEXT:\n{text}"),
            },
        ],
    )
    return _build_statement(extracted, administrator, text)


def _build_statement(
    extracted: _ExtractedFields,
    administrator: FundAdministrator,
    raw_text: str,
) -> CapitalAccountStatement:
    field_sources: dict[str, FieldSource] = {
        name: FieldSource(page=1, source_text=cite)
        for name, cite in extracted.citations.items()
        if cite.strip()
    }
    meta = SourceMetadata(
        administrator=administrator,
        extractor="llm.instructor",
        parse_confidence=extracted.confidence,
        raw_text_excerpt=raw_text[:500],
        field_sources=field_sources,
    )

    transactions = [
        Transaction(
            transaction_date=t.transaction_date,
            type=_normalize_type(t.type),
            amount=t.amount,
            description=t.description,
        )
        for t in extracted.transactions
    ]

    return CapitalAccountStatement(
        lp_name=extracted.lp_name,
        fund_name=extracted.fund_name,
        period_start=extracted.period_start,
        period_end=extracted.period_end,
        as_of_date=extracted.as_of_date,
        commitment=extracted.commitment,
        paid_in_capital=extracted.paid_in_capital,
        unfunded_commitment=extracted.unfunded_commitment,
        distributions=extracted.distributions,
        nav_beginning=extracted.nav_beginning,
        contributions_period=extracted.contributions_period,
        distributions_period=extracted.distributions_period,
        nav_ending=extracted.nav_ending,
        realized_gain_loss=extracted.realized_gain_loss,
        unrealized_gain_loss=extracted.unrealized_gain_loss,
        management_fees=extracted.management_fees,
        partnership_expenses=extracted.partnership_expenses,
        irr_net=extracted.irr_net,
        tvpi_net=extracted.tvpi_net,
        dpi_net=extracted.dpi_net,
        transactions=transactions,
        source_metadata=meta,
    )


def _normalize_type(raw: str) -> TransactionType:
    key = raw.lower().strip().replace(" ", "_").replace("-", "_")
    try:
        return TransactionType(key)
    except ValueError:
        return TransactionType.OTHER
