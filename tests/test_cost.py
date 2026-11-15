from __future__ import annotations

import random
from dataclasses import replace
from datetime import date
from decimal import Decimal

from finops import cost
from finops.cost import UNASSIGNED, allocate, build_lines, cents, month_fraction
from finops.model import Dataset

from .conftest import gpu, mini, usage

D = Decimal


def test_cents_rounds_half_to_even() -> None:
    assert cents(D("0.125")) == D("0.12")
    assert cents(D("0.135")) == D("0.14")
    assert cents(D("2.005")) == D("2.00")


def test_month_helpers() -> None:
    assert cost.month_of(date(2026, 3, 9)) == "2026-03"
    assert cost.days_in("2026-02") == 28 and cost.days_in("2028-02") == 29
    assert month_fraction("2026-11", date(2026, 11, 15)) == D(15) / D(30)
    assert month_fraction("2026-10", date(2026, 11, 15)) == 1
    assert month_fraction("2026-11", date(2026, 11, 30)) == 1


def test_token_cost_is_exact(ds: Dataset) -> None:
    # 4M input at $0.25 + 0.8M output at $1.25 + 2M cached at $0.025 = 1.00 + 1.00 + 0.05
    data = mini(ds, usage_rows=[usage(date(2026, 10, 5))], as_of=date(2026, 10, 5), shared=[])
    lines, unpriced = build_lines(data)
    assert unpriced == []
    assert len(lines) == 1
    ln = lines[0]
    assert ln.cost == D("2.05") and ln.kind == "tokens" and ln.item == "frontier-small"
    assert ln.tokens == 6_800_000 and ln.requests == 1000
    assert ln.team == "support-eng" and ln.cost_center == "CC-1010" and ln.month == "2026-10"


def test_price_change_applies_from_its_effective_date(ds: Dataset) -> None:
    rows = [
        usage(date(2026, 10, 31), model="frontier-large", i=1_000_000, o=0, c=0),
        usage(date(2026, 11, 1), model="frontier-large", i=1_000_000, o=0, c=0),
    ]
    data = mini(ds, usage_rows=rows, as_of=date(2026, 11, 1), shared=[])
    lines, _ = build_lines(data)
    assert [ln.cost for ln in lines] == [D("3.00"), D("2.50")]


def test_price_in_effect_picks_latest_not_after_the_day(ds: Dataset) -> None:
    assert cost.price_in_effect(ds.prices, "frontier-large", date(2026, 12, 1)) is not None
    assert cost.price_in_effect(ds.prices, "frontier-large", date(2025, 12, 31)) is None
    assert cost.price_in_effect(ds.prices, "nope", date(2026, 12, 1)) is None
    assert cost.rate_in_effect(ds.rates, "gpu-80gb", date(2025, 12, 31)) is None
    rate = cost.rate_in_effect(ds.rates, "gpu-80gb", date(2026, 6, 1))
    assert rate is not None and rate.hourly == D("3.50")


def test_gpu_is_billed_on_provisioned_hours(ds: Dataset) -> None:
    data = mini(
        ds,
        usage_rows=[],
        gpu=[gpu(date(2026, 10, 5), prov="10", busy="2")],
        as_of=date(2026, 10, 5),
        shared=[],
    )
    lines, _ = build_lines(data)
    assert [(ln.kind, ln.item, ln.cost, ln.hours) for ln in lines] == [
        ("gpu", "gpu-80gb", D("35.00"), D("10"))
    ]


def test_unpriced_records_are_reported_not_hidden(ds: Dataset) -> None:
    data = mini(
        ds,
        usage_rows=[usage(date(2026, 10, 5), model="mystery")],
        gpu=[gpu(date(2026, 10, 5), sku="gpu-x")],
        as_of=date(2026, 10, 5),
        shared=[],
    )
    lines, unpriced = build_lines(data)
    assert lines == []
    assert len(unpriced) == 2
    assert "mystery" in unpriced[0] and "gpu-x" in unpriced[1]


def test_unknown_app_is_unassigned_but_still_costed(ds: Dataset) -> None:
    data = mini(
        ds, usage_rows=[usage(date(2026, 10, 5), app="ghost")], as_of=date(2026, 10, 5), shared=[]
    )
    lines, _ = build_lines(data)
    assert lines[0].team == UNASSIGNED and lines[0].cost_center == "" and lines[0].cost == D("2.05")


