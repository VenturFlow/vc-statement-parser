# Philosophy: parsing without verification is the verification desert

A capital account statement is a small piece of arithmetic surrounded by branding. Every redacted PDF, every faxed-from-2003 layout, every "we updated our template again" email is a thin wrapper around the same handful of identities:

```
nav_beginning
    + contributions
    − distributions
    + realized_gain_loss
    + unrealized_gain_loss
    − management_fees
    − partnership_expenses
    = nav_ending

paid_in_capital + unfunded_commitment = total_commitment

tvpi_net = (nav_ending + cumulative_distributions) / paid_in_capital

dpi_net  = cumulative_distributions / paid_in_capital
```

If those identities don't hold, one of three things is true:

1. **The parse failed.** A column got merged. A negative was read as positive. A footnote was read as a number.
2. **The administrator made a typo.** Rare but real. We've seen it.
3. **The reporting standard drifted** (a fee got reclassified between footnotes and the activity block; a "carried interest reserve" line was added).

In all three cases, the LP wants to know — *before* the number lands in their reporting system, their LP-quarter board pack, or their portfolio analytics.

## Why this is "the verification desert"

The commercial market for LP statement parsing (Canoe Intelligence, Allvue Document IQ, Arch, Aduro) has converged on a "we'll get it 95% right and you trust us" SLA. That works for some workflows. It is dangerous for others — endowments, pensions, and family offices that *publish* numbers downstream. Their audit chain ends at "the document said so." There is no easy way for them to ask the system: *did the arithmetic close?*

That gap — between **extraction** and **verification** — is where bad numbers live. Open source has under-served it because the obvious thing to build is "another extractor." The non-obvious thing is to make verification a first-class concern, fail loudly, and surface the smallest possible discrepancy with full provenance.

## Design consequences

The philosophy translates into four concrete commitments:

1. **Every numeric field is source-grounded.** A parsed `nav_ending` carries a `(page, bbox, source_text)` triplet so a reviewer can jump from the parsed JSON to the exact pixel range it came from. Pattern borrowed from [google/langextract](https://github.com/google/langextract).
2. **Verification is built-in.** `parse_statement` returns the data; `verify` returns a `ValidationReport`. They are separate functions on purpose — extraction is opinionated, verification is universal.
3. **Tolerances are tunable but explicit.** Default is $1 absolute on dollar identities, 0.05 on multiple identities. A workflow that publishes to LPACs may want $0.01 and 0.001. A workflow that reconciles against a custodian may accept $100. The decision is yours; the default fails loud.
4. **Per-administrator templates are the moat.** A deterministic regex extractor for one admin is more auditable, faster, and cheaper than any LLM call. The LLM fallback is for the long tail.

## What this is *not*

This isn't a portfolio analytics engine. It isn't a fund accounting system. It isn't a substitute for your administrator's own ledger.

It's the layer that turns a PDF into a number you can trust — and tells you when you can't.
