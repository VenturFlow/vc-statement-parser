from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from vc_statement_parser.cli import app

runner = CliRunner()


def test_cli_json_output(standish_pdf: Path) -> None:
    result = runner.invoke(app, [str(standish_pdf)])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["lp_name"] == "Acme University Endowment"
    assert payload["source_metadata"]["administrator"] == "standish"


def test_cli_table_output(standish_pdf: Path) -> None:
    result = runner.invoke(app, [str(standish_pdf), "--format", "table"])
    assert result.exit_code == 0, result.output
    assert "Vintage Capital Partners" in result.output
    assert "Net IRR" in result.output


def test_cli_validate_passes(standish_pdf: Path) -> None:
    result = runner.invoke(app, [str(standish_pdf), "--validate"])
    assert result.exit_code == 0, result.output
    assert "PASS" in result.output
    assert "nav_roll_forward" in result.output


def test_cli_batch_mode_processes_each_file_independently(standish_pdf: Path) -> None:
    """Multiple files: each is processed in turn; the rule header separates them."""
    result = runner.invoke(app, [str(standish_pdf), str(standish_pdf), "--validate"])
    assert result.exit_code == 0, result.output
    # The same file twice → both verification reports appear.
    assert result.output.count("nav_roll_forward") >= 2
    assert result.output.count("PASS") >= 8  # 4 invariants x 2 files


def test_cli_json_summary_emits_newline_delimited_records(standish_pdf: Path) -> None:
    """--json-summary outputs one JSON record per file on stdout."""
    result = runner.invoke(
        app,
        [str(standish_pdf), str(standish_pdf), "--json-summary", "--no-llm"],
    )
    assert result.exit_code == 0, result.output
    records = [json.loads(line) for line in result.output.splitlines() if line.strip()]
    assert len(records) == 2
    for record in records:
        assert record["ok"] is True
        assert record["administrator"] == "standish"
        assert record["fund_name"] == "Vintage Capital Partners V, L.P."
        assert "nav_roll_forward" in record["invariants_run"]
        assert record["invariants_failed"] == []


def test_cli_json_summary_handles_unparseable_file_gracefully(
    tmp_path: Path, standish_pdf: Path
) -> None:
    """A file the dispatcher can't classify must still produce a summary line
    and a non-zero exit, not crash the whole batch."""
    # Build a stub PDF with no admin signature. Reuse the same approach as
    # test_unknown_admin_without_llm_raises.
    from reportlab.pdfgen import canvas  # noqa: PLC0415

    bad_pdf = tmp_path / "no_admin.pdf"
    c = canvas.Canvas(str(bad_pdf))
    c.drawString(72, 720, "Anonymous text without any administrator signature")
    c.showPage()
    c.save()

    result = runner.invoke(app, [str(standish_pdf), str(bad_pdf), "--json-summary", "--no-llm"])
    # Batch with mixed outcomes → EXIT_PARTIAL_BATCH_FAILURE = 3
    assert result.exit_code == 3, result.output
    records = [json.loads(line) for line in result.output.splitlines() if line.startswith("{")]
    assert len(records) == 2
    assert records[0]["ok"] is True
    assert records[1]["ok"] is False
    assert "error" in records[1]
