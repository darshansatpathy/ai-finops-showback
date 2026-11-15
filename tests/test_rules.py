"""One failing-case test per rule, plus checks that the sample behaves as the README says."""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from finops import cost, rules
from finops.model import App, Budget, Dataset, Outcome

from .conftest import TODAY, gpu, mini, usage

D = Decimal
EOM = date(2026, 10, 31)


def hits(data: Dataset, rule_id: str, today: date = TODAY) -> list[rules.Finding]:
    return [f for f in rules.run(data, today) if f.rule == rule_id]


def october(ds: Dataset) -> Dataset:
    """The sample cut to a complete month, so run-rate forecasting is out of the picture."""
    return replace(
        ds,
        usage=[u for u in ds.usage if u.day <= EOM],
        gpu=[g for g in ds.gpu if g.day <= EOM],
        outcomes=[o for o in ds.outcomes if o.day <= EOM],
        as_of=EOM,
    )


def test_the_sample_has_exactly_the_findings_the_readme_shows(ds: Dataset) -> None:
    found = rules.run(ds, TODAY)
    assert [(f.rule, f.subject) for f in found] == [
        ("FO009", "growth"),
        ("FO012", "marketing-gen"),
        ("FO012", "marketing-gen"),
        ("FO014", "marketing-gen"),
        ("FO015", "doc-search"),
        ("FO017", "eval-sandbox"),
    ]
    assert not any(rules.severity_rank(f.severity) >= rules.severity_rank("high") for f in found)


def test_fo001_unknown_app(ds: Dataset) -> None:
    data = replace(ds, usage=[*ds.usage, usage(date(2026, 11, 14), app="ghost")])
    (f,) = hits(data, "FO001")
    assert f.subject == "ghost" and "unassigned" in f.message


def test_fo002_unpriced_model(ds: Dataset) -> None:
    data = replace(ds, usage=[*ds.usage, usage(date(2026, 11, 14), model="mystery")])
    (f,) = hits(data, "FO002")
    assert "mystery" in f.message


def test_fo002_model_used_before_its_price_takes_effect(ds: Dataset) -> None:
    data = replace(ds, usage=[*ds.usage, usage(date(2025, 12, 31))])
    assert len(hits(data, "FO002")) == 1


def test_fo003_unrated_gpu(ds: Dataset) -> None:
    data = replace(ds, gpu=[*ds.gpu, gpu(date(2026, 11, 14), sku="gpu-x")])
    (f,) = hits(data, "FO003")
    assert "gpu-x" in f.message


def test_fo004_busy_exceeds_provisioned(ds: Dataset) -> None:
    data = replace(
        ds, gpu=[*ds.gpu, gpu(date(2026, 11, 14), app="fraud-triage", prov="10", busy="11")]
    )
    (f,) = hits(data, "FO004")
    assert "11" in f.message and "10" in f.message


def test_fo005_duplicates(ds: Dataset) -> None:
    data = replace(ds, usage=[*ds.usage, ds.usage[0]], gpu=[*ds.gpu, ds.gpu[0]])
    found = hits(data, "FO005")
    assert len(found) == 2 and all("duplicates" in f.message for f in found)


def test_fo006_app_with_unknown_team(ds: Dataset) -> None:
    apps = {**ds.apps, "orphan": App("orphan", "nobody", "CC-9", "prod", "", None)}
    (f,) = hits(replace(ds, apps=apps), "FO006")
    assert f.subject == "orphan"


def test_fo007_team_without_budget_and_budget_without_team(ds: Dataset) -> None:
    budgets = {k: v for k, v in ds.budgets.items() if k != "risk"}
    budgets["ghosts"] = Budget("ghosts", D(1))
    found = hits(replace(ds, budgets=budgets), "FO007")
    assert {(f.subject, f.message.split(" ", 1)[0]) for f in found} == {
        ("risk", "spends"),
        ("ghosts", "has"),
    }


