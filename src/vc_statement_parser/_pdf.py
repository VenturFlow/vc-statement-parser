"""Thin wrapper over pdfplumber for text extraction.

Kept tiny on purpose — extractors call `read_pdf_text` and operate on strings.
We isolate pdfplumber so a future swap (camelot, unstructured) is one file.
"""

from __future__ import annotations

import io
from pathlib import Path

import pdfplumber


def read_pdf_text(source: Path | bytes | io.BytesIO) -> tuple[str, list[str]]:
    """Return (joined_text, per_page_text). Newline-separated.

    Empty pages still produce an empty string in the per-page list so page indexing
    matches the PDF's 1-indexed page numbers (pages[0] == page 1).
    """
    if isinstance(source, bytes):
        stream: io.BytesIO | Path = io.BytesIO(source)
    else:
        stream = source

    with pdfplumber.open(stream) as pdf:
        pages = [(page.extract_text() or "") for page in pdf.pages]

    return ("\n".join(pages), pages)
