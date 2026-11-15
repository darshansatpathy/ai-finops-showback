from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest

from finops import __version__, cli, render, sample
from finops.cost import build_lines
from finops.model import Dataset

from .conftest import ROOT


def run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    code = cli.main(list(argv))
    out = capsys.readouterr()
    return code, out.out, out.err


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as e:
        cli.main(["--version"])
    assert e.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_check_text_and_exit_codes(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, "check", "--root", str(ROOT), "--today", "2026-11-15")
    assert code == 0  # default threshold is high and the sample has only medium and low
    assert "MEDIUM   FO009 growth" in out and out.rstrip().endswith("17 rules: 6 findings")
    assert (
        run(capsys, "check", "--root", str(ROOT), "--today", "2026-11-15", "--fail-on", "medium")[0]
        == 1
    )
    assert (
        run(capsys, "check", "--root", str(ROOT), "--today", "2026-11-15", "--fail-on", "critical")[
            0
        ]
        == 0
    )


def test_check_markdown(capsys: pytest.CaptureFixture[str]) -> None:
    _, out, _ = run(
        capsys, "check", "--root", str(ROOT), "--today", "2026-11-15", "--format", "markdown"
    )
    assert out.startswith("## Cost policy check") and "| medium | `FO009` | growth |" in out


def test_check_markdown_with_no_findings(capsys: pytest.CaptureFixture[str]) -> None:
    assert render.findings_markdown([], 17).strip().endswith("17 rules, no findings.")