def test_fo008_over_budget(ds: Dataset) -> None:
    budgets = {**ds.budgets, "support-eng": Budget("support-eng", D(100))}
    (f,) = hits(replace(ds, budgets=budgets), "FO008")
    assert f.subject == "support-eng" and "2026-11" in f.message


def test_fo008_ignores_earlier_months(ds: Dataset) -> None:
    budgets = {**ds.budgets, "support-eng": Budget("support-eng", D(5000))}
    # support-eng spent 8,580.81 in October, which is over 5,000, but October is closed
    assert hits(replace(ds, budgets=budgets), "FO008") == []


def test_fo009_forecast_overrun(ds: Dataset) -> None:
    (f,) = hits(ds, "FO009")
    assert f.subject == "growth" and "110.6%" in f.message


def test_fo010_warning_threshold_at_month_end(ds: Dataset) -> None:
    found = hits(october(ds), "FO010")
    assert {f.subject for f in found} == {"data-platform", "risk", "support-eng"}
    assert hits(ds, "FO010") == []  # mid-month, forecast-over is the stronger signal


def test_fo011_untagged_spend(ds: Dataset) -> None:
    assert hits(ds, "FO011") == []
    strict = replace(ds, policy=replace(ds.policy, untagged_max_pct=D("0.1")))
    (f,) = hits(strict, "FO011")
    assert "eval-sandbox" in f.message and "no cost centre" in f.message


def test_fo012_recent_anomaly_only(ds: Dataset) -> None:
    assert {f.subject for f in hits(ds, "FO012")} == {"marketing-gen"}
    later = replace(ds, usage=[*ds.usage], policy=replace(ds.policy, anomaly_recent_days=1))
    assert hits(later, "FO012") == []  # the spike was 3 days before the newest data


def test_fo013_stale_export(ds: Dataset) -> None:
    assert hits(ds, "FO013") == []
    assert hits(ds, "FO013", today=date(2026, 11, 17)) == []  # 3 days: at the limit
    (f,) = hits(ds, "FO013", today=date(2026, 11, 20))
    assert "6 days" in f.message


def test_fo014_unit_cost_over_target(ds: Dataset) -> None:
    (f,) = hits(ds, "FO014")
    assert f.subject == "marketing-gen" and "0.2612" in f.message and "0.20" in f.message


def test_fo015_idle_gpu(ds: Dataset) -> None:
    (f,) = hits(ds, "FO015")
    assert f.subject == "doc-search" and "35.1%" in f.message and "$1,526.00" in f.message


def test_fo016_allocation_must_reconcile(ds: Dataset, monkeypatch: pytest.MonkeyPatch) -> None:
    assert hits(ds, "FO016") == []
    monkeypatch.setattr(cost, "allocate", lambda total, weights: dict.fromkeys(weights, D("0.00")))
    found = hits(ds, "FO016")
    assert len(found) == 6 and found[0].severity == "critical"  # 2 months x 3 shared costs


def test_fo017_no_outcomes(ds: Dataset) -> None:
    (f,) = hits(ds, "FO017")
    assert f.subject == "eval-sandbox"
    fixed = replace(
        ds, outcomes=[*ds.outcomes, Outcome(date(2026, 11, 14), "eval-sandbox", 5, 2, "t")]
    )
    assert hits(fixed, "FO017") == []


def test_a_clean_minimal_dataset_has_no_findings(ds: Dataset) -> None:
    data = mini(
        ds,
        usage_rows=[usage(date(2026, 10, 5))],
        as_of=date(2026, 10, 31),
        shared=[],
        outcomes=[Outcome(date(2026, 10, 5), "support-copilot", 100, 10, "t")],
    )
    assert rules.run(data, date(2026, 11, 1)) == []


def test_findings_are_ordered_by_severity() -> None:
    assert rules.severity_rank("critical") > rules.severity_rank("low")


def test_every_rule_has_a_test_and_a_reason() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    ids = [r.id for r in rules.REGISTRY]
    assert ids == [f"FO{n:03d}" for n in range(1, len(ids) + 1)]
    for r in rules.REGISTRY:
        assert re.search(rf"def test_{r.id.lower()}_", source), f"no test for {r.id}"
        assert r.severity in rules.SEVERITIES and len(r.why) > 30 and r.title


