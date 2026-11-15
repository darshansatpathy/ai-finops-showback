"""Command line: check, budget, anomalies, unit, report, sample, rules."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from finops import __version__, anomaly, budget, render, rules, sample, unit
from finops.cost import build_lines
from finops.model import Dataset, load_dataset


def _load(root: Path) -> Dataset | None:
    ds, problems = load_dataset(root)
    for p in problems:
        print(f"error: {p}", file=sys.stderr)
    return ds


def _write_or_check(root: Path, files: dict[str, str], check: bool, what: str) -> int:
    stale = []
    for rel, text in files.items():
        path = root / rel
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current != text:
            stale.append(rel)
            if not check:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8", newline="\n")
    if check:
        for rel in stale:
            print(f"stale: {rel}")
        if stale:
            print(
                f"{len(stale)} of {len(files)} {what} files are stale; run the matching command and commit"
            )
            return 1
        print(f"{len(files)} {what} files are current")
        return 0
    print(f"wrote {len(stale)} of {len(files)} {what} files")
    return 0


def cmd_check(a: argparse.Namespace) -> int:
    ds = _load(Path(a.root))
    if ds is None:
        return 2
    findings = rules.run(ds, date.fromisoformat(a.today))
    if a.format == "markdown":
        print(render.findings_markdown(findings, len(rules.REGISTRY)), end="")
    else:
        for f in findings:
            print(f"{f.severity.upper():8} {f.rule} {f.subject}: {f.message}")
        print(f"{len(rules.REGISTRY)} rules: {len(findings)} findings")
    threshold = rules.severity_rank(a.fail_on)
    return 1 if any(rules.severity_rank(f.severity) >= threshold for f in findings) else 0


def cmd_budget(a: argparse.Namespace) -> int:
    ds = _load(Path(a.root))
    if ds is None:
        return 2
    lines, _ = build_lines(ds)
    status = [b for b in budget.budget_status(ds, lines) if a.month is None or b.month == a.month]
    for b in status:
        print(
            f"{b.month} {b.team:14} {b.state:13} spent {render.money(b.spent)} of {render.money(b.budget)} "
            f"({b.pct}%), forecast {render.money(b.forecast)} ({b.forecast_pct}%)"
        )
    return 1 if any(b.state in ("over", "forecast-over") for b in status) else 0


def cmd_anomalies(a: argparse.Namespace) -> int:
    ds = _load(Path(a.root))
    if ds is None:
        return 2
    lines, _ = build_lines(ds)
    found = anomaly.anomalies(lines, ds.policy)
    for x in found:
        print(
            f"{x.day} {x.app}: {render.money(x.cost)} against a typical {render.money(x.baseline)} (score {x.score})"
        )
    print(f"{len(found)} anomalous days")
    return 1 if found else 0


def cmd_unit(a: argparse.Namespace) -> int:
    ds = _load(Path(a.root))
    if ds is None:
        return 2
    lines, _ = build_lines(ds)
    for u in unit.unit_economics(ds, lines):
        if a.month is not None and u.month != a.month:
            continue
        print(
            f"{u.month} {u.app:16} cost {render.money(u.cost):>11}  per 1k requests {render._unit(u.per_1k_requests):>9}  "
            f"per outcome {render._unit(u.per_outcome):>8}  target {render._unit(u.target):>8}"
        )
    return 0


def cmd_report(a: argparse.Namespace) -> int:
    ds = _load(Path(a.root))
    if ds is None:
        return 2
    lines, unpriced = build_lines(ds)
    for line in unpriced:
        print(f"warning: {line}", file=sys.stderr)
    return _write_or_check(Path(a.root), render.all_reports(ds, lines), a.check, "generated")


def cmd_sample(a: argparse.Namespace) -> int:
    return _write_or_check(Path(a.root), sample.generate(), a.check, "sample data")


def cmd_rules(_: argparse.Namespace) -> int:
    for rid, sev, title, why in rules.catalog():
        print(f"{rid} {sev:8} {title}\n        {why}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="finops", description="AI cost showback, budgets and unit economics"
    )
    parser.add_argument("--version", action="version", version=f"finops {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name: str, fn: object, help_: str) -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=help_)
        p.add_argument("--root", default=".", help="directory holding config/ and data/")
        p.set_defaults(fn=fn)
        return p

    p = add("check", cmd_check, "run the policy rules")
    p.add_argument("--fail-on", choices=rules.SEVERITIES, default="high")
    p.add_argument("--format", choices=("text", "markdown"), default="text")
    p.add_argument("--today", default=date.today().isoformat(), help="date for the freshness rule")
    p = add("budget", cmd_budget, "budget status and forecast per team")
    p.add_argument("--month", help="only this month, YYYY-MM")
    add("anomalies", cmd_anomalies, "days of anomalous spend")
    p = add("unit", cmd_unit, "unit economics per app")
    p.add_argument("--month", help="only this month, YYYY-MM")
    p = add("report", cmd_report, "write the markdown reports and chargeback CSV")
    p.add_argument("--check", action="store_true", help="fail if generated files are stale")
    p = add("sample", cmd_sample, "regenerate the synthetic usage data")
    p.add_argument("--check", action="store_true", help="fail if the committed data differs")
    add("rules", cmd_rules, "list the policy rules")

    args = parser.parse_args(argv)
    code: int = args.fn(args)
    return code


if __name__ == "__main__":
    sys.exit(main())
