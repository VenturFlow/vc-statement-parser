# Extending the framework to other finance documents

`vc-statement-parser` was designed for one document type — the LP capital
account statement (PCAP). But the architecture under the surface is
generic, and we deliberately want to make it reusable for other documents
in the same family. This page is the map for that.

## The three pillars

Every parser in this codebase follows the same shape:

```text
PDF ─► dispatcher.detect_administrator()  ─► extractor.extract()  ─► verify()
        (header signatures + anchors)        (regex / layout)         (arithmetic invariants)
```

| Pillar | What it does | What you replace per document type |
|---|---|---|
| **Dispatch** | "Which template am I looking at?" | Add header signatures + (optionally) data-row anchors per document type. |
| **Extract** | "Get the typed fields out." | Subclass the per-document `Extractor`. |
| **Verify** | "Is the math internally consistent?" | Define identities specific to the document. |

The most valuable part is **verify**. Most parsers stop at extraction;
ours treats verification as a first-class wedge because every finance
document has redundant arithmetic that catches both bad scans and bad math.

---

## Worked example: capital call notices

A capital call notice has the same architectural shape:

| Pillar | PCAP statement | Capital call notice |
|---|---|---|
| Dispatch heading | "Capital Account Statement" | "Capital Call Notice" / "Drawdown Notice" |
| Data anchor | "Beginning Balance" / "Total Commitment" | "Amount Due" / "Wire Instructions" |
| Required fields | LP name, fund, period, NAV begin/end, … | LP name, fund, call date, call number, amount, wire instructions, due date |
| Arithmetic invariants | NAV roll-forward, commitment identity, TVPI/DPI consistency | `cumulative_called_to_date == previous_cumulative + this_call`, `unfunded_after == commitment - cumulative_called_to_date` |

Implementation steps:

1. **Add a new top-level model.** In `src/vc_statement_parser/models.py`
   (or a new sibling module — split when it gets noisy):

   ```python
   class CapitalCallNotice(BaseModel):
       model_config = ConfigDict(frozen=True)

       lp_name: str
       fund_name: str
       call_number: int
       call_date: date
       due_date: date
       amount_called: Decimal
       cumulative_called: Decimal
       unfunded_after: Decimal
       commitment: Decimal | None = None  # may not appear on the notice itself
       wire_instructions: WireInstructions | None = None
       source_metadata: SourceMetadata
   ```

2. **Add a `DocumentType` discriminator** so a single CLI invocation can
   route between PCAP and capital-call documents:

   ```python
   class DocumentType(StrEnum):
       PCAP_STATEMENT = "pcap_statement"
       CAPITAL_CALL_NOTICE = "capital_call_notice"
       DISTRIBUTION_NOTICE = "distribution_notice"
       K1_PARTNERSHIP_TAX = "k1_partnership_tax"
       FUND_LEVEL_FINANCIALS = "fund_level_financials"
   ```

   The dispatcher would first detect the document type, then the
   administrator within that type.

3. **Add invariants in a dedicated module.** A capital call notice has
   simpler math than a PCAP — typically two identities:

   ```python
   def verify_capital_call(notice: CapitalCallNotice) -> ValidationReport:
       results = []
       # commitment identity (when commitment is present)
       if notice.commitment is not None:
           results.append(_check(
               name="unfunded_consistency",
               expected=notice.commitment - notice.cumulative_called,
               actual=notice.unfunded_after,
               tolerance=DEFAULT_DOLLAR_TOLERANCE,
           ))
       # cumulative-called identity — requires the previous notice's
       # cumulative figure as input. The verifier accepts an optional
       # `prior` argument for this case.
       ...
   ```

4. **Reuse what's reusable.** `_pdf.read_pdf_text`, the `dispatcher`
   header-region scan, the entry-point plugin loader, the source-grounding
   `FieldSource` pattern, and the CLI batch-mode + JSON-summary all
   work unchanged. You write only the model, the extractor, and the
   invariants.

---

## Document types we anticipate

The ones below are sized roughly by how much code they share with the
existing PCAP path. Items higher in the list re-use the most.

| Document | Notes | Effort |
|---|---|---|
| **Capital call notice** | Per-LP wire instructions, called amount, due date. Simpler math than PCAP; same "find admin signature, find data anchor" dispatch shape. | small |
| **Distribution notice** | Mirror of capital call — distributed amount, source (return-of-capital vs. realized-gain) breakdown, tax characterization. | small |
| **Fund-level financial statements** | Statement of Operations + Schedule of Investments + Notes. We already parse the SCPC page; extending to the full audited financial set is mostly more extractors. | medium |
| **Schedule K-1** | IRS partnership tax form. Highly structured (box-numbered fields). Best parsed with a position-based extractor rather than text regex. | medium |
| **PPM / Subscription docs** | Less arithmetic to verify, more clause extraction. The `verify()` philosophy doesn't transfer cleanly — closer to a contract-extraction product. | large |
| **GP financial statements** | Different schema entirely; better as a sister project that imports the dispatch + invariant utilities. | large |