# Boundaries: a limit means "up to and including the limit is fine".


def one_app_month(ds: Dataset, app: str = "support-copilot", **kw: object) -> Dataset:
    outs = [Outcome(date(2026, 10, 5), app, 100, 10, "t")]
    return mini(
        ds,
        usage_rows=[usage(date(2026, 10, 5), app=app)],
        as_of=EOM,
        shared=[],
        outcomes=outs,
        **kw,
    )


def test_fo004_equal_busy_and_provisioned_is_fine(ds: Dataset) -> None:
    data = mini(
        ds, usage_rows=[], gpu=[gpu(date(2026, 10, 5), prov="10", busy="10")], as_of=EOM, shared=[]
    )
    assert hits(data, "FO004") == []


def test_fo011_exactly_at_the_limit_is_fine(ds: Dataset) -> None:
    rows = [
        usage(date(2026, 10, 5), app="support-copilot"),
        usage(date(2026, 10, 5), app="eval-sandbox"),
    ]
    outs = [
        Outcome(date(2026, 10, 5), a, 1, 1, "t") for a in ("support-copilot", "eval-sandbox")
    ]  # both $2.05
    data = mini(ds, usage_rows=rows, as_of=EOM, shared=[], outcomes=outs)
    at_limit = replace(data, policy=replace(data.policy, untagged_max_pct=D(50)))
    assert hits(at_limit, "FO011") == []
    below = replace(data, policy=replace(data.policy, untagged_max_pct=D("49.9")))
    assert len(hits(below, "FO011")) == 1


def test_fo012_the_recent_window_includes_its_first_day(ds: Dataset) -> None:
    rows = [usage(date(2026, 10, d)) for d in range(1, 9)]
    rows.append(usage(date(2026, 10, 9), i=4_000_000_000))  # $1,000 against about $2
    for as_of, expected in ((date(2026, 10, 15), 1), (date(2026, 10, 16), 0)):  # 6 and 7 days after
        data = mini(ds, usage_rows=rows, as_of=as_of, shared=[])
        data = replace(data, policy=replace(data.policy, anomaly_recent_days=7))
        assert len(hits(data, "FO012")) == expected, as_of


def test_fo014_exactly_on_target_is_fine(ds: Dataset) -> None:
    on_target = mini(
        ds,
        usage_rows=[usage(date(2026, 10, 5))],
        as_of=EOM,
        shared=[],
        outcomes=[Outcome(date(2026, 10, 5), "support-copilot", 41, 10, "t")],  # $2.05 / 41 = 0.05
    )
    assert hits(on_target, "FO014") == []
    over = replace(on_target, outcomes=[Outcome(date(2026, 10, 5), "support-copilot", 40, 10, "t")])
    assert len(hits(over, "FO014")) == 1


def test_fo015_exactly_at_the_utilisation_floor_is_fine(ds: Dataset) -> None:
    def case(busy: str) -> Dataset:
        return mini(
            ds,
            usage_rows=[],
            gpu=[gpu(date(2026, 10, 5), prov="10", busy=busy)],
            as_of=EOM,
            shared=[],
        )

    assert hits(case("5"), "FO015") == []
    assert len(hits(case("4.9"), "FO015")) == 1


def test_fo017_does_not_pile_on_unregistered_apps(ds: Dataset) -> None:
    data = mini(ds, usage_rows=[usage(date(2026, 10, 5), app="ghost")], as_of=EOM, shared=[])
    assert hits(data, "FO017") == []
    assert len(hits(data, "FO001")) == 1


def test_fo007_does_not_ask_for_a_budget_for_unassigned_spend(ds: Dataset) -> None:
    data = mini(ds, usage_rows=[usage(date(2026, 10, 5), app="ghost")], as_of=EOM, shared=[])
    assert [f for f in hits(data, "FO007") if f.subject == cost.UNASSIGNED] == []
