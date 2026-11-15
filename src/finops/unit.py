"""Unit economics: what a request, an outcome and an active user cost, per app per month."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from finops.cost import Line, month_of
from finops.model import Dataset

PRECISION = Decimal("0.0001")


@dataclass(frozen=True)
class UnitEconomics:
    month: str
    app: str
    team: str
    cost: Decimal
    requests: int
    outcomes: int
    active_users: int
    target: Decimal | None

    @property
    def per_1k_requests(self) -> Decimal | None:
        if not self.requests:
            return None
        return (self.cost * 1000 / self.requests).quantize(PRECISION)

    @property
    def per_outcome(self) -> Decimal | None:
        if not self.outcomes:
            return None
        return (self.cost / self.outcomes).quantize(PRECISION)

    @property
    def per_active_user(self) -> Decimal | None:
        if not self.active_users:
            return None
        return (self.cost / self.active_users).quantize(PRECISION)


def unit_economics(ds: Dataset, lines: list[Line]) -> list[UnitEconomics]:
    """Cost includes the app's share of shared costs. Active users are the month's peak day."""
    out: list[UnitEconomics] = []
    keys = sorted({(ln.month, ln.app) for ln in lines})
    for month, app in keys:
        mine = [ln for ln in lines if ln.month == month and ln.app == app]
        outs = [o for o in ds.outcomes if o.app == app and month_of(o.day) == month]
        spec = ds.apps.get(app)
        out.append(
            UnitEconomics(
                month,
                app,
                mine[0].team,
                sum((ln.cost for ln in mine), Decimal(0)),
                sum(ln.requests for ln in mine),
                sum(o.outcomes for o in outs),
                max((o.active_users for o in outs), default=0),
                spec.target_cost_per_outcome if spec else None,
            )
        )
    return out
