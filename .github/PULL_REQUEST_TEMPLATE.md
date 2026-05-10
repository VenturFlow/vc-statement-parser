<!--
Thanks for the PR! A few quick guides:

  - For new administrators, see CONTRIBUTING.md "Step-by-step: adding a new
    administrator".
  - For new document types beyond PCAP, see docs/EXTENDING.md.
  - DO NOT include real LP statements anywhere — see CONTRIBUTING.md → Privacy.
-->

## Summary

<!-- One or two sentences. What does this PR do, and why? -->

## Type of change

- [ ] New deterministic extractor for an administrator
- [ ] New / improved arithmetic invariant in `verification.py`
- [ ] Bug fix (with regression test)
- [ ] Documentation
- [ ] Refactor / chore (no behavior change)
- [ ] Other (describe)

## Checklist

- [ ] `uv run pytest` passes locally
- [ ] `uv run ruff check src tests examples` is clean
- [ ] `uv run ruff format --check src tests examples` is clean
- [ ] If user-visible behavior changed: `CHANGELOG.md` updated under
      `[Unreleased]`
- [ ] If a new admin was added: `README.md` "Supported formats" table
      updated and a synthetic fixture generator was committed
- [ ] No real LP statements committed; only synthetic fixtures or
      public illustrative PDFs (per `examples/real_world/README.md`)
- [ ] If touching `src/vc_statement_parser/extractors/llm.py`: noted any
      provider-compat implications

## Testing notes

<!-- How did you exercise this? Include sample CLI invocations, screenshots
of verification reports, etc. -->

## Related issues

<!-- e.g. Closes #123, Refs #456 -->
