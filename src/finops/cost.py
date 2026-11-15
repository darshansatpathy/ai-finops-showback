"""Turn usage records into priced cost lines, and allocate shared costs so totals reconcile.

Rounding rule: every priced record is rounded to the cent once, half-to-even, the way an invoice
line is. Everything above that (an app, a team, the organisation) is a sum of cents, so the
numbers in different reports always add up exactly. Shared costs are split with the
largest-remainder method for the same reason: the parts sum to the whole, to the cent.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal

from finops.model import Dataset, GpuRate, ModelPrice

CENT = Decimal("0.01")
MILLION = Decimal(1_000_000)
UNASSIGNED = "(unassigned)"


def cents(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_EVEN)


def month_of(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def days_in(month: str) -> int:
    year, mon = (int(x) for x in month.split("-"))
    return calendar.monthrange(year, mon)[1]


def month_fraction(month: str, as_of: date) -> Decimal:
    """Share of the month that the data covers: 1 for a complete month."""
    if month != month_of(as_of):
        return Decimal(1)
    return Decimal(as_of.day) / Decimal(days_in(month))


def price_in_effect(prices: list[ModelPrice], model: str, on: date) -> ModelPrice | None:
    candidates = [p for p in prices if p.model == model and p.effective_from <= on]
    return max(candidates, key=lambda p: p.effective_from, default=None)


def rate_in_effect(rates: list[GpuRate], sku: str, on: date) -> GpuRate | None:
    candidates = [r for r in rates if r.sku == sku and r.effective_from <= on]
    return max(candidates, key=lambda r: r.effective_from, default=None)


@dataclass(frozen=True)
class Line:
    """One priced line. `day` is None for allocated shared costs, which are monthly."""

    day: date | None
    month: str
    team: str
    app: str
    cost_center: str
    kind: str  # tokens | gpu | shared
    item: str  # model, GPU sku or shared-cost id
    requests: int
    tokens: int
    hours: Decimal
    cost: Decimal


def allocate(total: Decimal, weights: dict[str, Decimal]) -> dict[str, Decimal]:
    """Split `total` (in cents) across keys in proportion to weights, summing exactly to it."""
    if not weights:
        return {}
    keys = sorted(weights)
    w = {k: weights[k] for k in keys}
    if sum(w.values()) <= 0:
        w = dict.fromkeys(keys, Decimal(1))
    whole = sum(w.values())
    units = int((total / CENT).to_integral_value())
    exact = {k: Decimal(units) * w[k] / whole for k in keys}
    floors = {k: int(exact[k]) for k in keys}
    left = units - sum(floors.values())
    order = sorted(keys, key=lambda k: (-(exact[k] - floors[k]), k))
    for k in order[:left]:
        floors[k] += 1
    return {k: Decimal(floors[k]) * CENT for k in keys}


def build_lines(ds: Dataset) -> tuple[list[Line], list[str]]:
    """Priced lines for direct spend and allocated shared costs, and what could not be priced."""
    lines: list[Line] = []
    unpriced: list[str] = []

    def owner(app_id: str) -> tuple[str, str]:
        app = ds.apps.get(app_id)
        return (app.team, app.cost_center) if app else (UNASSIGNED, "")

    for u in sorted(ds.usage, key=lambda u: (u.day, u.app, u.model)):
        price = price_in_effect(ds.prices, u.model, u.day)
        if price is None:
            unpriced.append(f"{u.source}: no price for model `{u.model}` on {u.day}")
            continue
        raw = (
            Decimal(u.input_tokens) * price.input_per_mtok
            + Decimal(u.output_tokens) * price.output_per_mtok
            + Decimal(u.cached_input_tokens) * price.cached_per_mtok
        ) / MILLION
        team, cc = owner(u.app)
        lines.append(
            Line(
                u.day,
                month_of(u.day),
                team,
                u.app,
                cc,
                "tokens",
                u.model,
                u.requests,
                u.input_tokens + u.output_tokens + u.cached_input_tokens,
                Decimal(0),
                cents(raw),
            )
        )
    for g in sorted(ds.gpu, key=lambda g: (g.day, g.app, g.sku)):
        rate = rate_in_effect(ds.rates, g.sku, g.day)
        if rate is None:
            unpriced.append(f"{g.source}: no rate for GPU `{g.sku}` on {g.day}")
            continue
        team, cc = owner(g.app)
        lines.append(
            Line(
                g.day,
                month_of(g.day),
                team,
                g.app,
                cc,
                "gpu",
                g.sku,
                0,
                0,
                g.hours_provisioned,
                cents(g.hours_provisioned * rate.hourly),
            )
        )
    lines.extend(_shared_lines(ds, lines))
    return lines, unpriced


def _shared_lines(ds: Dataset, direct: list[Line]) -> list[Line]:
    out: list[Line] = []
    for month in sorted({ln.month for ln in direct}):
        in_month = [ln for ln in direct if ln.month == month]
        apps = sorted({ln.app for ln in in_month})
        for sh in sorted(ds.shared, key=lambda s: s.id):
            weights: dict[str, Decimal] = {}
            for app in apps:
                mine = [ln for ln in in_month if ln.app == app]
                if sh.driver == "tokens":
                    weights[app] = Decimal(sum(ln.tokens for ln in mine))
                elif sh.driver == "requests":
                    weights[app] = Decimal(sum(ln.requests for ln in mine))
                else:
                    weights[app] = Decimal(1)
            total = cents(sh.monthly_usd * month_fraction(month, ds.as_of))
            for app, amount in allocate(total, weights).items():
                team, cc = (
                    (ds.apps[app].team, ds.apps[app].cost_center)
                    if app in ds.apps
                    else (UNASSIGNED, "")
                )
                out.append(
                    Line(None, month, team, app, cc, "shared", sh.id, 0, 0, Decimal(0), amount)
                )
    return out
