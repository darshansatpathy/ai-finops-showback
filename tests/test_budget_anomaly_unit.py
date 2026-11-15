from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

from finops import anomaly, unit
from finops.budget import BudgetStatus, budget_status
from finops.cost import Line, build_lines
from finops.model import Budget, Dataset, Outcome, Policy

from .conftest import mini, usage

D = Decimal


def with_budget(ds: Dataset, amount: str) -> dict[str, Budget]:
    return {"support-eng": Budget("support-eng", D(amount))}


def one_team(ds: Dataset, day: date, as_of: date, budget: str) -> BudgetStatus:
    # one record costing $2.05, no shared costs
    data = mini(
        ds, usage_rows=[usage(day)], as_of=as_of, shared=[], budgets=with_budget(ds, budget)
    )
    lines, _ = build_lines(data)
    (status,) = budget_status(data, lines)
    return status


def test_budget_states(ds: Dataset) -> None:
    eom = date(2026, 10, 31)
    assert one_team(ds, date(2026, 10, 5), eom, "100").state == "ok"
    assert one_team(ds, date(2026, 10, 5), eom, "2.50").state == "warn"  # 82% used, month over
    assert one_team(ds, date(2026, 10, 5), eom, "2.05").state == "warn"  # exactly 100% is not over
    assert one_team(ds, date(2026, 10, 5), eom, "2.00").state == "over"


def test_forecast_over_is_a_run_rate_not_a_fact(ds: Dataset) -> None:
    s = one_team(ds, date(2026, 11, 3), date(2026, 11, 15), "3.00")  # $2.05 so far, 50% of month
    assert s.spent == D("2.05") and s.forecast == D("4.10")
    assert s.state == "forecast-over"
    assert s.pct == D("68.3") and s.forecast_pct == D("136.7")


def test_forecast_equals_spend_for_a_complete_month(ds: Dataset) -> None:
    s = one_team(ds, date(2026, 10, 5), date(2026, 11, 15), "100")
    assert s.forecast == s.spent == D("2.05")


def test_zero_budget_does_not_divide_by_zero(ds: Dataset) -> None:
    s = one_team(ds, date(2026, 10, 5), date(2026, 10, 31), "0")
    assert s.pct == 0 and s.state == "over"


def test_the_sample_has_one_forecast_overrun(ds: Dataset) -> None:
    lines, _ = build_lines(ds)
    latest = [b for b in budget_status(ds, lines) if b.month == "2026-11"]
    assert {b.team: b.state for b in latest} == {
        "data-platform": "ok",
        "growth": "forecast-over",
        "risk": "ok",
        "support-eng": "ok",
    }


# anomaly detection

POLICY = Policy(D(2), D(80), D(50), 3, 14, 7, D("3.5"), D(25), 7)
DAY0 = date(2026, 10, 1)


def series(values: list[int]) -> dict[date, Decimal]:
    return {DAY0 + timedelta(days=i): D(v) for i, v in enumerate(values)}


def test_a_steady_series_has_no_anomaly() -> None:
    assert (
        anomaly.detect("a", series([100, 104, 98, 101, 99, 103, 100, 102, 97, 105]), POLICY) == []
    )


def test_a_spike_is_flagged_with_its_baseline() -> None:
    found = anomaly.detect("a", series([100, 104, 98, 101, 99, 103, 100, 102, 400]), POLICY)
    assert len(found) == 1
    assert found[0].day == DAY0 + timedelta(days=8) and found[0].cost == D(400)
    assert found[0].baseline == D("100.5") and found[0].score > D("3.5")


def test_a_second_runaway_day_is_still_flagged() -> None:
    found = anomaly.detect("a", series([100, 104, 98, 101, 99, 103, 100, 102, 400, 450]), POLICY)
    assert [a.cost for a in found] == [D(400), D(450)]  # the median ignores the first spike


def test_a_spike_that_costs_little_is_ignored() -> None:
    assert anomaly.detect("a", series([2, 3, 2, 3, 2, 3, 2, 3, 15]), POLICY) == []  # +$12 < $25


def test_not_enough_history_is_not_judged() -> None:
    assert anomaly.detect("a", series([100, 100, 100, 100, 100, 100, 900]), POLICY) == []


def test_a_flat_history_still_catches_a_jump() -> None:
    found = anomaly.detect("a", series([100] * 8 + [400]), POLICY)
    assert [a.cost for a in found] == [D(400)]


def test_a_drop_is_not_an_anomaly() -> None:
    assert anomaly.detect("a", series([100, 104, 98, 101, 99, 103, 100, 102, 5]), POLICY) == []