def test_check_reports_load_errors(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    code, _, err = run(capsys, "check", "--root", str(tmp_path))
    assert code == 2 and "error:" in err


def test_stale_data_fails_the_freshness_rule(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(
        capsys, "check", "--root", str(ROOT), "--today", "2026-12-31", "--fail-on", "medium"
    )
    assert code == 1 and "FO013" in out


def test_budget_command(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, "budget", "--root", str(ROOT), "--month", "2026-11")
    assert code == 1  # growth is forecast over
    assert "growth" in out and "forecast-over" in out and "2026-10" not in out
    code, out, _ = run(capsys, "budget", "--root", str(ROOT), "--month", "2026-10")
    assert code == 0 and "warn" in out


def test_anomalies_command(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, "anomalies", "--root", str(ROOT))
    assert (
        code == 1
        and "2026-11-10 marketing-gen" in out
        and out.rstrip().endswith("2 anomalous days")
    )


def test_unit_command(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, "unit", "--root", str(ROOT), "--month", "2026-11")
    assert code == 0 and "marketing-gen" in out and "2026-10" not in out
    assert "n/a" in out  # eval-sandbox has no outcomes
    _, all_months, _ = run(capsys, "unit", "--root", str(ROOT))
    assert "2026-10" in all_months


def test_rules_command(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, "rules")
    assert code == 0 and "FO016 critical" in out


def test_commands_fail_cleanly_on_a_broken_root(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    for cmd in ("budget", "anomalies", "unit", "report"):
        assert run(capsys, cmd, "--root", str(tmp_path))[0] == 2


def test_report_writes_then_is_current_then_detects_staleness(
    capsys: pytest.CaptureFixture[str], sample_root: Path
) -> None:
    code, out, _ = run(capsys, "report", "--root", str(sample_root))
    assert code == 0 and "wrote 6 of 6 generated files" in out
    assert (
        run(capsys, "report", "--root", str(sample_root), "--check")[1].strip()
        == "6 generated files are current"
    )
    (sample_root / "reports" / "budgets.md").write_text("tampered", encoding="utf-8")
    code, out, _ = run(capsys, "report", "--root", str(sample_root), "--check")
    assert code == 1 and "stale: reports/budgets.md" in out and "1 of 6" in out
    assert run(capsys, "report", "--root", str(sample_root))[0] == 0
    assert run(capsys, "report", "--root", str(sample_root), "--check")[0] == 0


def test_report_warns_about_unpriced_records(
    capsys: pytest.CaptureFixture[str], sample_root: Path
) -> None:
    p = sample_root / "data" / "usage.jsonl"
    p.write_text(
        p.read_text(encoding="utf-8").replace("frontier-small", "mystery", 1), encoding="utf-8"
    )
    code, _, err = run(capsys, "report", "--root", str(sample_root))
    assert code == 0 and "warning:" in err and "mystery" in err


def test_the_committed_reports_are_current(capsys: pytest.CaptureFixture[str]) -> None:
    assert run(capsys, "report", "--root", str(ROOT), "--check")[0] == 0


def test_sample_data_is_reproducible(capsys: pytest.CaptureFixture[str]) -> None:
    assert sample.generate() == sample.generate()
    assert run(capsys, "sample", "--root", str(ROOT), "--check")[0] == 0


def test_sample_check_detects_change_and_regenerates(
    capsys: pytest.CaptureFixture[str], sample_root: Path
) -> None:
    (sample_root / "data" / "gpu.jsonl").write_text("{}\n", encoding="utf-8")
    code, out, _ = run(capsys, "sample", "--root", str(sample_root), "--check")
    assert code == 1 and "stale: data/gpu.jsonl" in out
    assert (
        run(capsys, "sample", "--root", str(sample_root))[1].strip()
        == "wrote 1 of 3 sample data files"
    )
    assert run(capsys, "sample", "--root", str(sample_root), "--check")[0] == 0


def test_sample_contains_the_runaway_and_the_idle_gpu() -> None:
    files = sample.generate()
    runaway = [
        line
        for line in files["data/usage.jsonl"].splitlines()
        if '"marketing-gen"' in line and '"2026-11-10"' in line
    ]
    normal = [
        line
        for line in files["data/usage.jsonl"].splitlines()
        if '"marketing-gen"' in line and '"2026-11-04"' in line
    ]
    assert len(runaway) == len(normal) == 1
    assert '"requests": ' in runaway[0]
    assert sum(1 for _ in files["data/outcomes.jsonl"].splitlines()) == 45 * 4


def test_chargeback_csv_reconciles_with_the_reports(ds: Dataset) -> None:
    lines, _ = build_lines(ds)
    rows = list(csv.DictReader(io.StringIO(render.chargeback(lines))))
    assert sum(float(r["cost_usd"]) for r in rows) == pytest.approx(
        float(sum(ln.cost for ln in lines)), abs=0.005
    )
    assert {r["month"] for r in rows} == {"2026-10", "2026-11"}
    assert {r["kind"] for r in rows} == {"tokens", "gpu", "shared"}


def test_every_report_is_deterministic_and_marked_generated(ds: Dataset) -> None:
    lines, _ = build_lines(ds)
    first = render.all_reports(ds, lines)
    assert first == render.all_reports(ds, lines)
    assert all(t.startswith("<!-- Generated") for p, t in first.items() if p.endswith(".md"))
    assert set(first) == {
        "reports/showback.md",
        "reports/budgets.md",
        "reports/anomalies.md",
        "reports/unit-economics.md",
        "reports/rules.md",
        "exports/chargeback.csv",
    }


def test_showback_totals_match_the_lines(ds: Dataset) -> None:
    lines, _ = build_lines(ds)
    text = render.showback(ds, lines)
    for month in ("2026-10", "2026-11"):
        total = sum(ln.cost for ln in lines if ln.month == month)
        assert f"Total **{render.money(total)}**" in text
    assert "47% of the month" in text and "complete month" in text


def test_anomaly_report_with_none(ds: Dataset) -> None:
    from dataclasses import replace

    quiet = replace(ds, usage=[u for u in ds.usage if u.app != "marketing-gen"])
    lines, _ = build_lines(quiet)
    assert render.anomalies_report(quiet, lines).rstrip().endswith("No anomalies.")


def test_unit_report_states(ds: Dataset) -> None:
    lines, _ = build_lines(ds)
    text = render.unit_report(ds, lines)
    assert "over target" in text and "within target" in text and "n/a" in text
