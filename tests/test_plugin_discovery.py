"""Tests for the entry-point-based extractor plugin mechanism.

These tests exercise the discovery path without requiring a real published
plugin package — we monkeypatch `importlib.metadata.entry_points` to return
synthesized entries, which is the same shape `pip install`ed plugins would
produce.
"""

from __future__ import annotations

from importlib import metadata
from pathlib import Path

import pytest

from vc_statement_parser.extractors import (
    ENTRY_POINT_GROUP,
    Extractor,
    _load_plugin_extractors,
)
from vc_statement_parser.models import (
    CapitalAccountStatement,
    FundAdministrator,
)


class _StubExtractor(Extractor):
    """Minimal extractor for plugin-discovery tests.

    We don't actually wire it into parse_statement here — the discovery test
    only verifies the entry-point load mechanism, not end-to-end parse.
    """

    administrator = FundAdministrator.UNKNOWN
    name = "test.stub"

    def supports(self, text: str, administrator: FundAdministrator) -> bool:
        return False

    def extract(
        self,
        source: Path | bytes,
        text: str,
        per_page_text: list[str],
    ) -> CapitalAccountStatement:
        raise NotImplementedError


class _BrokenAtImport:
    """Object that raises on instantiation — simulates a buggy plugin class."""

    def __init__(self) -> None:
        raise RuntimeError("synthetic init failure")


class _NotAnExtractor:
    """Object that is not an Extractor — simulates a plugin pointing at the
    wrong target."""


class _FakeEntryPoint:
    """Stand-in for `importlib.metadata.EntryPoint` — has the same `.name`,
    `.value`, `.group` attrs and a `.load()` that returns whatever we pass in.

    `EntryPoint` itself is an immutable NamedTuple (Python 3.11+) so we can't
    monkeypatch `load` on real instances. Duck-typing is good enough — the
    plugin loader only calls `.name`, `.value`, and `.load()`.
    """

    def __init__(self, name: str, value: str, loader: object) -> None:
        self.name = name
        self.value = value
        self.group = ENTRY_POINT_GROUP
        self._loader = loader

    def load(self) -> object:
        return self._loader


def _fake_entry_point(name: str, value: str, loader: object) -> _FakeEntryPoint:
    return _FakeEntryPoint(name, value, loader)


def test_plugin_extractor_class_is_loaded_and_instantiated(monkeypatch: pytest.MonkeyPatch) -> None:
    ep = _fake_entry_point("stub", "tests.fake:StubExtractor", _StubExtractor)
    monkeypatch.setattr(metadata, "entry_points", lambda group=None: [ep])
    extractors = _load_plugin_extractors()
    assert len(extractors) == 1
    assert isinstance(extractors[0], _StubExtractor)
    assert extractors[0].name == "test.stub"


def test_plugin_extractor_instance_is_accepted_directly(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the entry point already points at an *instance*, use it as-is."""
    ep = _fake_entry_point("stub", "tests.fake:stub_instance", _StubExtractor())
    monkeypatch.setattr(metadata, "entry_points", lambda group=None: [ep])
    extractors = _load_plugin_extractors()
    assert len(extractors) == 1
    assert isinstance(extractors[0], _StubExtractor)


def test_buggy_plugin_emits_warning_and_does_not_crash(
    monkeypatch: pytest.MonkeyPatch, recwarn: pytest.WarningsRecorder
) -> None:
    """One broken plugin must not stop the rest from loading."""
    good = _fake_entry_point("good", "tests.fake:Good", _StubExtractor)
    broken = _fake_entry_point("broken", "tests.fake:Broken", _BrokenAtImport)
    monkeypatch.setattr(metadata, "entry_points", lambda group=None: [broken, good])

    extractors = _load_plugin_extractors()
    assert len(extractors) == 1
    assert isinstance(extractors[0], _StubExtractor)
    # A warning was raised about the broken one.
    assert any("broken" in str(w.message) for w in recwarn.list)


def test_plugin_pointing_at_non_extractor_is_skipped(
    monkeypatch: pytest.MonkeyPatch, recwarn: pytest.WarningsRecorder
) -> None:
    bogus = _fake_entry_point("bogus", "tests.fake:NotAnExtractor", _NotAnExtractor())
    good = _fake_entry_point("good", "tests.fake:Good", _StubExtractor)
    monkeypatch.setattr(metadata, "entry_points", lambda group=None: [bogus, good])

    extractors = _load_plugin_extractors()
    assert len(extractors) == 1
    assert any("did not return an Extractor instance" in str(w.message) for w in recwarn.list)


def test_no_plugins_installed_returns_empty_tuple(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(metadata, "entry_points", lambda group=None: [])
    assert _load_plugin_extractors() == ()