def test_old_days_fall_out_of_the_window() -> None:
    old_spike = [100] * 7 + [1000] * 9 + [100, 1000]
    # by the last day the window of 14 holds mostly 1000s, so 1000 is no longer odd
    found = anomaly.detect("a", series(old_spike), POLICY)
    assert DAY0 + timedelta(days=17) not in [a.day for a in found]


def test_anomalies_use_direct_spend_per_app(ds: Dataset) -> None:
    def ln(app: str, d: date, cost: str, kind: str = "tokens", day: bool = True) -> Line:
        return Line(d if day else None, "2026-10", "t", app, "cc", kind, "m", 0, 0, D(0), D(cost))

    lines = [ln("a", DAY0 + timedelta(days=i), "100") for i in range(8)]
    lines.append(ln("a", DAY0 + timedelta(days=8), "400"))
    lines.append(ln("a", DAY0 + timedelta(days=8), "9999", "shared", day=False))  # never counted
    found = anomaly.anomalies(lines, POLICY)
    assert [(a.app, a.cost) for a in found] == [("a", D(400))]


def test_the_sample_runaway_is_found(ds: Dataset) -> None:
    lines, _ = build_lines(ds)
    found = anomaly.anomalies(lines, ds.policy)
    assert [(str(a.day), a.app) for a in found] == [
        ("2026-11-10", "marketing-gen"),
        ("2026-11-11", "marketing-gen"),
    ]


# unit economics


def test_unit_costs(ds: Dataset) -> None:
    rows = [usage(date(2026, 10, 5), app="support-copilot", requests=1000)]
    outs = [
        Outcome(date(2026, 10, 5), "support-copilot", 100, 40, "t1"),
        Outcome(date(2026, 10, 6), "support-copilot", 50, 90, "t2"),
    ]
    data = mini(ds, usage_rows=rows, as_of=date(2026, 10, 31), shared=[], outcomes=outs)
    lines, _ = build_lines(data)
    (u,) = unit.unit_economics(data, lines)
    assert u.cost == D("2.05") and u.requests == 1000 and u.outcomes == 150 and u.active_users == 90
    assert u.per_1k_requests == D("2.0500")
    assert u.per_outcome == D("0.0137")
    assert u.per_active_user == D("0.0228")
    assert u.target == D("0.05")


def test_unit_costs_are_none_without_a_denominator(ds: Dataset) -> None:
    data = mini(
        ds,
        usage_rows=[usage(date(2026, 10, 5), app="eval-sandbox", requests=0)],
        as_of=date(2026, 10, 31),
        shared=[],
    )
    lines, _ = build_lines(data)
    (u,) = unit.unit_economics(data, lines)
    assert u.per_1k_requests is None and u.per_outcome is None and u.per_active_user is None
    assert u.target is None


def test_unit_economics_for_an_unregistered_app_has_no_target(ds: Dataset) -> None:
    data = mini(
        ds, usage_rows=[usage(date(2026, 10, 5), app="ghost")], as_of=date(2026, 10, 31), shared=[]
    )
    lines, _ = build_lines(data)
    (u,) = unit.unit_economics(data, lines)
    assert u.target is None and u.team == "(unassigned)"


def test_policy_replace_is_independent(ds: Dataset) -> None:
    other = replace(ds.policy, anomaly_threshold=D(100))
    assert other.anomaly_threshold == D(100) and ds.policy.anomaly_threshold == D("3.5")


def test_warning_starts_exactly_at_the_threshold(ds: Dataset) -> None:
    eom = date(2026, 10, 31)
    assert one_team(ds, date(2026, 10, 5), eom, "2.5625").state == "warn"  # $2.05 is exactly 80%
    assert one_team(ds, date(2026, 10, 5), eom, "2.5626").state == "ok"


def test_history_boundary_and_increase_boundary() -> None:
    assert (
        len(anomaly.detect("a", series([100] * 7 + [400]), POLICY)) == 1
    )  # exactly 7 days of history
    assert anomaly.detect("a", series([100] * 6 + [400]), POLICY) == []
    assert len(anomaly.detect("a", series([10] * 8 + [35]), POLICY)) == 1  # +$25 exactly
    assert anomaly.detect("a", series([10] * 8 + [34]), POLICY) == []


def test_gpu_rate_applies_on_its_effective_date(ds: Dataset) -> None:
    from finops import cost

    assert cost.rate_in_effect(ds.rates, "gpu-80gb", date(2026, 1, 1)) is not None
    assert cost.price_in_effect(ds.prices, "frontier-large", date(2026, 1, 1)) is not None
