"""Typer CLI: parse one or many statement PDFs into ILPA-aligned, verified JSON.

Usage:
    vc-statement-parse statement.pdf --validate
    vc-statement-parse a.pdf b.pdf c.pdf --validate                 # batch
    vc-statement-parse *.pdf --json-summary                         # JSONL pipeline
    vc-statement-parse statement.pdf --format table --validate
"""

from __future__ import annotations

import json
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

from .models import CapitalAccountStatement
from .parse import NoExtractorAvailableError, parse_statement
from .verification import ValidationReport, verify

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Parse LP capital account statement PDFs into ILPA-aligned, verified JSON.",
)
console = Console()
err_console = Console(stderr=True)


class OutputFormat(StrEnum):
    JSON = "json"
    TABLE = "table"


# Exit codes — kept stable so shell pipelines can rely on them.
EXIT_OK = 0
EXIT_INVARIANT_FAILURE = 1
EXIT_NO_EXTRACTOR = 2
EXIT_PARTIAL_BATCH_FAILURE = 3


def _money(value: Decimal | None) -> str:
    """Format an Optional Decimal as currency, or '—' if missing."""
    return f"${value:,.2f}" if value is not None else "—"


def _decimal_default(obj: object) -> str:
    if isinstance(obj, Decimal):
        return str(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serialisable")


@app.command()
def parse(
    files: Annotated[
        list[Path],
        typer.Argument(
            exists=True,
            dir_okay=False,
            readable=True,
            help="One or more PDF files. Multiple files are processed sequentially.",
        ),
    ],
    admin_hint: Annotated[
        str | None,
        typer.Option("--admin", "-a", help="Force a fund administrator (e.g. 'standish')."),
    ] = None,
    output_format: Annotated[
        OutputFormat,
        typer.Option("--format", "-f", help="Per-file output format."),
    ] = OutputFormat.JSON,
    json_summary: Annotated[
        bool,
        typer.Option(
            "--json-summary",
            help=(
                "Suppress per-file output and print one newline-delimited JSON "
                "summary record per file to stdout. Designed for shell pipelines "
                "(`vc-statement-parse *.pdf --json-summary | jq …`). Implies --validate."
            ),
        ),
    ] = False,
    validate: Annotated[
        bool,
        typer.Option("--validate", "-v", help="Run arithmetic-invariant verification."),
    ] = False,
    no_llm: Annotated[
        bool,
        typer.Option("--no-llm", help="Disable LLM fallback (deterministic only)."),
    ] = False,
) -> None:
    """Parse one or more statement PDFs and print results.

    With a single file, behaves exactly as before. With multiple files, each is
    processed independently — one failure does not abort the rest, and the exit
    code reflects whether any failed.
    """
    # --json-summary turns on validation implicitly: a summary without an
    # invariant report is not very useful.
    run_validate = validate or json_summary

    failures: list[Path] = []
    for pdf in files:
        result = _process_file(
            pdf,
            admin_hint=admin_hint,
            output_format=output_format,
            json_summary=json_summary,
            run_validate=run_validate,
            use_llm_fallback=not no_llm,
            multi_file=len(files) > 1,
        )
        if not result.ok:
            failures.append(pdf)

    # Exit code semantics:
    #   - single file: preserve historical behavior (1 / 2 propagate from the file)
    #   - multi file: 0 if all OK, EXIT_PARTIAL_BATCH_FAILURE otherwise
    if len(files) == 1:
        # If the single file failed, _process_file already raised typer.Exit.
        return
    if failures:
        err_console.print(
            f"[yellow]{len(failures)} of {len(files)} files failed:[/yellow] "
            + ", ".join(str(p) for p in failures)
        )
        raise typer.Exit(code=EXIT_PARTIAL_BATCH_FAILURE)


# --------------------------------------------------------------------------- #
#   Per-file helpers
# --------------------------------------------------------------------------- #


class _FileResult:
    __slots__ = ("ok",)

    def __init__(self, *, ok: bool) -> None:
        self.ok = ok


def _process_file(
    pdf: Path,
    *,
    admin_hint: str | None,
    output_format: OutputFormat,
    json_summary: bool,
    run_validate: bool,
    use_llm_fallback: bool,
    multi_file: bool,
) -> _FileResult:
    """Parse one file. Print output. Return success flag."""
    try:
        statement = parse_statement(pdf, admin_hint=admin_hint, use_llm_fallback=use_llm_fallback)
    except NoExtractorAvailableError as e:
        if json_summary:
            _emit_summary_line(pdf, error=str(e))
            return _FileResult(ok=False)
        err_console.print(f"[red]error[/red] [{pdf}]: {e}")
        if multi_file:
            return _FileResult(ok=False)
        raise typer.Exit(code=EXIT_NO_EXTRACTOR) from e

    report: ValidationReport | None = verify(statement) if run_validate else None

    if json_summary:
        _emit_summary_line(pdf, statement=statement, report=report)
        return _FileResult(ok=report is None or report.passed)

    if multi_file:
        console.rule(f"[bold cyan]{pdf}")
    if output_format is OutputFormat.JSON:
        payload = statement.model_dump(mode="json")
        console.print_json(json.dumps(payload, default=_decimal_default))
    else:
        _print_table(statement)

    if report is not None:
        _print_validation(report)
        if not report.passed:
            if multi_file:
                return _FileResult(ok=False)
            raise typer.Exit(code=EXIT_INVARIANT_FAILURE)

    return _FileResult(ok=True)


def _emit_summary_line(
    pdf: Path,
    *,
    statement: CapitalAccountStatement | None = None,
    report: ValidationReport | None = None,
    error: str | None = None,
) -> None:
    """Print one newline-delimited JSON record to stdout. Pipeline-friendly."""
    record: dict[str, Any] = {"file": str(pdf)}
    if error is not None:
        record["ok"] = False
        record["error"] = error
    else:
        assert statement is not None
        record["ok"] = report is None or report.passed
        record["administrator"] = statement.source_metadata.administrator.value
        record["extractor"] = statement.source_metadata.extractor
        record["confidence"] = statement.source_metadata.parse_confidence
        record["fund_name"] = statement.fund_name
        record["lp_name"] = statement.lp_name
        record["period_end"] = statement.period_end.isoformat()
        record["nav_ending"] = (
            str(statement.nav_ending) if statement.nav_ending is not None else None
        )
        if report is not None:
            record["invariants_run"] = [r.name for r in report.results]
            record["invariants_failed"] = [r.name for r in report.failures]
    console.print_json(json.dumps(record, default=_decimal_default), indent=None)


def _print_table(statement: CapitalAccountStatement) -> None:
    t = Table(title=f"{statement.fund_name} — {statement.lp_name}", show_header=True)
    t.add_column("Field", style="cyan")
    t.add_column("Value", style="white", justify="right")

    rows: list[tuple[str, str]] = [
        ("Period", f"{statement.period_start} → {statement.period_end}"),
        ("As of", str(statement.as_of_date)),
        ("Commitment", _money(statement.commitment)),
        ("Paid-in Capital", _money(statement.paid_in_capital)),
        ("Unfunded", _money(statement.unfunded_commitment)),
        ("NAV (begin)", _money(statement.nav_beginning)),
        ("NAV (end)", _money(statement.nav_ending)),
        ("Realized G/L", _money(statement.realized_gain_loss)),
        ("Unrealized G/L", _money(statement.unrealized_gain_loss)),
        ("Mgmt Fees", _money(statement.management_fees)),
        ("Partnership Expenses", _money(statement.partnership_expenses)),
    ]
    if statement.irr_net is not None:
        rows.append(("Net IRR", f"{statement.irr_net * Decimal('100'):.2f}%"))
    if statement.tvpi_net is not None:
        rows.append(("Net TVPI", f"{statement.tvpi_net:.2f}x"))
    if statement.dpi_net is not None:
        rows.append(("Net DPI", f"{statement.dpi_net:.2f}x"))
    rows.append(("Administrator", statement.source_metadata.administrator.value))
    rows.append(("Extractor", statement.source_metadata.extractor))
    rows.append(("Confidence", f"{statement.source_metadata.parse_confidence:.0%}"))
    for label, value in rows:
        t.add_row(label, value)
    console.print(t)


def _print_validation(report: ValidationReport) -> None:
    t = Table(title="Verification Report", show_header=True)
    t.add_column("Invariant", style="cyan")
    t.add_column("Status")
    t.add_column("Expected", justify="right")
    t.add_column("Actual", justify="right")
    t.add_column("Δ", justify="right")
    for r in report.results:
        status = "[green]PASS[/green]" if r.passed else "[red]FAIL[/red]"
        t.add_row(r.name, status, f"{r.expected:.2f}", f"{r.actual:.2f}", f"{r.delta:.2f}")
    console.print(t)
    if not report.passed:
        err_console.print(f"[red]{len(report.failures)} invariant(s) failed.[/red]")


if __name__ == "__main__":  # pragma: no cover
    app()