If you start one of these, please open an issue first so we can align on
the model shape and invariants before code review.

---

## Generalising verification beyond PCAP

The wedge is "redundant arithmetic that the document declares about
itself". Anywhere a financial document carries multiple numbers that must
satisfy an identity, an invariant is possible.

Examples beyond PCAP NAV roll-forward:

| Document | Invariants you can declare |
|---|---|
| Capital call notice | `cumulative_called == previous_cumulative + this_call`, `unfunded == commitment - cumulative_called` |
| Distribution notice | `total_distribution == sum(distribution_components)`, `cumulative_distributions_after == previous + this_distribution` |
| Schedule of Investments | `sum(cost_basis) == fund.total_cost_basis`, `sum(fair_value) == fund.total_fair_value` |
| K-1 | `sum(partner_capital_after) == fund.partners_capital_total`, partner % allocations sum to 100% within rounding |
| Fund financials | balance-sheet balance (assets == liabilities + partners' capital), income-statement bottom-line consistency |

Each of these takes 5-10 lines of code in the same shape as
[`verification.py`](../src/vc_statement_parser/verification.py). The hard
part isn't the invariant — it's identifying which fields are redundantly
expressed in the source document.

---

## Cookbook

### Recipe 1: batch-process a directory and pipe to jq

```bash
# Process every PDF in the inbox, emit JSONL summaries, count failures.
vc-statement-parse inbox/*.pdf --json-summary --no-llm \
  | jq -r 'select(.ok == false) | .file'
```

### Recipe 2: load all parsed statements into a pandas DataFrame

```python
from pathlib import Path
import pandas as pd
from vc_statement_parser import parse_statement, verify

records = []
for pdf in Path("inbox").glob("*.pdf"):
    try:
        s = parse_statement(pdf, use_llm_fallback=False)
    except Exception as e:                    # noqa: BLE001 — record-and-continue
        records.append({"file": pdf.name, "ok": False, "error": str(e)})
        continue
    report = verify(s)
    records.append({
        "file": pdf.name,
        "ok": report.passed,
        "fund": s.fund_name,
        "lp": s.lp_name,
        "period_end": s.period_end,
        "nav_ending": float(s.nav_ending),
        "commitment": float(s.commitment) if s.commitment is not None else None,
        "administrator": s.source_metadata.administrator.value,
        "extractor": s.source_metadata.extractor,
        "confidence": s.source_metadata.parse_confidence,
    })

df = pd.DataFrame(records)
df.to_parquet("statements.parquet")
```

### Recipe 3: run a fully-private parse with local LLM fallback

```bash
# Start Ollama in a separate terminal: ollama serve, then ollama pull llama3.2
export OPENAI_API_KEY=ollama          # any non-empty token works
export OPENAI_BASE_URL=http://localhost:11434/v1
export VC_PARSER_LLM_MODEL=llama3.2

vc-statement-parse confidential.pdf --validate
# No data leaves your laptop.
```

### Recipe 4: write a custom invariant for your fund's quirks

```python
# Some funds report "non-cash distributions" separately. Verify they net out.
from decimal import Decimal
from vc_statement_parser.verification import _check, ValidationReport

def verify_non_cash_distributions(statement, *, non_cash: Decimal) -> ValidationReport:
    return ValidationReport(results=(
        _check(
            name="non_cash_distribution_consistency",
            description="distributions_period == cash + non_cash",
            expected=statement.distributions_period,
            actual=cash_distributions + non_cash,
            tolerance=Decimal("1.00"),
        ),
    ))
```

### Recipe 5: scheduled overnight job (systemd timer)

```ini
# /etc/systemd/system/vc-parse-inbox.service
[Service]
Type=oneshot
Environment=OPENAI_BASE_URL=http://localhost:11434/v1
Environment=OPENAI_API_KEY=ollama
ExecStart=/usr/bin/bash -c 'vc-statement-parse /srv/inbox/*.pdf --json-summary --no-llm \
  > /srv/inbox/results-$(date +%%F).jsonl 2>&1'
```

---

## See also

- [`docs/PLUGINS.md`](PLUGINS.md) — for shipping extractors as pip packages
- [`docs/ILPA_ALIGNMENT.md`](ILPA_ALIGNMENT.md) — the ILPA Reporting Template v2.0 schema we already align with
- [`docs/DECISIONS.md`](DECISIONS.md) — architectural rationale, especially the "make fields Optional" entry
- [`SECURITY.md`](../SECURITY.md) — threat model & operator hardening checklist
