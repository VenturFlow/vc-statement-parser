# Contributing

Thanks for your interest in `vc-statement-parser`. The single highest-value
contribution is a **new deterministic extractor** — every administrator we
add is one fewer LP that has to retype quarterly statements.

This doc explains how to set up locally, what good contributions look like,
and a step-by-step walkthrough of adding a new administrator.

---

## Quick links

- **Found a bug or want to discuss a design choice?** Open a [GitHub
  issue](https://github.com/venturflow/vc-statement-parser/issues). For
  format-specific bugs, attach a synthetic PDF that reproduces the issue
  (NEVER a real LP statement — see [Privacy](#privacy) below).
- **Found a security issue?** See [SECURITY.md](SECURITY.md). Do NOT open
  a public issue.
- **Curious about a design decision?** Browse [docs/DECISIONS.md](docs/DECISIONS.md).
- **Want to extend the framework to non-PCAP documents?** See
  [docs/EXTENDING.md](docs/EXTENDING.md).
- **Plugin development (third-party extractors via `pip install`)?** See
  [docs/PLUGINS.md](docs/PLUGINS.md).

---

## Local setup

```bash
git clone https://github.com/venturflow/vc-statement-parser.git
cd vc-statement-parser
uv sync --all-extras
uv run pytest                     # 60+ tests, runs in <5s
uv run ruff check src tests examples
uv run ruff format --check src tests examples
```

If you don't have `uv`, install it from [astral.sh/uv](https://astral.sh/uv)
or use `pip install -e '.[dev,llm,fixtures]'` against a Python 3.11+ venv.

We also recommend installing pre-commit hooks so ruff runs before every
commit:

```bash
uv run pre-commit install
```

---

## What makes a good contribution

| Priority | Contribution | Why it matters |
|---|---|---|
| **HIGH** | A new deterministic extractor for an administrator we don't yet support (Gen II, SS&C, Citco, Apex, Alter Domus, …) | Each one removes manual retyping for everyone using that admin. |
| **HIGH** | Better arithmetic invariants in `verification.py` | Verification is the project's wedge — more invariants = more bugs caught. |
| MEDIUM | New supported document types (capital call notice, distribution notice, K-1) | The architecture already separates dispatch / extract / verify; extending it to new doc types is mostly schema + regex. |
| MEDIUM | Real-world bug fixes against existing extractors with a regression test | The synthetic fixtures cover the layouts we know; real PDFs will keep finding edges. |
| LOW | Style-only refactors with no behavior change | We will accept these but they slow review. Bundle with a real fix when possible. |

---

## Step-by-step: adding a new administrator

This walkthrough builds a stub `GenIIExtractor`. Real extractors are usually
done across 2-3 PRs (synthetic fixture → extractor → real-PDF tests).

### 1. Get a synthetic fixture for the format

Real Gen II statements are confidential. Build a synthetic that mirrors the
public layout:

```bash
# Copy the Standish generator as a starting point
cp examples/fixtures/generate.py examples/fixtures/generate_gen_ii.py
# Edit it: change the layout + label text to match Gen II's public template.
# Use realistic dollar amounts; pick numbers that satisfy the verification
# identity nav_begin + contribs - dists + P&L - fees == nav_end.
```

Run the generator to produce `examples/fixtures/gen_ii_synthetic.pdf` and
eyeball it (open it in any PDF viewer) — that's what the parser will see.

### 2. Wire up the dispatcher

Edit `src/vc_statement_parser/dispatcher.py`. The Gen II signature already
exists in `_HEADER_SIGNATURES` — confirm or extend it. Also confirm the
PCAP data anchor (`_PCAP_DATA_ANCHOR`) matches a phrase that appears on a
real Gen II statement (e.g. "Capital Account Statement", "Beginning
Balance", "Total Commitment"). If not, add it to the regex.

### 3. Subclass `Extractor`

Create `src/vc_statement_parser/extractors/gen_ii.py`. The minimum viable
shape is:

```python
from .base import Extractor
from ..models import (
    CapitalAccountStatement, FieldSource, FundAdministrator,
    SourceMetadata, Transaction, TransactionType,
)


class GenIIExtractor(Extractor):
    administrator = FundAdministrator.GEN_II
    name = "deterministic.gen_ii"

    def supports(self, text: str, administrator: FundAdministrator) -> bool:
        return administrator == FundAdministrator.GEN_II

    def extract(
        self,
        source,            # Path | bytes — usually unused
        text: str,         # full document text
        per_page_text: list[str],
    ) -> CapitalAccountStatement:
        # Parse out fields from `text`. Use regex helpers similar to those in
        # standish.py and gaap_scpc.py. Build and return a
        # CapitalAccountStatement with source_metadata populated.
        ...
```

Look at [`extractors/standish.py`](src/vc_statement_parser/extractors/standish.py)
for a simple LP-PCAP reference, or
[`extractors/gaap_scpc.py`](src/vc_statement_parser/extractors/gaap_scpc.py)
for a more complex multi-column extractor with PDF whitespace-bug
normalisation.

### 4. Register the extractor

Append your extractor to the tuple in
`src/vc_statement_parser/extractors/__init__.py`:

```python
from .gen_ii import GenIIExtractor

DETERMINISTIC_EXTRACTORS: tuple[Extractor, ...] = (
    StandishExtractor(),
    GaapScpcExtractor(),
    GenIIExtractor(),
)
```

(Or skip this step entirely and ship as a separate plugin package — see
[docs/PLUGINS.md](docs/PLUGINS.md) for entry-point-based discovery.)

### 5. Add tests

Create `tests/test_extractors_gen_ii.py`:

```python
def test_gen_ii_synthetic_parses_and_verifies(tmp_path):
    from examples.fixtures.generate_gen_ii import render_gen_ii_pdf
    pdf = render_gen_ii_pdf(tmp_path / "gen_ii.pdf")
    statement = parse_statement(pdf, use_llm_fallback=False)
    assert statement.source_metadata.administrator is FundAdministrator.GEN_II
    report = verify(statement)
    assert report.passed
```

If you have a public reference PDF (e.g. fund-admin marketing material),
add it to `examples/real_world/` and write integration tests guarded by
`@pytest.mark.skipif(not PDF.exists(), ...)`. **Read
[`examples/real_world/README.md`](examples/real_world/README.md) first**
to confirm the file meets our public-source rule.

### 6. Open the PR

A good PR includes:
- The extractor + tests passing
- A note in [CHANGELOG.md](CHANGELOG.md) under `[Unreleased]`
- A 1-line update to [`README.md`](README.md)'s "Supported formats" table
- Confirmation that `uv run ruff check`, `uv run ruff format --check`, and
  `uv run pytest` are all green locally

---

## Coding standards

- **Python ≥ 3.11**, fully type-annotated.
- **Pydantic models are frozen** — never mutate; use `model_copy(update=...)`.
- **Prefer many small, focused modules.** Files > 400 lines need a strong
  reason. The single exception is auditor-template generators in
  `examples/fixtures/`, which are intentionally linear.
- **Validate at boundaries**; trust internal calls.
- **`ruff check` and `ruff format` must be clean.** CI enforces this.
- **The `S` (security/bandit) ruleset is enabled in src/.** If you trip a
  rule, fix the code rather than blanket-ignoring; `# noqa: S###` is
  acceptable only with a one-line justification comment.
- **Avoid `print()` in library code** — the CLI uses `rich.console`.

## Commits

Conventional commits: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`,
`chore:`, `perf:`, `ci:`. Body lines under 72 chars.

Examples:
```
feat(extractors): add Gen II deterministic extractor
fix(dispatcher): require PCAP data anchor to avoid vendor-list false positives
docs: walkthrough for adding a new administrator
```

## Privacy

Real LP statements contain confidential investor and fund data. **Never**
commit, paste, or upload one — not in the issue tracker, not in PR
descriptions, not in test fixtures.

The only PDFs allowed in this repository are:
1. **Synthetic fixtures** generated by `examples/fixtures/generate*.py`.
2. **Public illustrative documents** (auditor templates, ILPA guidance,
   FOIA disclosures) that meet the rules in
   [`examples/real_world/README.md`](examples/real_world/README.md).

`.gitignore` blocks the common slip-up patterns (`*.real.pdf`, `*.lp.pdf`,
`*.confidential.pdf`, `examples/real_world/private_*`, etc.) but it is the
last line of defense, not the first.

If a real LP file ever lands in history, follow [SECURITY.md](SECURITY.md)
— assume the data is exposed and notify the affected LP.

## License

By contributing you agree that your contributions are licensed under the
MIT License (see [LICENSE](LICENSE)).
