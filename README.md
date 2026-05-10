# vc-statement-parser

> **Parse LP capital account statements into ILPA-aligned, arithmetic-verified JSON.**
> Drop-in for fund administrators that ship PDF-only statements (Standish, Gen II, SS&C, Citco, Apex, Alter Domus, …) plus auditor-style fund-level GAAP "Statement of Changes in Partners' Capital" (KPMG, CohnReznick, Deloitte, EY, PwC). Verification is a first-class citizen, not an afterthought.

[![CI](https://github.com/venturflow/vc-statement-parser/actions/workflows/ci.yml/badge.svg)](https://github.com/venturflow/vc-statement-parser/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python: 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

## Why this exists

Limited Partners receive quarterly statements as PDFs from a dozen different fund administrators, each with its own layout. Today the choice is (1) hire an analyst to retype them, (2) buy Canoe / Allvue / Arch (closed SaaS, $$$), or (3) build it yourself.

There's a deeper problem the closed-source tools rarely solve cleanly: **a parsed number is worthless until you've verified it**. A capital account statement is loaded with redundant arithmetic — `NAV_begin + contributions - distributions + P&L - fees = NAV_end`, `paid_in + unfunded = commitment`, `TVPI = (NAV + cum_distributions) / paid_in`. If those identities don't hold within tolerance, the parse failed (or the statement is wrong).

`vc-statement-parser` makes the verification layer the wedge:

```python
from vc_statement_parser import parse_statement, verify

statement = parse_statement("acme_q1_2024.pdf")   # → typed Pydantic model
report = verify(statement)                         # → arithmetic invariants
if not report.passed:
    for failure in report.failures:
        print(failure)                             # name, expected, actual, Δ, tolerance
```

## Install

```bash
pip install vc-statement-parser            # core: pdfplumber + pypdfium2 + typer
pip install 'vc-statement-parser[llm]'     # optional LLM fallback (instructor + openai)
```

The `[llm]` extra speaks the **OpenAI Chat Completions** protocol — it is *not* tied to OpenAI's hosted service. Point it at any OpenAI-compatible provider via env vars:

```bash
# Free local (Ollama)
export OPENAI_API_KEY=ollama                                # any non-empty string
export OPENAI_BASE_URL=http://localhost:11434/v1
export VC_PARSER_LLM_MODEL=llama3.2

# Free tier (Groq, very low latency)
export OPENAI_API_KEY=$GROQ_API_KEY
export OPENAI_BASE_URL=https://api.groq.com/openai/v1
export VC_PARSER_LLM_MODEL=llama-3.3-70b-versatile

# OpenRouter (free tier on selected models)
export OPENAI_API_KEY=$OPENROUTER_API_KEY
export OPENAI_BASE_URL=https://openrouter.ai/api/v1
export VC_PARSER_LLM_MODEL=meta-llama/llama-3.3-70b-instruct:free

# OpenAI default — no OPENAI_BASE_URL needed
export OPENAI_API_KEY=$OPENAI_API_KEY
export VC_PARSER_LLM_MODEL=gpt-4o-mini       # default if unset
```

Other compatible providers: Together AI, DeepSeek, Fireworks AI, LM Studio (local), vLLM, LiteLLM proxy, etc. See [`src/vc_statement_parser/extractors/llm.py`](src/vc_statement_parser/extractors/llm.py) for the full list and config details.

## 30-second demo

```bash
git clone https://github.com/venturflow/vc-statement-parser.git
cd vc-statement-parser
uv sync --all-extras
uv run python -m examples.fixtures.generate              # fake Standish (LP-PCAP)
uv run python -m examples.fixtures.generate_gaap_scpc    # fake fund-level SCPC
uv run vc-statement-parse examples/fixtures/standish_synthetic.pdf --validate
uv run vc-statement-parse examples/fixtures/gaap_scpc_synthetic.pdf --validate
```

You'll see the parsed JSON plus a verification report:

```text
Verification Report
nav_roll_forward      PASS
commitment_identity   PASS
tvpi_consistency      PASS
dpi_consistency       PASS
```

> Note on invariants: a fund-level GAAP **Statement of Changes in Partners' Capital** (KPMG / CohnReznick layout) doesn't carry the LP-specific `commitment` / `paid_in_capital` / `unfunded_commitment` / `IRR` / `TVPI` / `DPI` fields. The parser leaves those as `None`, and `verify()` skips the invariants whose inputs are unknown rather than failing them — so an SCPC-only parse runs only `nav_roll_forward`. This is by design (see [`docs/ILPA_ALIGNMENT.md`](docs/ILPA_ALIGNMENT.md#optional-fields)).

## Architecture

```
PDF ──► pdfplumber + pypdfium2 ──► raw text + per-page text
            │
            ▼
    dispatcher.detect_administrator()       ← header-signature regex
            │
            ▼
    DETERMINISTIC_EXTRACTORS                ← per-admin templates (the OSS flywheel)
            │   if no match
            ▼
    extractors.llm.extract_with_llm()       ← instructor + OpenAI-compatible
            │
            ▼
    CapitalAccountStatement (Pydantic)      ← ILPA Reporting Template v2.0 vocabulary
            │
            ▼
    verification.verify()                   ← arithmetic invariants, fail loud
```

- **Two extraction paths.** Deterministic regex/layout extractor per administrator (fast, free, audit-friendly) plus an LLM fallback (`instructor` + any OpenAI-compatible API — OpenAI, OpenRouter, Groq, Together, Ollama, LM Studio, vLLM, ...) for unknown formats.
- **Source-grounded.** Every numeric field carries `(page, bbox, source_text)` — pattern borrowed from [google/langextract](https://github.com/google/langextract) — so anything you parse can be traced back to the exact line of the PDF.
- **ILPA-aligned.** Field names follow the [ILPA Reporting Template v2.0](https://ilpa.org/) (mandatory Q1 2026). See [`docs/ILPA_ALIGNMENT.md`](docs/ILPA_ALIGNMENT.md).
- **MIT-licensed core, no copyrighted templates redistributed** — we encode field semantics, not the ILPA artifacts.

## Adding a new administrator

The flywheel: each new admin template added is one fewer LP that has to retype. See **[CONTRIBUTING.md](CONTRIBUTING.md)** for the full step-by-step walkthrough. TL;DR:

1. Generate a synthetic fixture (never commit a real one).
2. Add a header-signature regex to `dispatcher.py`.
3. Subclass `Extractor` and register it in `extractors/__init__.py`.
4. Add a passing pipeline test.

PRs welcome — Gen II, SS&C, Citco, Apex, and Alter Domus are all open seats today.

### Don't want to PR? Ship a plugin.

Internal-only formats (your fund admin's bespoke template, your firm's custom roll-forward) belong in your own private package. Register an `Extractor` against the `vc_statement_parser.extractors` setuptools entry point and `pip install` it — the host parser will discover and use it automatically. See **[docs/PLUGINS.md](docs/PLUGINS.md)**.

### Extending beyond PCAP

The dispatch / extract / verify architecture generalises to capital call notices, distribution notices, K-1 partnership tax forms, fund-level financials, and any other document with redundant arithmetic. See **[docs/EXTENDING.md](docs/EXTENDING.md)** for the design pattern + a cookbook with batch processing, pandas integration, fully-private local-LLM, and scheduled-job recipes.

## Supported formats

| Format | Detector | Extractor | Source provenance |
|---|---|---|---|
| Standish (LP-PCAP) | `STANDISH` | `deterministic.standish` | per-field |
| Auditor-style fund-level "Statement of Changes in Partners' Capital" — KPMG, CohnReznick, Deloitte, EY, PwC layouts | `GAAP_SCPC` | `deterministic.gaap_scpc` | per-field |
| Gen II, SS&C/Geneva, Citco, Apex, Alter Domus | dispatcher signatures wired; deterministic extractors not yet implemented | LLM fallback | n/a until extractor exists |
| Anything else | dispatcher returns `UNKNOWN` | LLM fallback (with `[llm]` extra + `OPENAI_API_KEY` and optional `OPENAI_BASE_URL`) | per-field via `instructor` citations |

The fund-level SCPC parser is an **aggregate** view (the "Limited Partners" column treated as one synthetic LP, `lp_name = "All Limited Partners (Aggregate)"`). It cannot give per-LP figures because the source document doesn't carry them — but it does give a verified roll-forward at the fund level.

## Roadmap

- [x] **v0.1** — synthetic Standish fixture, deterministic extractor, verification layer, CLI, LLM fallback.
- [x] **v0.1.1** — fund-level GAAP SCPC extractor (KPMG / CohnReznick layouts), optional model fields, per-page dispatcher with data-anchor requirement.
- [ ] **v0.2** — Gen II and SS&C deterministic extractors against real-shape sample PDFs (synthetic).
- [ ] **v0.3** — page rasterization → vision-LLM path for image-only statements (`pypdfium2` already wired).
- [ ] **v0.4** — Citco, Apex, Alter Domus templates.
- [ ] **v0.5** — JSON Schema published; ILPA cross-reference doc; HTML viewer for source-grounded review (langextract-style).
- [ ] **v0.6** — capital call notice + distribution notice parsing (sister documents).
- [ ] **v1.0** — stable schema, batched parsing, optional Postgres sink.

## Standing on the shoulders of

Built on top of work this project would not exist without:

- [jsvine/pdfplumber](https://github.com/jsvine/pdfplumber) — primary PDF text/table extractor (MIT)
- [pypdfium2-team/pypdfium2](https://github.com/pypdfium2-team/pypdfium2) — page rasterisation for vision-LLM fallback (Apache-2.0/BSD)
- [jxnl/instructor](https://github.com/jxnl/instructor) — Pydantic-typed LLM extraction with retries, provider-agnostic (MIT)
- [openai/openai-python](https://github.com/openai/openai-python) — official OpenAI client; the wire protocol every modern provider has converged on (Apache-2.0)
- [pydantic/pydantic](https://github.com/pydantic/pydantic) — schema, validation, immutability (MIT)
- [tiangolo/typer](https://github.com/tiangolo/typer) — CLI surface (MIT)
- [google/langextract](https://github.com/google/langextract) — inspiration for source-grounded extraction with per-field citations (Apache-2.0)
- [ILPA Reporting Template v2.0](https://ilpa.org/) — field vocabulary (referenced, not redistributed)

Full prior-art audit, including everything we considered and why we didn't fork an existing project, in [PRIOR_ART.md](PRIOR_ART.md).

## Documentation map

| Doc | When to read it |
|---|---|
| [`README.md`](README.md) (this file) | Install + 30-second demo |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Adding a fund administrator (in-tree) |
| [`docs/PLUGINS.md`](docs/PLUGINS.md) | Shipping an extractor as a separate `pip install` package |
| [`docs/EXTENDING.md`](docs/EXTENDING.md) | Generalising to other finance documents (capital calls, K-1s, fund financials, …) |
| [`docs/ILPA_ALIGNMENT.md`](docs/ILPA_ALIGNMENT.md) | The ILPA Reporting Template v2.0 schema we align with |
| [`docs/PHILOSOPHY.md`](docs/PHILOSOPHY.md) | Why verification-first, why deterministic-first |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Architecture decisions (ADR log) |
| [`SECURITY.md`](SECURITY.md) | Threat model + operator hardening checklist + disclosure path |
| [`CHANGELOG.md`](CHANGELOG.md) | Release notes |

## License

MIT — see [LICENSE](LICENSE).

---

*Maintained by the [VenturFlow](https://venturflow-marketing.vercel.app) team.*
