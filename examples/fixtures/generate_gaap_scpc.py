"""Generate a synthetic auditor-style Statement of Changes in Partners' Capital.

This is the layout used by KPMG, CohnReznick, Deloitte, EY, and PwC in their
illustrative private-equity-fund financial statements: a fund-level statement
broken into three columns (General Partner | Limited Partners | Total). Numbers
are SYNTHETIC and chosen so the LP column satisfies the NAV roll-forward
identity to the cent.

Run:
    python -m examples.fixtures.generate_gaap_scpc

Outputs:
    examples/fixtures/gaap_scpc_synthetic.pdf

Designed to mirror the Standish synthetic generator next door — both produce a
realistic exercise document for the parser, but for a different administrator
format (Standish = LP-specific PCAP; GAAP_SCPC = fund-level SCPC).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas


@dataclass(frozen=True)
class GaapScpcStatementInput:
    """Inputs for the synthetic GAAP SCPC PDF.

    Numbers are chosen so that for the Limited Partners column:
        nav_beginning + contributions - distributions
            + realized + unrealized
            - net_investment_loss - carried_interest_to_gp == nav_ending

    which matches the parser's NAV roll-forward identity (treating
    `net_investment_loss + carried_interest_to_gp` as `partnership_expenses`).

    Kept deliberately compact — only the line items needed to exercise every
    parser category. Real auditor templates have additional broken-out FX
    rows that we don't bother synthesising (they produce reportlab text-flow
    overlap when the wrapped label runs into the right-aligned value column).
    """

    fund_name: str = "Vintage Capital Partners V, L.P."
    period_label: str = "Year ended December 31, 2024"

    # GP / LP / Total — three-column rows. We track the LP column explicitly
    # because that's what the parser extracts; GP and Total are reasonable
    # fillers so the layout looks like a real audited statement.
    lp_nav_beginning: Decimal = Decimal("100000000.00")
    lp_contributions: Decimal = Decimal("8000000.00")
    lp_distributions: Decimal = Decimal("12000000.00")  # absolute magnitude; printed in parens
    lp_net_investment_loss: Decimal = Decimal("1500000.00")  # printed in parens
    lp_realized_gain_investments: Decimal = Decimal("4500000.00")
    lp_unrealized_gain_investments: Decimal = Decimal("3000000.00")
    lp_carried_interest_to_gp: Decimal = Decimal("2500000.00")  # printed in parens

    # GP and Total columns — illustrative ratios; not used by the parser but
    # need to look plausible for the document to read like a real statement.
    gp_share: Decimal = Decimal("0.01")  # ~1% allocation typical for a small GP commitment

    transactions: list[tuple[str, str, Decimal]] = field(default_factory=list)

    @property
    def lp_nav_ending(self) -> Decimal:
        return (
            self.lp_nav_beginning
            + self.lp_contributions
            - self.lp_distributions
            - self.lp_net_investment_loss
            + self.lp_realized_gain_investments
            + self.lp_unrealized_gain_investments
            - self.lp_carried_interest_to_gp
        )


def _gp(value: Decimal, share: Decimal) -> Decimal:
    return (value * share).quantize(Decimal("1"))


def _row(value_lp: Decimal, share: Decimal, *, paren: bool = False) -> tuple[str, str, str]:
    """Format a single row's three columns (GP | LP | Total)."""
    gp_value = _gp(value_lp, share)
    total = value_lp + gp_value

    def fmt(v: Decimal) -> str:
        return f"$({abs(v):,.0f})" if paren else f"${v:,.0f}"

    return fmt(gp_value), fmt(value_lp), fmt(total)


def render_gaap_scpc_pdf(out_path: Path, data: GaapScpcStatementInput | None = None) -> Path:
    """Render the synthetic GAAP SCPC PDF to `out_path`. Returns the path written."""
    data = data or GaapScpcStatementInput()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    c = canvas.Canvas(str(out_path), pagesize=LETTER)
    _width, height = LETTER
    y = height - 72
    left = 60
    col_gp = 320
    col_lp = 420
    col_total = 520

    def header(text: str, *, size: int = 14, bold: bool = True, gap: int = 22) -> None:
        nonlocal y
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.drawString(left, y, text)
        y -= gap

    def row(label: str, gp: str, lp: str, total: str, *, bold: bool = False, gap: int = 16) -> None:
        nonlocal y
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 10)
        c.drawString(left, y, label)
        c.drawRightString(col_gp, y, gp)
        c.drawRightString(col_lp, y, lp)
        c.drawRightString(col_total, y, total)
        y -= gap

    # --- Title block (matches KPMG / CohnReznick layout) ---
    header(data.fund_name, size=14)
    header("Statement of Changes in Partners' Capital", size=12, bold=False, gap=18)
    header(data.period_label, size=11, bold=False, gap=28)

    # Column headers
    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(col_gp, y, "General Partner")
    c.drawRightString(col_lp, y, "Limited Partners")
    c.drawRightString(col_total, y, "Total")
    y -= 22

    # --- Rows (LP column drives the math) ---
    share = data.gp_share

    gp, lp, tot = _row(data.lp_nav_beginning, share)
    row("Partners' capital, beginning of year", gp, lp, tot, bold=False, gap=18)

    gp, lp, tot = _row(data.lp_contributions, share)
    row("Capital contributions", gp, lp, tot)

    gp, lp, tot = _row(data.lp_distributions, share, paren=True)
    row("Capital distributions", gp, lp, tot)

    # Allocation of net income — broken-out KPMG-style P&L lines
    c.setFont("Helvetica-Oblique", 10)
    c.drawString(left, y, "Allocation of net income (loss)")
    y -= 14

    gp, lp, tot = _row(data.lp_net_investment_loss, share, paren=True)
    row("Net investment loss", gp, lp, tot)

    gp, lp, tot = _row(data.lp_realized_gain_investments, share)
    row("Net realized gain from investments", gp, lp, tot)

    gp, lp, tot = _row(data.lp_unrealized_gain_investments, share)
    row("Net unrealized gain from investments", gp, lp, tot)

    # Carried interest — moves capital GP-ward; LP side is paren-wrapped
    ci_gp = f"${data.lp_carried_interest_to_gp:,.0f}"
    ci_lp = f"$({data.lp_carried_interest_to_gp:,.0f})"
    ci_total = "—"
    row("Carried interest to general partner", ci_gp, ci_lp, ci_total, gap=18)

    gp, lp, tot = _row(data.lp_nav_ending, share)
    row("Partners' capital, end of year", gp, lp, tot, bold=True, gap=24)

    c.setFont("Helvetica-Oblique", 9)
    c.drawString(left, y, "Synthetic test fixture — see examples/fixtures/generate_gaap_scpc.py")

    c.showPage()
    c.save()
    return out_path


def main() -> None:
    here = Path(__file__).resolve().parent
    out = render_gaap_scpc_pdf(here / "gaap_scpc_synthetic.pdf")
    print(f"Wrote: {out}")


if __name__ == "__main__":
    main()
