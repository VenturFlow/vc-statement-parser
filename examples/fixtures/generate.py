"""Generate synthetic-but-realistic LP capital account statement PDFs.

These fixtures are SYNTHETIC. They use fake LP names, fund names, and dollar
amounts that satisfy the arithmetic-invariant verification layer. They exist
so the parser, tests, and CLI demo work end-to-end without ever touching real
investor data.

Run:
    python -m examples.fixtures.generate

Outputs:
    examples/fixtures/standish_synthetic.pdf
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas


@dataclass(frozen=True)
class StandishStatementInput:
    """Inputs for the synthetic Standish-format PDF. Numbers must satisfy invariants."""

    lp_name: str = "Acme University Endowment"
    fund_name: str = "Vintage Capital Partners V, L.P."
    period_label: str = "January 1, 2024 - March 31, 2024"
    as_of_label: str = "March 31, 2024"

    commitment: Decimal = Decimal("25000000.00")
    paid_in_capital: Decimal = Decimal("12500000.00")
    unfunded_commitment: Decimal = Decimal("12500000.00")
    cumulative_distributions: Decimal = Decimal("4200000.00")

    nav_beginning: Decimal = Decimal("13400000.00")
    contributions_period: Decimal = Decimal("1500000.00")
    distributions_period: Decimal = Decimal("800000.00")
    realized_gain_loss: Decimal = Decimal("250000.00")
    unrealized_gain_loss: Decimal = Decimal("920000.00")
    management_fees: Decimal = Decimal("125000.00")
    partnership_expenses: Decimal = Decimal("45000.00")

    irr_net_pct: Decimal = Decimal("18.50")
    tvpi_net_x: Decimal = Decimal("1.54")
    dpi_net_x: Decimal = Decimal("0.34")

    transactions: list[tuple[str, str, Decimal]] = field(
        default_factory=lambda: [
            ("2024-01-15", "Contribution", Decimal("1500000.00")),
            ("2024-02-28", "Distribution", Decimal("800000.00")),
            ("2024-03-31", "Mgmt Fee", Decimal("125000.00")),
            ("2024-03-31", "Expenses", Decimal("45000.00")),
        ]
    )

    @property
    def nav_ending(self) -> Decimal:
        # Computed from inputs so the PDF always satisfies the NAV roll-forward.
        return (
            self.nav_beginning
            + self.contributions_period
            - self.distributions_period
            + self.realized_gain_loss
            + self.unrealized_gain_loss
            - self.management_fees
            - self.partnership_expenses
        )


def _fmt_money(value: Decimal) -> str:
    if value < 0:
        return f"(${abs(value):,.2f})"
    return f"${value:,.2f}"


def render_standish_pdf(out_path: Path, data: StandishStatementInput | None = None) -> Path:
    """Render the synthetic Standish-format PDF to `out_path`. Returns the path written."""
    data = data or StandishStatementInput()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    c = canvas.Canvas(str(out_path), pagesize=LETTER)
    _width, height = LETTER
    y = height - 60
    left = 60
    money_col = 380

    def line(label: str, value: str | None = None, *, bold: bool = False, gap: int = 18) -> None:
        nonlocal y
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 11)
        c.drawString(left, y, label)
        if value is not None:
            c.drawString(money_col, y, value)
        y -= gap

    # Header
    c.setFont("Helvetica-Bold", 16)
    c.drawString(left, y, "STANDISH FUND SERVICES")
    y -= 22
    c.setFont("Helvetica", 13)
    c.drawString(left, y, "Capital Account Statement")
    y -= 28

    line(f"Limited Partner: {data.lp_name}")
    line(f"Fund: {data.fund_name}")
    line(f"Period: {data.period_label}")
    line(f"As of Date: {data.as_of_label}", gap=24)

    line("COMMITMENT SUMMARY", bold=True)
    line("Total Commitment:", _fmt_money(data.commitment))
    line("Paid-in Capital:", _fmt_money(data.paid_in_capital))
    line("Unfunded Commitment:", _fmt_money(data.unfunded_commitment))
    line("Cumulative Distributions:", _fmt_money(data.cumulative_distributions), gap=24)

    line("CAPITAL ACCOUNT ACTIVITY", bold=True)
    line("Beginning Balance (NAV):", _fmt_money(data.nav_beginning))
    line("Capital Contributions:", _fmt_money(data.contributions_period))
    line("Distributions:", _fmt_money(-data.distributions_period))
    line("Realized Gains/(Losses):", _fmt_money(data.realized_gain_loss))
    line("Unrealized Gains/(Losses):", _fmt_money(data.unrealized_gain_loss))
    line("Management Fees:", _fmt_money(-data.management_fees))
    line("Partnership Expenses:", _fmt_money(-data.partnership_expenses))
    line("Ending Balance (NAV):", _fmt_money(data.nav_ending), bold=True, gap=24)

    line("PERFORMANCE", bold=True)
    line("Net IRR:", f"{data.irr_net_pct:.2f}%")
    line("Net TVPI:", f"{data.tvpi_net_x:.2f}x")
    line("Net DPI:", f"{data.dpi_net_x:.2f}x", gap=24)

    line("TRANSACTION DETAIL", bold=True)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(left, y, "Date")
    c.drawString(left + 100, y, "Type")
    c.drawString(left + 240, y, "Amount")
    y -= 16
    c.setFont("Helvetica", 10)
    for tx_date, tx_type, tx_amount in data.transactions:
        c.drawString(left, y, tx_date)
        c.drawString(left + 100, y, tx_type)
        c.drawString(left + 240, y, _fmt_money(tx_amount))
        y -= 14

    c.showPage()
    c.save()
    return out_path


def main() -> None:
    here = Path(__file__).resolve().parent
    out = render_standish_pdf(here / "standish_synthetic.pdf")
    print(f"Wrote: {out}")


if __name__ == "__main__":
    main()
