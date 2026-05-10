# Writing an extractor plugin

`vc-statement-parser` discovers third-party extractors at runtime via
[setuptools entry points](https://packaging.python.org/en/latest/specifications/entry-points/).
This means you can ship an extractor for any administrator — including
proprietary ones used internally at your firm — as a separate
`pip install`able package, with **zero changes** to this repository.

> **Why?** The in-tree extractors are a flywheel for *commonly-shared*
> formats (Standish, KPMG/CohnReznick illustrative, eventually Gen II /
> SS&C / Citco / Apex / Alter Domus). Internal-only formats (your fund
> admin's bespoke template, your firm's custom roll-forward, your
> consultant's hand-built XLSX→PDF export) belong in your own private
> package, not the public repo.

---

## 30-second example

Create a tiny package `vc-extractor-acme`:

```text
vc-extractor-acme/
├── pyproject.toml
└── src/
    └── vc_extractor_acme/
        ├── __init__.py
        └── extractor.py
```

`pyproject.toml`:

```toml
[project]
name = "vc-extractor-acme"
version = "0.1.0"
dependencies = ["vc-statement-parser>=0.1"]

[project.entry-points."vc_statement_parser.extractors"]
acme = "vc_extractor_acme.extractor:AcmeExtractor"
```

`src/vc_extractor_acme/extractor.py`:

```python
from __future__ import annotations

from pathlib import Path

from vc_statement_parser.extractors.base import Extractor
from vc_statement_parser.models import (
    CapitalAccountStatement,
    FundAdministrator,
    SourceMetadata,
)


class AcmeExtractor(Extractor):
    administrator = FundAdministrator.UNKNOWN  # or your custom admin code
    name = "acme.proprietary"

    def supports(self, text: str, administrator: FundAdministrator) -> bool:
        # Match the Acme letterhead string.
        return "ACME FUND ADMIN" in text[:500]

    def extract(
        self,
        source: Path | bytes,
        text: str,
        per_page_text: list[str],
    ) -> CapitalAccountStatement:
        # ... your regex / table extraction logic ...
        # Return a CapitalAccountStatement.
        raise NotImplementedError
```

Then:

```bash
pip install vc-extractor-acme
vc-statement-parse acme_q1_2024.pdf --validate     # AcmeExtractor auto-runs
```

That's it. The plugin's class is discovered at import time and added to
`DETERMINISTIC_EXTRACTORS` after the in-tree extractors.

---

## Entry-point group

Plugins must register against the group:

```
vc_statement_parser.extractors
```

The entry point's *value* may be either:

- **A class** (preferred). It will be instantiated with no args.
- **An instance**. It will be used as-is.

Either works. Classes are slightly more idiomatic.

---

## Order and precedence

The final tuple returned by `vc_statement_parser.extractors.DETERMINISTIC_EXTRACTORS`
is, in order:

1. **In-tree extractors** in the order they appear in
   `_BUILTIN_EXTRACTORS` (currently `StandishExtractor`, then
   `GaapScpcExtractor`).
2. **Plugin extractors** in whatever order `importlib.metadata.entry_points()`
   yields them — typically install order, but do not depend on this.

`parse_statement()` walks the tuple in order and returns the first extractor
whose `supports()` returns `True`. If you need to override an in-tree
extractor for the same administrator, do not use the plugin path — that's
a sign you should be sending a PR upstream, or forking.

---

## Robustness contract

The host process treats plugin discovery as **best-effort**:

- A plugin that fails to import emits a `UserWarning` and is skipped.
- A plugin that fails to instantiate emits a `UserWarning` and is skipped.
- A plugin whose loaded object isn't an `Extractor` instance emits a
  `UserWarning` and is skipped.

These warnings are also logged at `WARNING` level under the
`vc_statement_parser.extractors` logger so production log aggregators see
them. The host application keeps running with whatever extractors did load
— **one bad plugin must never break parsing for everyone else.**

For the same reason: don't do expensive work in your extractor's
constructor (it runs at import time of any process that imports
`vc_statement_parser`). Lazy-load any heavy dependencies inside `extract()`
or use module-level helpers that fail gracefully.

---

## Testing your plugin

Inside your plugin package:

```python
def test_plugin_registers_via_entry_point():
    from vc_statement_parser.extractors import DETERMINISTIC_EXTRACTORS
    assert any(
        e.name == "acme.proprietary" for e in DETERMINISTIC_EXTRACTORS
    )
```

This is the strongest end-to-end test — it confirms your `pyproject.toml`
entry point declaration is syntactically correct AND that `pip install`
exposed it through `importlib.metadata`.

---

## Naming conventions

- Plugin packages: `vc-extractor-<slug>` (PyPI) or
  `vc_extractor_<slug>` (Python module).
- Entry-point name: `<slug>` (lowercase, no prefix).
- `Extractor.name`: dotted, descriptive — e.g.
  `"acme.proprietary"`, `"deutsche-bank.q1-2024"`.

---

## When NOT to use plugins

- The format is **publicly used by many LPs** (Gen II, SS&C, Citco, Apex,
  Alter Domus). Send a PR — every other LP using that admin benefits.
- The change touches the **schema** (`CapitalAccountStatement`) or the
  **verification layer**. Those are core; PR them.
- The format is a **document type other than PCAP** (capital call notice,
  K-1, fund financials). See [docs/EXTENDING.md](EXTENDING.md) — those
  belong as new top-level document types, not as plugin extractors.

---

## See also

- [`CONTRIBUTING.md`](../CONTRIBUTING.md) — for in-tree contributions
- [`docs/EXTENDING.md`](EXTENDING.md) — for new document types
- [`docs/DECISIONS.md`](DECISIONS.md) — for architectural rationale
- [setuptools entry-point docs](https://setuptools.pypa.io/en/latest/userguide/entry_point.html)
- [PEP 621](https://peps.python.org/pep-0621/) — the `pyproject.toml`
  metadata standard
