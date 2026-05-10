# Prior Art Audit — LP Capital Account Statement Parser

Audit goal: confirm whether to greenfield, fork, or plug into existing OSS for parsing LP capital account / PCAP statements from fund administrators (Standish, Gen II, SS&C, Citco, Apex, Alter Domus) into structured JSON, with arithmetic-invariant verification.

## 1. Existing LP / Capital-Account Statement Parsers

- [codereverser/casparser](https://github.com/codereverser/casparser) — License: MIT — What it does: Parses Indian mutual-fund Consolidated Account Statements (CAMS/Karvy/Kfintech). — Gap: Retail mutual funds, not LP/PE PCAP. — Decision: INSPIRE (good template for "per-admin parser" plugin pattern).
- [calvincronin/statement_parser](https://github.com/calvincronin/statement_parser) — License: none/personal — One-off "dad's brokerage statements" PDF→CSV. — Gap: Not LP. — Decision: N/A.
- [electrovir/statement-parser](https://github.com/electrovir/statement-parser) — License: MIT — TS-based bank/credit-card statement parser, per-issuer modules. — Gap: Retail banking. — Decision: INSPIRE (per-issuer adapter pattern is exactly what we need for fund admins).
- [lorenzbr/BankStatementParser](https://github.com/lorenzbr/BankStatementParser) — License: GPL-3.0 — German bank statements → transactions. — Gap: Retail banking, GPL. — Decision: N/A.
- **No GitHub repo found** parsing PCAP / LP capital account statements specifically (searches: "capital account statement parser", "LP statement parser", "PCAP parser private equity", "fund administrator parser"). Closest commercial equivalents — **Canoe Intelligence**, **Allvue Document IQ**, **Arch**, **Aduro Advisors**, **FundCount** — are all proprietary SaaS. There is a clear open-source gap here.

## 2. PDF Table Extraction

- [jsvine/pdfplumber](https://github.com/jsvine/pdfplumber) — License: MIT — ~10k stars — Char-level access; best handling of merged cells and borderless financial tables; lets you build custom column detectors. — Decision: **ADOPT (primary)**.
- [camelot-dev/camelot](https://github.com/camelot-dev/camelot) — License: MIT — Lattice/stream modes; excellent on tables with visible borders, struggles on borderless layouts common in admin statements. — Decision: ADOPT (secondary, for ruled-line statements).
- [chezou/tabula-py](https://github.com/chezou/tabula-py) — License: MIT — Java wrapper; merges adjacent columns more aggressively than Camelot. — Decision: INSPIRE only (JVM dependency is friction).
- [pdfminer/pdfminer.six](https://github.com/pdfminer/pdfminer.six) — License: MIT — Low-level engine that pdfplumber sits on. — Decision: ADOPT (transitive).
- [pypdfium2-team/pypdfium2](https://github.com/pypdfium2-team/pypdfium2) — License: Apache-2.0 / BSD-3-Clause — Fast PDFium bindings, good for rendering pages to images for vision-LLM fallback. — Decision: ADOPT (page-image rasterizer for LLM fallback).
- [Unstructured-IO/unstructured](https://github.com/Unstructured-IO/unstructured) — License: Apache-2.0 — Big-tent ETL: partitions PDFs into elements with layout. Heavy deps (detectron2, OCR models). — Decision: INSPIRE (too heavy as a hard dep; worth offering as an optional backend).
- [run-llama/llama_parse](https://github.com/run-llama/llama_parse) — License: client lib MIT, **service is paid SaaS** ($1.25 per 1k credits, $0.003–$0.075/page). — Strong on financial docs but requires LlamaCloud API key + sends data to their cloud. — Decision: INSPIRE / optional adapter only — incompatible with self-hosted/privacy-sensitive LP data as default.

**Verdict on multi-column financial tables with merged cells:** community consensus and our reading is **pdfplumber > Camelot > Tabula** for this exact shape. pdfplumber + pypdfium2 (for rasterization) covers ~90% of cases; LLM fallback handles the rest.

## 3. LLM Structured-Extraction Frameworks

- [jxnl/instructor](https://github.com/jxnl/instructor) — License: MIT — ~11k stars, 3M+ monthly downloads — Patches Anthropic/OpenAI clients to return Pydantic models; native multimodal (PDF, image, base64); first-class Anthropic support; retries with validation feedback baked in. — Decision: **ADOPT (primary LLM wrapper)**.
- [pydantic/pydantic-ai](https://github.com/pydantic/pydantic-ai) — License: MIT — ~17k stars — Agent framework from the Pydantic team; typed tools, evals, streaming, multi-provider. Heavier than instructor for pure extraction. — Decision: INSPIRE (use if we add agentic verification loops; otherwise overkill).
- [dottxt-ai/outlines](https://github.com/dottxt-ai/outlines) — License: Apache-2.0 — Constrained generation via grammar/regex/JSON-schema; strongest with local/open models, weaker fit for Anthropic API which already does tool-use schema enforcement. — Decision: N/A for our Anthropic-first use case.
- [PrefectHQ/marvin](https://github.com/PrefectHQ/marvin) — License: Apache-2.0 — ~6k stars — Higher-level "ambient AI" abstractions, recently pivoted to agents. Less focused on raw extraction than instructor. — Decision: INSPIRE.
- [google/langextract](https://github.com/google/langextract) — License: Apache-2.0 — ~36k stars — **Source-grounded** extraction with page/coordinate citations and an HTML visualization of where each field came from in the PDF. Built for Gemini but model-agnostic adapters exist. — Decision: **STRONGLY INSPIRE** — the page-citation + HTML-review-UI pattern is exactly the audit trail LPs will demand. We may want to adopt the visualizer or align our output schema with it.

**Verdict:** **instructor** is the cleanest fit for Pydantic + Anthropic + multimodal PDF. We borrow LangExtract's source-grounding pattern (each extracted field carries `{page, bbox, source_text}`).

## 4. Open Cap Format (OCF)

- [Open-Cap-Table-Coalition/Open-Cap-Format-OCF](https://github.com/Open-Cap-Table-Coalition/Open-Cap-Format-OCF) — License: NOASSERTION (free, but not OSI-approved) — JSON-Schema standard for **company-side cap tables**: stock classes, vesting, valuations, transactions, stakeholders. — Gap: **Models the issuer's cap table, not the LP's view of a fund.** No PCAP, capital call, distribution, NAV, IRR/TVPI/DPI, or commitment-tracking objects. The `Valuation` schema is for share-price valuations of a startup, not fund NAV. — Decision: **NOT APPLICABLE**. Different problem domain (VC issuers vs LP-into-fund).
- [jacobyavis/ocf4java](https://github.com/jacobyavis/ocf4java) — License: MIT — Java codegen for OCF. — Decision: N/A.

## 5. ILPA Reporting Templates

- [ILPA Reporting Template v2.0 (Jan 2025)](https://ilpa.org/industry-guidance/templates-standards-model-documents/updated-ilpa-templates-hub/ilpa-reporting-template/) — License: ILPA's own (free download, redistribution restricted). Required for Q1 2026 funds. — XLSX template + PDF guidance + an [XML-compliant definitions doc](https://ilpa.org/resources-tools/resource-library/ilpa-reporting-template-guidance-and-definitions-xml-compliant/). — Gap: ILPA does **not** publish a JSON Schema or open parser, and the XML guidance is a definitions document rather than a runnable schema. — Decision: **ADOPT field semantics** (use ILPA's field names + definitions as our canonical schema vocabulary). No code to consume.
- [ILPA Capital Call & Distribution Notice template (2016)](https://ilpa.org/wp-content/uploads/2016/10/ILPA-Capital-Call-Distribution-Notice-Best-Practices-October-2016.pdf) — Same disposition: align field names, no code exists.
- **No GitHub project found** that consumes or produces ILPA templates programmatically. Another clear gap.

## 6. Carta / Pulley / AngelList LP-Side OSS

- [captableinc/captable](https://github.com/captableinc/captable) — License: AGPL-3.0 — "Open-source Carta alternative" — issuer cap table, not LP statements. — Decision: N/A (wrong side of the table; AGPL also a constraint).
- No open-source LP-side reporting / NAV-statement project found from Carta, Pulley, AngelList, or comparable.

## 7. Pitchbook / CB Insights / Preqin

No public machine-readable schema. All three are proprietary data subscriptions. No reuse opportunity.

## 8. Generic Financial Statement Parsers (XBRL / 10-K)

- [Arelle/Arelle](https://github.com/Arelle/Arelle) — License: Apache-2.0 — ~200 stars — Mature XBRL platform (validate, query, transform). — Gap: XBRL is for SEC filings (10-K/Q), not PE admin PDFs. — Decision: N/A.
- [manusimidt/py-xbrl](https://github.com/manusimidt/py-xbrl) — License: **GPL-3.0** — XBRL parser. — Decision: N/A (GPL + wrong format).
- [runaphasia335/Financial-Statement-Parsers](https://github.com/runaphasia335/Financial-Statement-Parsers) — Hobby-tier 10-K PDF parser. — Decision: N/A.
- [JerBouma/FinanceToolkit](https://github.com/JerBouma/FinanceToolkit) — License: MIT — Public-equity ratio analysis on top of public filings. — Decision: N/A.

## 9. Fund-Admin Published Schemas

- **SS&C** ([developer.ssctech.com](https://developer.ssctech.com/)) — Has an APIM portal for some products, but no public LP-statement schema. Geneva, Investran, Black Diamond export formats are customer-only and proprietary. — Decision: N/A.
- **FIS Investran "DX" (Data Exchange)** — Customer-side reporting product, no public schema.
- **Citco One**, **Apex**, **Alter Domus**, **Standish**, **Gen II** — None publish a developer portal or open schema for LP statements as of this audit. Each ships PDFs with their own layout. This is precisely why our project exists: **per-admin templates are the moat**.
- Decision across the board: **N/A** — but the absence confirms market need.

## 10. Reference Repos for Python OSS Scaffolding

- [pydantic/pydantic](https://github.com/pydantic/pydantic) — License: MIT — `pyproject.toml` with hatchling build, ruff + mypy, mkdocs-material. — Decision: ADOPT (copy structure).
- [tiangolo/typer](https://github.com/tiangolo/typer) — License: MIT — Clean CLI scaffold. — Decision: ADOPT for our CLI surface.
- [tiangolo/fastapi](https://github.com/tiangolo/fastapi) — License: MIT — README/docs hierarchy reference if we ever expose an HTTP service. — Decision: INSPIRE.
- [jxnl/instructor](https://github.com/jxnl/instructor) — Already in §3 — best example of a small, focused library wrapping LLM calls with strong docs. — Decision: ADOPT (closest spiritual sibling — copy README/cookbook structure).

---

## RECOMMENDATION

**1. PDF library — primary:** **pdfplumber (MIT)**, with **pypdfium2 (Apache-2.0/BSD)** for page rasterization when we need to hand a page to a vision LLM. Camelot stays as an optional secondary backend for ruled-line statements.

**2. LLM extraction framework:** **instructor (MIT)**. It owns the Pydantic + Anthropic + multimodal-PDF intersection cleanly; retries with validation feedback are built-in. Borrow the **source-grounding metadata pattern from google/langextract** so every extracted field carries `(page, bbox, source_text)` — that becomes the audit trail the verification layer hangs off.

**3. Schema alignment:** Do **not** align to OCF — wrong domain (issuer cap table, not LP-into-fund). **Do** align field names and definitions to **ILPA Reporting Template v2.0** (Jan 2025, mandatory Q1 2026). ILPA gives us the vocabulary; we provide the JSON Schema and the parser. This is a real wedge — nobody has done it.

**4. Fork vs greenfield:** **Greenfield.** The four searches we ran (capital account statement parser, LP statement parser, PCAP parser, fund administrator parser) returned zero meaningful prior art. Adjacent OSS (casparser, electrovir/statement-parser) is worth studying for the per-issuer adapter pattern but isn't a fork base. Commercial incumbents (Canoe, Allvue Document IQ, Arch) are closed SaaS — they validate the market without occupying the OSS slot.

**5. Bottom line:** **Build greenfield, depend heavily on existing libs.** The recipe:

```
pdfplumber + pypdfium2          → text/table/image extraction
  → instructor + OpenAI-compat   → Pydantic-typed extraction with retries
    → langextract-style citations → page/bbox grounding for every field
      → our verification layer    → arithmetic invariants (opening + calls
                                    − distributions + P&L = closing, etc.)
        → per-admin template pack → Standish, Gen II, SS&C, Citco, Apex,
                                    Alter Domus prompt + schema overrides
          → output: ILPA-aligned JSON + verification report
```

The differentiating wedge — **arithmetic-invariant verification + per-admin templates aligned to ILPA v2.0** — does not exist in OSS today. The infrastructure (PDF + LLM extraction libs) is mature and MIT/Apache-licensed. We are a thin, well-tested wrapper plus the parts nobody has bothered to standardize.

**License posture:** ship under **Apache-2.0 or MIT**. All core dependencies above are MIT/Apache/BSD-compatible. Avoid the GPL-licensed py-xbrl and AGPL captable. ILPA template materials are referenced, not redistributed — we encode field names and definitions, not the copyrighted XLSX/PDF artifacts.
