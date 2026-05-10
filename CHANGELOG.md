# Changelog

All notable changes to this project will be documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **GAAP Statement of Changes in Partners' Capital extractor** for KPMG /
  CohnReznick / Deloitte / EY / PwC illustrative templates and any GP-issued
  fund-level financial. New `FundAdministrator.GAAP_SCPC`,
  `extractors.gaap_scpc.GaapScpcExtractor`. Handles multi-line wrapped
  labels, reportlab whitespace bugs, em-dash zero placeholders, and the
  `20XX` placeholder year.
- **Synthetic SCPC fixture generator** at
  `examples/fixtures/generate_gaap_scpc.py`, mirroring the Standish
  generator pattern.
- **Per-page dispatcher** with PCAP data-row anchors. Eliminates false
  positives where an admin name appears in a vendor list or research-paper
  citation rather than on an actual statement page.
- **OpenAI-compatible LLM fallback** — was Anthropic-only. Now works with
  any OpenAI-Chat-Completions provider (OpenAI, OpenRouter, Groq, Together,
  DeepSeek, Fireworks, Ollama, LM Studio, vLLM, LiteLLM proxy). Configure
  via `OPENAI_API_KEY` + `OPENAI_BASE_URL` + `VC_PARSER_LLM_MODEL`.
- **`SECURITY.md`** with disclosure path, threat model, and operator
  hardening checklist.
- **`docs/DECISIONS.md`** ADR log — captures the rationale for the optional
  fields, the dispatcher tightening, the 20XX→2099 mapping, and the
  Anthropic→OpenAI-compatible swap.
- **`docs/PLUGINS.md`** and entry-point based plugin discovery — third
  parties can ship extractors as separate `pip install` packages.
- **`docs/EXTENDING.md`** — generalising the framework to non-PCAP
  document types (capital call notices, distribution notices, K-1s).
- **CLI batch mode** — `vc-statement-parse a.pdf b.pdf c.pdf` plus
  `--json-summary` for newline-delimited JSON pipelines.
- **Pre-commit configuration** — `ruff` + `ruff-format` hooks.
- **GitHub issue + PR templates**.

### Changed
- LP-specific fields (`commitment`, `paid_in_capital`, `unfunded_commitment`,
  `distributions`, `management_fees`, `partnership_expenses`) are now
  Optional with `None` default. Verification skips invariants whose inputs
  are unknown rather than failing them. Required for fund-level SCPC support.
- Renamed `LLMExtractionUnavailable` → `LLMExtractionUnavailableError` (PEP-8
  exception naming). Old name kept as a deprecated alias.
- Switched `FundAdministrator` and `TransactionType` from `(str, Enum)` to
  `StrEnum` (Python 3.11+).
- CLI table output now prints `—` for unset Optional fields instead of
  crashing with `None` formatting.
- Ruff `S` (bandit) ruleset enabled in `src/`.

### Removed
- Hard dependency on `anthropic`. Dropped from `[llm]` and `dev` extras in
  favour of `openai>=1.0`. Migration guidance: `pip install
  'vc-statement-parser[llm]'` no longer ships `anthropic`. Set
  `OPENAI_BASE_URL` to route to Anthropic via OpenRouter or LiteLLM.

### Fixed
- Dispatcher false-positive on the ILPA Reporting Template Guidance v2 PDF
  (was misclassified as `gen_ii` because of a "Gen II" mention in the
  Steering Committee vendor list at char 600 of page 6). Dispatcher now
  requires both an admin signature AND a PCAP data anchor on the same page.

## [0.1.0] - TBD

Initial release. Standish extractor, verification layer, CLI, Anthropic-based
LLM fallback. (Never tagged on PyPI.)
