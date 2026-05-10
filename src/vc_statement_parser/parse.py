"""Top-level parse_statement entry point.

Pipeline:
  1. Read PDF text via pdfplumber.
  2. Detect administrator from header signatures (or use `admin_hint`).
  3. Find the first deterministic extractor that supports the administrator.
  4. Fall back to the LLM extractor if no deterministic match (requires `[llm]`
     extras and `ANTHROPIC_API_KEY`).
  5. Return a fully-typed `CapitalAccountStatement`.

The dispatcher is intentionally simple — keep it readable. New admins are added
by registering an extractor in `extractors/__init__.py`, not by editing this file.
"""

from __future__ import annotations

from pathlib import Path

from ._pdf import read_pdf_text
from .dispatcher import detect_administrator
from .extractors import DETERMINISTIC_EXTRACTORS
from .models import CapitalAccountStatement, FundAdministrator


class NoExtractorAvailableError(RuntimeError):
    """No deterministic extractor matched and the LLM fallback is disabled."""


def parse_statement(
    file: Path | str | bytes,
    admin_hint: str | None = None,
    *,
    use_llm_fallback: bool = True,
) -> CapitalAccountStatement:
    """Parse one LP capital account statement PDF into a typed Pydantic model.

    Args:
        file: Path to a PDF, or raw PDF bytes.
        admin_hint: Optional administrator override (e.g. "standish", "gen_ii").
        use_llm_fallback: If True (default), fall through to the instructor +
            Anthropic extractor when no deterministic extractor matches.

    Raises:
        NoExtractorAvailableError: if no deterministic extractor matches and
            the LLM fallback is unavailable or disabled.
    """
    source: Path | bytes = Path(file) if isinstance(file, str | Path) else file

    text, per_page_text = read_pdf_text(source)
    administrator = detect_administrator(text, admin_hint, per_page_text=per_page_text)

    for extractor in DETERMINISTIC_EXTRACTORS:
        if extractor.supports(text, administrator):
            return extractor.extract(source, text, per_page_text)

    if not use_llm_fallback:
        raise NoExtractorAvailableError(
            f"No deterministic extractor for administrator={administrator.value!r} "
            "and LLM fallback is disabled."
        )

    # Lazy import so the core package works without LLM extras.
    from .extractors.llm import (  # noqa: PLC0415  (lazy: optional [llm] extra)
        LLMExtractionUnavailableError,
        extract_with_llm,
    )

    try:
        return extract_with_llm(source, text, administrator)
    except LLMExtractionUnavailableError as e:
        raise NoExtractorAvailableError(
            f"No deterministic extractor for administrator={administrator.value!r} "
            f"and LLM fallback unavailable: {e}"
        ) from e


__all__ = ["FundAdministrator", "NoExtractorAvailableError", "parse_statement"]
