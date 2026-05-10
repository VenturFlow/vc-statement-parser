"""30-second demo. Generates a synthetic Standish PDF, parses it, prints JSON, verifies."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from examples.fixtures.generate import render_standish_pdf

from vc_statement_parser import parse_statement, verify


def _decimal_default(o: object) -> str:
    if isinstance(o, Decimal):
        return str(o)
    raise TypeError(type(o).__name__)


def main() -> None:
    fixture = Path(__file__).resolve().parent / "fixtures" / "standish_synthetic.pdf"
    render_standish_pdf(fixture)

    statement = parse_statement(fixture)
    print(json.dumps(statement.model_dump(mode="json"), indent=2, default=_decimal_default))

    report = verify(statement)
    print()
    print(f"Verification: {'PASS' if report.passed else 'FAIL'}")
    for r in report.results:
        flag = "ok " if r.passed else "FAIL"
        print(f"  [{flag}] {r.name:24s}  Δ={r.delta:>14.2f}  tol={r.tolerance}")


if __name__ == "__main__":
    main()
