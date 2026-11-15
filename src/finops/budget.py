"""Budgets: month-to-date, run-rate forecast and state, per team per month."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from finops.cost import CENT, Line, cents, month_fraction
from finops.model import Dataset


@dataclass(frozen=True)
class BudgetStatus:
    month: str
    team: str
    budget: Decimal
    spent: Decimal
    forecast: Decimal
    state: str  # ok | warn | forecast-over | over

    @property
    def pct(self) -> Decimal:
        return _pct(self.spent, self.budget)

    @property
    def forecast_pct(self) -> Decimal:
        return _pct(self.forecast, self.budget)


def _pct(part: Decimal, whole: Decimal) -> Decimal:
    if whole <= 0:
        return Decimal(0)
    return (part * 100 / whole).quantize(Decimal("0.1"))


def budget_status(ds: Dataset, lines: list[Line]) -> list[BudgetStatus]:
    out: list[BudgetStatus] = []
    for month in sorted({ln.month for ln in lines}):
        frac = month_fraction(month, ds.as_of)
        for team in sorted(ds.budgets):
            budget = ds.budgets[team].monthly_usd
            spent = sum(
                (ln.cost for ln in lines if ln.month == month and ln.team == team), Decimal(0)
            )
            forecast = cents(spent / frac) if frac > 0 else spent
            if spent > budget:
                state = "over"
            elif forecast > budget:
                state = "forecast-over"
            elif spent * 100 >= budget * ds.policy.budget_warn_pct:
                state = "warn"
            else:
                state = "ok"
            out.append(BudgetStatus(month, team, budget, spent.quantize(CENT), forecast, state))
    return out