def test_allocate_sums_exactly_and_gives_the_spare_cent_by_remainder() -> None:
    parts = allocate(D("100.00"), {"a": D(1), "b": D(1), "c": D(1)})
    assert parts == {"a": D("33.34"), "b": D("33.33"), "c": D("33.33")}
    parts = allocate(D("0.10"), {"a": D(2), "b": D(1)})
    assert parts == {"a": D("0.07"), "b": D("0.03")}


def test_allocate_edge_cases() -> None:
    assert allocate(D("10.00"), {}) == {}
    assert allocate(D("10.00"), {"a": D(0), "b": D(0)}) == {"a": D("5.00"), "b": D("5.00")}
    assert allocate(D("0.00"), {"a": D(3), "b": D(1)}) == {"a": D("0.00"), "b": D("0.00")}
    assert allocate(D("5.00"), {"only": D(7)}) == {"only": D("5.00")}


def test_allocate_always_reconciles() -> None:
    rng = random.Random(7)
    for _ in range(300):
        total = D(rng.randrange(0, 5_000_000)) / 100
        weights = {f"k{i}": D(rng.randrange(0, 1000)) for i in range(rng.randrange(1, 9))}
        parts = allocate(total, weights)
        assert sum(parts.values(), D(0)) == total
        assert all(v >= 0 for v in parts.values())


def test_allocate_is_proportional_to_weight() -> None:
    parts = allocate(D("1000.00"), {"big": D(9), "small": D(1)})
    assert parts == {"big": D("900.00"), "small": D("100.00")}


def test_shared_cost_follows_the_driver(ds: Dataset) -> None:
    rows = [
        usage(date(2026, 10, 5), app="support-copilot", requests=3000),
        usage(date(2026, 10, 5), app="fraud-triage", requests=1000),
    ]
    data = mini(ds, usage_rows=rows, as_of=date(2026, 10, 31))
    lines, _ = build_lines(data)
    gateway = {ln.app: ln.cost for ln in lines if ln.item == "ai-gateway"}
    assert gateway == {"fraud-triage": D("750.00"), "support-copilot": D("2250.00")}  # 3000 x 1:3
    harness = {ln.app: ln.cost for ln in lines if ln.item == "eval-harness"}
    assert harness == {"fraud-triage": D("600.00"), "support-copilot": D("600.00")}  # even
    tokens = {ln.app: ln.cost for ln in lines if ln.item == "observability"}
    assert sum(tokens.values(), D(0)) == D("1800.00")


def test_shared_cost_is_pro_rated_for_a_partial_month(ds: Dataset) -> None:
    data = mini(ds, usage_rows=[usage(date(2026, 11, 3))], as_of=date(2026, 11, 15))
    lines, _ = build_lines(data)
    shared = sum((ln.cost for ln in lines if ln.kind == "shared"), D(0))
    assert shared == cents(D("6000") * D(15) / D(30))


def test_shared_cost_uses_unassigned_for_unknown_apps(ds: Dataset) -> None:
    data = mini(ds, usage_rows=[usage(date(2026, 10, 5), app="ghost")], as_of=date(2026, 10, 31))
    lines, _ = build_lines(data)
    assert {ln.team for ln in lines if ln.kind == "shared"} == {UNASSIGNED}


def test_zero_driver_weight_falls_back_to_an_even_split(ds: Dataset) -> None:
    rows = [
        usage(date(2026, 10, 5), app=a, requests=0, i=0, o=0, c=0)
        for a in ("support-copilot", "doc-search")
    ]
    data = replace(mini(ds, usage_rows=rows, as_of=date(2026, 10, 31)))
    lines, _ = build_lines(data)
    gateway = {ln.app: ln.cost for ln in lines if ln.item == "ai-gateway"}
    assert gateway == {"doc-search": D("1500.00"), "support-copilot": D("1500.00")}


def test_the_sample_reconciles(ds: Dataset) -> None:
    lines, unpriced = build_lines(ds)
    assert unpriced == []
    for month, frac in (("2026-10", D(1)), ("2026-11", D(14) / D(30))):
        shared = sum((ln.cost for ln in lines if ln.month == month and ln.kind == "shared"), D(0))
        assert shared == cents(D("6000") * frac)
