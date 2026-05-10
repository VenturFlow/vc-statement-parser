# ILPA Reporting Template v2.0 — field-by-field alignment

`vc-statement-parser` aligns its schema to the [ILPA Reporting Template v2.0](https://ilpa.org/industry-guidance/templates-standards-model-documents/updated-ilpa-templates-hub/ilpa-reporting-template/) (released January 2025; mandatory Q1 2026 reporting). ILPA does not publish a JSON Schema — we encode their **field semantics** here, not their copyrighted XLSX or PDF artifacts. Where ILPA labels and our model field names diverge, this table is authoritative.

| Our field (`CapitalAccountStatement`) | ILPA term                                                  | Sign / unit                                  |
| ------------------------------------- | ---------------------------------------------------------- | -------------------------------------------- |
| Our field (`CapitalAccountStatement`) | ILPA term                                                  | Required? | Sign / unit                                  |
| ------------------------------------- | ---------------------------------------------------------- | --------- | -------------------------------------------- |
| `lp_name`                             | Limited Partner                                            | required  | string                                       |
| `fund_name`                           | Fund                                                       | required  | string                                       |
| `period_start`                        | Period Beginning                                           | required  | ISO-8601 date                                |
| `period_end`                          | Period Ending                                              | required  | ISO-8601 date                                |
| `as_of_date`                          | As Of Date                                                 | required  | ISO-8601 date                                |
| `commitment`                          | Total Commitment                                           | optional  | positive Decimal (USD or fund currency)      |
| `paid_in_capital`                     | Cumulative Capital Called / Paid-in Capital                | optional  | positive Decimal                             |
| `unfunded_commitment`                 | Unfunded Commitment / Remaining Commitment                 | optional  | positive Decimal                             |
| `distributions`                       | Cumulative Distributions                                   | optional  | positive magnitude (life-to-date)            |
| `nav_beginning`                       | Beginning Balance (Net Asset Value)                        | required  | Decimal, can be negative                     |
| `contributions_period`                | Capital Contributions (period)                             | required  | positive magnitude                           |
| `distributions_period`                | Distributions (period)                                     | required  | positive magnitude — sign applied internally |
| `nav_ending`                          | Ending Balance (Net Asset Value)                           | required  | Decimal, can be negative                     |
| `realized_gain_loss`                  | Realized Gains/(Losses)                                    | required  | signed Decimal                               |
| `unrealized_gain_loss`                | Unrealized Gains/(Losses) / Change in Unrealized Valuation | required  | signed Decimal                               |
| `management_fees`                     | Management Fees                                            | optional  | positive magnitude — subtracted in NAV roll  |
| `partnership_expenses`                | Partnership Expenses                                       | optional  | positive magnitude — subtracted in NAV roll  |
| `irr_net`                             | Net IRR                                                    | optional  | decimal multiple (`0.185` for 18.5%)         |
| `tvpi_net`                            | Net TVPI                                                   | optional  | decimal multiple (`1.54` for 1.54×)          |
| `dpi_net`                             | Net DPI                                                    | optional  | decimal multiple                             |
| `transactions[]`                      | Transactional Activity (period)                            | optional  | list of `Transaction`                        |
| `source_metadata`                     | (parser provenance — not in ILPA)                          | required  | `SourceMetadata`                             |

## Optional fields

The "Required?" column above reflects what an LP-specific PCAP statement carries. For **fund-level** GAAP "Statement of Changes in Partners' Capital" documents (the layout used by KPMG, CohnReznick, Deloitte, EY, and PwC in their illustrative templates, and by GPs producing audited fund-level financials), the LP-specific columns simply don't exist on the page — the statement aggregates across all Limited Partners.

When the GAAP_SCPC extractor parses such a document, the optional fields are left as `None`:

- `commitment`, `paid_in_capital`, `unfunded_commitment` — there is no LP-specific commitment on a fund-level SCPC.
- `distributions` (cumulative) — only the period flow is reported.
- `management_fees`, `partnership_expenses` — fees are commingled into "Net investment loss" on most SCPC layouts; the extractor leaves `management_fees = 0` and rolls "Net investment loss" + "Carried interest to GP" into `partnership_expenses` so the NAV roll-forward identity still balances.
- `irr_net`, `tvpi_net`, `dpi_net` — performance ratios are presented to LPs separately, not on the SCPC.

`verify()` skips any invariant whose inputs are `None` rather than failing it — so an SCPC-only parse runs `nav_roll_forward` and skips `commitment_identity` / `tvpi_consistency` / `dpi_consistency`. This is intentional and matches the existing skip-when-missing pattern already used for `tvpi_net` / `dpi_net` on Standish-style statements.

## Sign conventions

All flow magnitudes are stored as **positive numbers**; sign is implied by the field's role in the NAV roll-forward identity:

```
nav_ending = nav_beginning
           + contributions_period
           - distributions_period
           + realized_gain_loss
           + unrealized_gain_loss
           - management_fees
           - partnership_expenses
```

`realized_gain_loss` and `unrealized_gain_loss` are the exception — they are signed because gains and losses both occur and the sign carries information.

## Performance multiples

ILPA presents IRR as a percentage (`18.50%`) and TVPI / DPI as a multiple (`1.54x`). Our schema stores all three as plain `Decimal` ratios:

- `irr_net = 0.185` (i.e. 18.5% expressed as decimal)
- `tvpi_net = 1.54`
- `dpi_net = 0.34`

The CLI's `--format=table` renders them in their conventional display form.

## What we deliberately don't model (yet)

- **Capital Call & Distribution Notices** — the ILPA Capital Call & Distribution Notice template (2016) is a separate document with its own schema. Planned for v0.6.
- **Look-through fund-of-funds reporting** — investor → master → underlying fund hierarchies. Out of scope for v0.x.
- **Side-letter economics** — the ILPA template covers the headline economics, not LP-specific carve-outs. We surface what the statement reports.

## Open questions

If you spot a place where ILPA v2.0's field semantics conflict with ours, please open an issue. We will defer to ILPA in any genuine conflict.
