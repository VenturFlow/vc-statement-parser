# `examples/real_world/` — provenance rules

The PDFs in this directory are intentionally committed to the repository as
**reference fixtures** for the parser. They are also the only category of
input file we keep checked in.

## What MAY live here

Only documents that meet ALL of the following:

1. **Publicly published** — anyone can download them from the original
   source's public website without authentication, payment, or signing an
   NDA.
2. **Not LP-specific** — illustrative templates, guidance documents, sample
   fund-level financial statements, or freedom-of-information disclosures.
   No document that names a real Limited Partner alongside their actual
   capital balance.
3. **License-compatible** — re-distribution permitted by the source's terms,
   OR fair-use as documentation/test fixture (we cite the source URL in
   our README and never claim authorship).

## Currently committed fixtures

| File | Source | Type |
|---|---|---|
| `kpmg_pe_illustrative_2023.pdf` | KPMG public illustrative financial statements (2023) | auditor template |
| `kpmg_pcap_p9.pdf` | Page 9 of the KPMG PDF above | auditor template excerpt |
| `cohnreznick_pe_illustrative_2024.pdf` | CohnReznick public illustrative financial statements (2024) | auditor template |
| `ilpa_reporting_template_v2_guidance.pdf` | ILPA Reporting Template v2.0 Guidance (Jan 2025) | industry guidance |
| `pa_sers_ilpa_template_v1_1.pdf` | PA SERS public filing of ILPA Reporting Template Guidance v1.1 | industry guidance |

## What MUST NEVER live here

- A real LP's quarterly capital account statement, even if their name is
  redacted by hand. Static redaction is unreliable; metadata, embedded XMP,
  or visible layout artifacts can re-identify the LP. Use the synthetic
  fixture generator (`examples/fixtures/generate.py` or
  `examples/fixtures/generate_gaap_scpc.py`) instead.
- A statement marked "CONFIDENTIAL", "Internal Use Only", "Proprietary",
  "Limited Distribution", or similar.
- Anything pulled from a Drive / Dropbox / Box link that required login.
- Vendor-internal PDF templates that you happen to have access to via your
  employer.

The `.gitignore` at the repo root has defensive name-pattern guards
(`*.real.pdf`, `*.private.pdf`, `*.confidential.pdf`, `*.lp.pdf`,
`examples/real_world/private_*`, etc.) that block the common slip-ups, but
the gitignore is a last line of defense — the first line is your judgement
when staging a file.

## If you accidentally commit one

Stop, do not push, and follow the procedure in [`SECURITY.md`](../../SECURITY.md).
For information that already reached `origin`, force-push removal alone is
insufficient — assume the data is exposed and notify the LP whose data was
involved.
