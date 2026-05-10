# Architecture decisions

A running log of design choices that future contributors (and future me) will
want context on. New entries go on top.

---

## 2026-05 — LLM fallback switched to OpenAI-compatible API (was Anthropic-only)

**Context.** The original LLM fallback used `instructor.from_anthropic()` and
required an `ANTHROPIC_API_KEY`. That choice locked anyone who wanted to
self-host (Ollama, LM Studio, vLLM), use a free tier (OpenRouter, Groq), or
pick a different vendor (OpenAI, DeepSeek, Together, Fireworks) into either
paying Anthropic or not using the fallback at all. The deterministic core is
the project's main value prop, but the fallback should not be a vendor lock.

**Decision.** Switch to `instructor.from_openai(OpenAI(...))` — the OpenAI
Chat Completions wire protocol is the de facto standard every modern provider
implements. Configuration is via three env vars:

  * `OPENAI_API_KEY` — required
  * `OPENAI_BASE_URL` — optional; points at any OpenAI-compatible endpoint
  * `VC_PARSER_LLM_MODEL` — optional; defaults to `gpt-4o-mini`

This makes the fallback work, with no code changes, against:

  * OpenAI (default)
  * OpenRouter, Groq, Together, DeepSeek, Fireworks AI (cloud, often with free tiers)
  * Ollama, LM Studio, vLLM (local, fully free, fully private)
  * LiteLLM proxy (route to any backend, including Anthropic via the OpenAI-compatible
    adapter — so the original Claude path is still reachable, just one hop away)

**Trade-offs.**

  * The Anthropic SDK and prompt-caching / tool-use specifics are no longer
    directly addressable. Users who want Claude can route through LiteLLM or
    OpenRouter. Acceptable: the LLM fallback is a long-tail safety net, not
    the project's primary value.
  * Default model `gpt-4o-mini` requires a paid OpenAI account out of the box.
    The README documents the local / free-tier alternatives prominently.

**Validation.** `pip install 'vc-statement-parser[llm]'` now installs `openai`
instead of `anthropic`; the `LLMExtractionUnavailableError` message lists the
compatible providers; deterministic extractors and tests are unaffected
(61/61 still pass).

---

## 2026-05 — LP-specific fields made Optional in `CapitalAccountStatement`

**Context.** The original schema followed the ILPA Reporting Template v2.0
exactly: every numeric field was a required `Decimal`. This worked perfectly
for the LP-PCAP statements admins like Standish ship to individual LPs. It
broke the moment we tried to parse a fund-level GAAP **Statement of Changes
in Partners' Capital** (the layout published by KPMG, CohnReznick, Deloitte,
EY, PwC in their illustrative templates and used by GPs in audited fund-level
financials). Those documents aggregate across all Limited Partners — there
is no single LP, no LP commitment, no LP-specific paid-in / unfunded /
cumulative distributions / IRR / TVPI / DPI on the page.

**Decision.** Make the LP-specific fields optional with `None` defaults:

- `commitment`
- `paid_in_capital`
- `unfunded_commitment`
- `distributions` (cumulative life-to-date)
- `management_fees`
- `partnership_expenses`

Update `verify()` to skip any invariant whose inputs are `None` rather than
failing it. This extends the existing skip-when-missing pattern that already
applied to `tvpi_net` / `dpi_net` (which were already optional).

**Alternatives considered.**

1. *A separate `FundLevelStatementOfChanges` model.* Cleanest semantically but
   forces every downstream caller to handle two output types. Not worth it for
   what is in practice the same shape minus six fields.
2. *Synthesise zeros for missing fields.* Tempting but dishonest — `verify()`
   would silently pass against fabricated `commitment_identity` of `0 + 0 == 0`.
3. *Reject SCPC documents at the dispatcher level.* Defeats the purpose of
   adding the extractor in the first place.

**Trade-offs.**

- Type narrowing: callers that previously assumed a `Decimal` now must handle
  `Decimal | None`. Existing consumers (the CLI's `--format=table` path) were
  updated to print `—` for missing fields rather than crashing.
- Schema instability: this is a real public-API change. Justifiable now (the
  project has zero releases on PyPI and zero git commits) and will not be
  doable cleanly post-1.0.

**Validation.** All four real-world fixtures still verify the invariants that
apply to them:

| Fixture | nav_roll_forward | commitment_identity | TVPI/DPI |
|---|---|---|---|
| Standish synthetic | PASS | PASS | PASS |
| GAAP_SCPC synthetic | PASS | skipped | skipped |
| KPMG illustrative p9 | PASS | skipped | skipped |
| CohnReznick illustrative | PASS | skipped | skipped |

---

## 2026-05 — Dispatcher restricted to per-page header regions + data anchors

**Context.** The first pass scanned the entire concatenated document text for
admin signatures. An ILPA reporting-template guidance PDF (which lists "Citco
/ Gen II / SS&C" as example vendors in its prose) was misclassified as Gen II.
Long audited annual reports embed the SCPC heading in their table of contents
and page-running headers, so a heading-only check would also misclassify the
TOC page as the actual statement.

**Decision.** Two changes to `dispatcher.detect_administrator`:

1. Scan only the first ~1500 chars (the "header region") of each page, not
   the whole document. Admin signatures live in letterheads / footers of
   page 1, not in page-9 prose.
2. For administrators whose heading text legitimately appears outside the
   actual statement (currently just `GAAP_SCPC`), require an *additional*
   data-row anchor (e.g. "Partners' capital, beginning of year") on the same
   page. The anchor is searched across the full page, not just the header
   region — it has to be on the SAME page as the heading, but not necessarily
   close to it.

The dispatcher signature now takes an optional `per_page_text: list[str]`
parameter, defaulting to scanning the whole concatenated text when not
supplied. `parse_statement` always passes per-page text.

---

## 2026-05 — `20XX` placeholder year mapped to `2099`

**Context.** Auditor illustrative templates (KPMG, CohnReznick) use the
literal string `"20XX"` as a placeholder year in headings like "Year ended
December 31, 20XX". Real fund deliveries substitute the actual year before
shipping. The parser needs to handle the placeholder so the extracted
`CapitalAccountStatement` is well-formed.

**Decision.** Substitute `20XX → 2099` in the GAAP_SCPC extractor's period
parser. `2099` is unambiguously fictitious (no real fund year-end will ever
be 2099) and signals "this came from a placeholder template" without
crashing the model's date validation.

---
