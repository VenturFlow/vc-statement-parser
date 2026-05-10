"""Extractor interface — one implementation per fund administrator."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ..models import CapitalAccountStatement, FundAdministrator


class Extractor(ABC):
    """Subclass per administrator. Stateless — instances are reused across parses."""

    administrator: FundAdministrator
    name: str

    @abstractmethod
    def supports(self, text: str, administrator: FundAdministrator) -> bool:
        """Return True iff this extractor can handle the given text/administrator."""

    @abstractmethod
    def extract(
        self,
        source: Path | bytes,
        text: str,
        per_page_text: list[str],
    ) -> CapitalAccountStatement:
        """Run extraction and return a fully populated `CapitalAccountStatement`."""
