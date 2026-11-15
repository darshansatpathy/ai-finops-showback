"""Policy rules over the cost data. Each has an ID, a severity, a reason and a failing-case test.

The rules ask whether the numbers can be trusted before asking whether they are good: is every
record attributable to an app and a team, is every line priced, do the parts add up to the whole.
Only then do budgets, anomalies and unit cost matter.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from finops import anomaly, budget, unit
from finops.cost import (
    Line,
    build_lines,
    cents,
    month_fraction,
    month_of,
    price_in_effect,
    rate_in_effect,
)
from finops.model import Dataset

SEVERITIES = ("low", "medium", "high", "critical")


def severity_rank(s: str) -> int:
    return SEVERITIES.index(s)


@dataclass(frozen=True)
class Context:
    ds: Dataset
    lines: list[Line]
    today: date

    @property
    def month(self) -> str:
        return month_of(self.ds.as_of)


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: str
    subject: str
    message: str


@dataclass(frozen=True)
class Rule:
    id: str
    severity: str
    title: str
    why: str
    check: Callable[[Context], Iterator[tuple[str, str]]]


REGISTRY: list[Rule] = []
Check = Callable[[Context], Iterator[tuple[str, str]]]


def rule(rule_id: str, severity: str, title: str, why: str) -> Callable[[Check], Check]:
    def wrap(fn: Check) -> Check:
        REGISTRY.append(Rule(rule_id, severity, title, why, fn))
        return fn

    return wrap


def money(x: Decimal) -> str:
    return f"${x:,.2f}"


@rule(
    "FO001",
    "high",
    "Every record belongs to a registered app",
    "Spend on an unknown app has no owner, so nobody can be asked about it and no budget sees it.",
)
def fo001(ctx: Context) -> Iterator[tuple[str, str]]:
    seen: dict[str, str] = {}
    for kind, rows in (("usage", ctx.ds.usage), ("gpu", ctx.ds.gpu), ("outcomes", ctx.ds.outcomes)):
        for r in rows:
            if r.app not in ctx.ds.apps:
                seen.setdefault(r.app, f"{kind} record {r.source}")
    for app, where in sorted(seen.items()):
        yield app, f"not in org.toml (first seen in {where}); its cost is shown as unassigned"


@rule(
    "FO002",
    "high",
    "Every model used has a price in effect on that day",
    "A record with no price is dropped from the totals, which understates spend without any error.",
)
def fo002(ctx: Context) -> Iterator[tuple[str, str]]:
    for u in ctx.ds.usage:
        if price_in_effect(ctx.ds.prices, u.model, u.day) is None:
            yield u.source, f"no price for model `{u.model}` on {u.day}; the record is not costed"


@rule(
    "FO003",
    "high",
    "Every GPU SKU used has a rate in effect on that day",
    "Provisioned GPU hours are often the largest fixed cost; an unrated SKU hides it.",
)
def fo003(ctx: Context) -> Iterator[tuple[str, str]]:
    for g in ctx.ds.gpu:
        if rate_in_effect(ctx.ds.rates, g.sku, g.day) is None:
            yield g.source, f"no rate for GPU `{g.sku}` on {g.day}; the record is not costed"


@rule(
    "FO004",
    "high",
    "Busy GPU hours never exceed provisioned hours",
    "It cannot happen, so the export is wrong and every utilisation figure built on it is too.",
)
def fo004(ctx: Context) -> Iterator[tuple[str, str]]:
    for g in ctx.ds.gpu:
        if g.hours_busy > g.hours_provisioned:
            yield g.source, f"{g.hours_busy} busy hours but only {g.hours_provisioned} provisioned"


@rule(
    "FO005",
    "high",
    "No duplicate usage or GPU records for the same day",
    "A record loaded twice doubles that day's cost and looks like a real spike.",
)
def fo005(ctx: Context) -> Iterator[tuple[str, str]]:
    seen: dict[tuple[object, ...], str] = {}
    for u in ctx.ds.usage:
        key = ("usage", u.day, u.app, u.model)
        if key in seen:
            yield u.source, f"duplicates {seen[key]} (same day, app and model)"
        seen.setdefault(key, u.source)
    for g in ctx.ds.gpu:
        gkey = ("gpu", g.day, g.app, g.sku)
        if gkey in seen:
            yield g.source, f"duplicates {seen[gkey]} (same day, app and SKU)"
        seen.setdefault(gkey, g.source)


@rule(
    "FO006",
    "high",
    "Every app belongs to a registered team",
    "Showback is by team. An app without one cannot be charged to anybody.",
)
def fo006(ctx: Context) -> Iterator[tuple[str, str]]:
    for app in ctx.ds.apps.values():
        if app.team not in ctx.ds.teams:
            yield app.id, f"team `{app.team}` is not in org.toml"


@rule(
    "FO007",
    "medium",
    "Every team that spends has a budget, and every budget has a team",
    "A team with no budget can overspend without any signal; a budget for no team guards nothing.",
)
def fo007(ctx: Context) -> Iterator[tuple[str, str]]:
    spenders = {ln.team for ln in ctx.lines if ln.team in ctx.ds.teams}
    for team in sorted(spenders - set(ctx.ds.budgets)):
        yield team, "spends but has no budget"
    for team in sorted(set(ctx.ds.budgets) - set(ctx.ds.teams)):
        yield team, "has a budget but is not a registered team"


def _latest_budgets(ctx: Context) -> list[budget.BudgetStatus]:
    return [b for b in budget.budget_status(ctx.ds, ctx.lines) if b.month == ctx.month]


@rule(
    "FO008",
    "high",
    "No team is over budget this month",
    "Spend already exceeds what was agreed; the owner needs to decide, not be told next month.",
)
def fo008(ctx: Context) -> Iterator[tuple[str, str]]:
    for b in _latest_budgets(ctx):
        if b.state == "over":
            yield b.team, f"{money(b.spent)} of {money(b.budget)} ({b.pct}%) in {b.month}"


@rule(
    "FO009",
    "medium",
    "No team is forecast to exceed its budget",
    "At the current run-rate the month ends over budget, while there is still time to act.",
)
def fo009(ctx: Context) -> Iterator[tuple[str, str]]:
    for b in _latest_budgets(ctx):
        if b.state == "forecast-over":
            yield (
                b.team,
                f"{money(b.spent)} so far, forecast {money(b.forecast)} against {money(b.budget)} "
                f"({b.forecast_pct}%) for {b.month}",
            )


@rule(
    "FO010",
    "low",
    "No team has used most of its budget",
    "An early warning, at the threshold the policy sets.",
)
def fo010(ctx: Context) -> Iterator[tuple[str, str]]:
    for b in _latest_budgets(ctx):
        if b.state == "warn":
            yield b.team, f"{b.pct}% of {money(b.budget)} used in {b.month}"


@rule(
    "FO011",
    "medium",
    "Spend without a cost centre stays under the policy limit",
    "Untagged spend cannot be charged back. A little is normal; a lot means tagging has broken.",
)
def fo011(ctx: Context) -> Iterator[tuple[str, str]]:
    direct = [ln for ln in ctx.lines if ln.kind != "shared" and ln.month == ctx.month]
    total = sum((ln.cost for ln in direct), Decimal(0))
    untagged = sum((ln.cost for ln in direct if not ln.cost_center), Decimal(0))
    if total > 0 and untagged * 100 / total > ctx.ds.policy.untagged_max_pct:
        apps = sorted({ln.app for ln in direct if not ln.cost_center})
        yield (
            ctx.month,
            f"{money(untagged)} of {money(total)} ({untagged * 100 / total:.1f}%) has no cost centre: "
            f"{', '.join(apps)}",
        )


@rule(
    "FO012",
    "medium",
    "No recent day of spend is anomalous",
    "A sudden jump is usually a loop, a retry storm or a leaked key, and costs more every hour.",
)
def fo012(ctx: Context) -> Iterator[tuple[str, str]]:
    cutoff = ctx.ds.as_of.toordinal() - ctx.ds.policy.anomaly_recent_days
    for a in anomaly.anomalies(ctx.lines, ctx.ds.policy):
        if a.day.toordinal() > cutoff:
            yield (
                a.app,
                f"{a.day}: {money(a.cost)} against a typical {money(a.baseline)} (score {a.score})",
            )


@rule(
    "FO013",
    "medium",
    "The usage export is fresh",
    "Every other result is only as current as the export behind it.",
)
def fo013(ctx: Context) -> Iterator[tuple[str, str]]:
    lag = (ctx.today - ctx.ds.as_of).days
    if lag > ctx.ds.policy.max_data_lag_days:
        yield "usage", f"newest record is {ctx.ds.as_of}, {lag} days before {ctx.today}"


@rule(
    "FO014",
    "medium",
    "Cost per outcome is within the app's target",
    "Unit cost is how a budget becomes a business decision: cheaper per outcome, or not worth it.",
)
def fo014(ctx: Context) -> Iterator[tuple[str, str]]:
    for u in unit.unit_economics(ctx.ds, ctx.lines):
        if (
            u.month == ctx.month
            and u.target is not None
            and u.per_outcome is not None
            and u.per_outcome > u.target
        ):
            yield u.app, f"{u.per_outcome} per outcome against a target of {u.target} in {u.month}"


@rule(
    "FO015",
    "medium",
    "GPU capacity is used",
    "Provisioned hours are paid for whether or not anything runs on them.",
)
def fo015(ctx: Context) -> Iterator[tuple[str, str]]:
    totals: dict[tuple[str, str], list[Decimal]] = {}
    for g in ctx.ds.gpu:
        if month_of(g.day) == ctx.month:
            t = totals.setdefault((g.app, g.sku), [Decimal(0), Decimal(0)])
            t[0] += g.hours_busy
            t[1] += g.hours_provisioned
    for (app, sku), (busy, provisioned) in sorted(totals.items()):
        if provisioned > 0 and busy * 100 / provisioned < ctx.ds.policy.min_gpu_utilisation_pct:
            idle = (provisioned - busy) * _rate(ctx, sku)
            yield (
                app,
                f"`{sku}` busy {busy * 100 / provisioned:.1f}% of {provisioned} provisioned hours "
                f"in {ctx.month}; about {money(cents(idle))} spent on idle hours",
            )


def _rate(ctx: Context, sku: str) -> Decimal:
    rate = rate_in_effect(ctx.ds.rates, sku, ctx.ds.as_of)
    return rate.hourly if rate else Decimal(0)


@rule(
    "FO016",
    "critical",
    "Shared costs are allocated in full, to the cent",
    "If the allocated parts do not add up to the shared cost, every team's total is wrong.",
)
def fo016(ctx: Context) -> Iterator[tuple[str, str]]:
    for month in sorted({ln.month for ln in ctx.lines if ln.kind != "shared"}):
        for sh in ctx.ds.shared:
            allocated = sum(
                (
                    ln.cost
                    for ln in ctx.lines
                    if ln.month == month and ln.kind == "shared" and ln.item == sh.id
                ),
                Decimal(0),
            )
            expected = cents(sh.monthly_usd * month_fraction(month, ctx.ds.as_of))
            if allocated != expected:
                yield f"{month}/{sh.id}", f"allocated {allocated} but expected {expected}"


@rule(
    "FO017",
    "low",
    "Every app that spends reports outcomes",
    "Without outcomes there is no unit cost, only a total that can grow unnoticed.",
)
def fo017(ctx: Context) -> Iterator[tuple[str, str]]:
    with_outcomes = {o.app for o in ctx.ds.outcomes if month_of(o.day) == ctx.month}
    for app in sorted({ln.app for ln in ctx.lines if ln.month == ctx.month}):
        if app in ctx.ds.apps and app not in with_outcomes:
            yield app, f"spends in {ctx.month} but reports no outcomes, so it has no unit cost"


def run(ds: Dataset, today: date) -> list[Finding]:
    lines, _ = build_lines(ds)
    ctx = Context(ds, lines, today)
    found = [
        Finding(r.id, r.severity, subject, msg) for r in REGISTRY for subject, msg in r.check(ctx)
    ]
    return sorted(found, key=lambda f: (-severity_rank(f.severity), f.rule, f.subject))


def catalog() -> list[tuple[str, str, str, str]]:
    return [(r.id, r.severity, r.title, r.why) for r in REGISTRY]
