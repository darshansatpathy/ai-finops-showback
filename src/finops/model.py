"""The data the tool reads: prices, organisation, and daily usage records.

Everything is validated structurally here and every problem is reported in one pass. Meaning
(an app that does not exist, a model with no price) is judged by the rules, not the loader, so
a damaged export still produces a report that shows the damage.

Money is `Decimal` throughout. Prices are written as strings in TOML so they never pass
through a binary float.
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

DRIVERS = ("tokens", "requests", "even")
ENVIRONMENTS = ("prod", "staging", "dev")
ZERO = Decimal(0)


@dataclass(frozen=True)
class ModelPrice:
    model: str
    effective_from: date
    input_per_mtok: Decimal
    output_per_mtok: Decimal
    cached_per_mtok: Decimal


@dataclass(frozen=True)
class GpuRate:
    sku: str
    effective_from: date
    hourly: Decimal


@dataclass(frozen=True)
class Team:
    id: str
    name: str
    cost_center: str


@dataclass(frozen=True)
class App:
    id: str
    team: str
    cost_center: str
    environment: str
    outcome_name: str
    target_cost_per_outcome: Decimal | None


@dataclass(frozen=True)
class Budget:
    team: str
    monthly_usd: Decimal


@dataclass(frozen=True)
class Shared:
    id: str
    name: str
    monthly_usd: Decimal
    driver: str


@dataclass(frozen=True)
class Policy:
    untagged_max_pct: Decimal
    budget_warn_pct: Decimal
    min_gpu_utilisation_pct: Decimal
    max_data_lag_days: int
    anomaly_window_days: int
    anomaly_min_history: int
    anomaly_threshold: Decimal
    anomaly_min_increase_usd: Decimal
    anomaly_recent_days: int


@dataclass(frozen=True)
class Usage:
    day: date
    app: str
    model: str
    requests: int
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int
    source: str


@dataclass(frozen=True)
class GpuUse:
    day: date
    app: str
    sku: str
    hours_provisioned: Decimal
    hours_busy: Decimal
    source: str


@dataclass(frozen=True)
class Outcome:
    day: date
    app: str
    outcomes: int
    active_users: int
    source: str


@dataclass(frozen=True)
class Dataset:
    root: Path
    prices: list[ModelPrice]
    rates: list[GpuRate]
    teams: dict[str, Team]
    apps: dict[str, App]
    budgets: dict[str, Budget]
    shared: list[Shared]
    policy: Policy
    usage: list[Usage]
    gpu: list[GpuUse]
    outcomes: list[Outcome]
    as_of: date


class _Problems:
    def __init__(self) -> None:
        self.items: list[str] = []

    def add(self, where: str, message: str) -> None:
        self.items.append(f"{where}: {message}")


def _decimal(raw: Any, where: str, key: str, p: _Problems, *, minimum: Decimal = ZERO) -> Decimal:
    if isinstance(raw, bool | float) or raw is None:
        p.add(where, f"`{key}` must be a string or integer (never a float), got {raw!r}")
        return ZERO
    try:
        value = Decimal(str(raw))
    except InvalidOperation:
        p.add(where, f"`{key}` is not a number: {raw!r}")
        return ZERO
    if not value.is_finite() or value < minimum:
        p.add(where, f"`{key}` must be a finite number >= {minimum}, got {raw!r}")
        return ZERO
    return value


def _date(raw: Any, where: str, key: str, p: _Problems) -> date:
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        p.add(where, f"`{key}` must be an ISO date (YYYY-MM-DD), got {raw!r}")
        return date.min


def _text(
    table: dict[str, Any], key: str, where: str, p: _Problems, *, required: bool = True
) -> str:
    v = table.get(key)
    if v is None:
        if required:
            p.add(where, f"missing `{key}`")
        return ""
    if not isinstance(v, str):
        p.add(where, f"`{key}` must be text")
        return ""
    return v


def _count(raw: Any, where: str, key: str, p: _Problems) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
        p.add(where, f"`{key}` must be a whole number >= 0, got {raw!r}")
        return 0
    return raw


def _read_toml(path: Path, p: _Problems) -> dict[str, Any]:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        p.add(str(path.name), "file not found")
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
        p.add(str(path.name), f"not valid TOML: {e}")
    return {}


def _read_jsonl(path: Path, p: _Problems) -> list[tuple[str, dict[str, Any]]]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        p.add(path.name, "file not found")
        return []
    except UnicodeDecodeError:
        p.add(path.name, "not valid UTF-8")
        return []
    rows: list[tuple[str, dict[str, Any]]] = []
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        where = f"{path.name}:{n}"
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            p.add(where, f"not valid JSON: {e.msg}")
            continue
        if not isinstance(obj, dict):
            p.add(where, "each line must be a JSON object")
            continue
        rows.append((where, obj))
    return rows


def _tables(doc: dict[str, Any], name: str, p: _Problems, file: str) -> list[dict[str, Any]]:
    raw = doc.get(name, [])
    if not isinstance(raw, list) or not all(isinstance(t, dict) for t in raw):
        p.add(file, f"`[[{name}]]` must be an array of tables")
        return []
    return raw


def _load_policy(doc: dict[str, Any], p: _Problems) -> Policy:
    t = doc.get("policy")
    where = "org.toml [policy]"
    if not isinstance(t, dict):
        p.add("org.toml", "missing [policy] table")
        t = {}

    def dec(key: str) -> Decimal:
        return _decimal(t.get(key), where, key, p)

    def whole(key: str) -> int:
        return _count(t.get(key), where, key, p)

    return Policy(
        untagged_max_pct=dec("untagged_max_pct"),
        budget_warn_pct=dec("budget_warn_pct"),
        min_gpu_utilisation_pct=dec("min_gpu_utilisation_pct"),
        max_data_lag_days=whole("max_data_lag_days"),
        anomaly_window_days=whole("anomaly_window_days"),
        anomaly_min_history=whole("anomaly_min_history"),
        anomaly_threshold=dec("anomaly_threshold"),
        anomaly_min_increase_usd=dec("anomaly_min_increase_usd"),
        anomaly_recent_days=whole("anomaly_recent_days"),
    )


def load_dataset(root: Path) -> tuple[Dataset | None, list[str]]:
    p = _Problems()
    prices_doc = _read_toml(root / "config" / "prices.toml", p)
    org = _read_toml(root / "config" / "org.toml", p)

    prices = []
    for i, t in enumerate(_tables(prices_doc, "model", p, "prices.toml"), 1):
        w = f"prices.toml [[model]] #{i}"
        prices.append(
            ModelPrice(
                _text(t, "id", w, p),
                _date(t.get("effective_from"), w, "effective_from", p),
                _decimal(t.get("input_per_mtok"), w, "input_per_mtok", p),
                _decimal(t.get("output_per_mtok"), w, "output_per_mtok", p),
                _decimal(t.get("cached_input_per_mtok"), w, "cached_input_per_mtok", p),
            )
        )
    rates = []
    for i, t in enumerate(_tables(prices_doc, "gpu", p, "prices.toml"), 1):
        w = f"prices.toml [[gpu]] #{i}"
        rates.append(
            GpuRate(
                _text(t, "sku", w, p),
                _date(t.get("effective_from"), w, "effective_from", p),
                _decimal(t.get("hourly"), w, "hourly", p),
            )
        )

    teams: dict[str, Team] = {}
    for i, t in enumerate(_tables(org, "team", p, "org.toml"), 1):
        w = f"org.toml [[team]] #{i}"
        team = Team(_text(t, "id", w, p), _text(t, "name", w, p), _text(t, "cost_center", w, p))
        if team.id in teams:
            p.add(w, f"duplicate team id `{team.id}`")
        teams[team.id] = team

    apps: dict[str, App] = {}
    for i, t in enumerate(_tables(org, "app", p, "org.toml"), 1):
        w = f"org.toml [[app]] #{i}"
        env = _text(t, "environment", w, p)
        if env and env not in ENVIRONMENTS:
            p.add(w, f"`environment` must be one of {', '.join(ENVIRONMENTS)}")
        target = t.get("target_cost_per_outcome")
        app = App(
            _text(t, "id", w, p),
            _text(t, "team", w, p),
            _text(t, "cost_center", w, p, required=False),
            env,
            _text(t, "outcome_name", w, p, required=False),
            None if target is None else _decimal(target, w, "target_cost_per_outcome", p),
        )
        if app.id in apps:
            p.add(w, f"duplicate app id `{app.id}`")
        apps[app.id] = app

    budgets: dict[str, Budget] = {}
    for i, t in enumerate(_tables(org, "budget", p, "org.toml"), 1):
        w = f"org.toml [[budget]] #{i}"
        b = Budget(_text(t, "team", w, p), _decimal(t.get("monthly_usd"), w, "monthly_usd", p))
        if b.team in budgets:
            p.add(w, f"duplicate budget for team `{b.team}`")
        budgets[b.team] = b

    shared = []
    for i, t in enumerate(_tables(org, "shared", p, "org.toml"), 1):
        w = f"org.toml [[shared]] #{i}"
        driver = _text(t, "driver", w, p)
        if driver and driver not in DRIVERS:
            p.add(w, f"`driver` must be one of {', '.join(DRIVERS)}")
        shared.append(
            Shared(
                _text(t, "id", w, p),
                _text(t, "name", w, p),
                _decimal(t.get("monthly_usd"), w, "monthly_usd", p),
                driver,
            )
        )

    policy = _load_policy(org, p)

    usage = []
    for w, r in _read_jsonl(root / "data" / "usage.jsonl", p):
        usage.append(
            Usage(
                _date(r.get("date"), w, "date", p),
                _text(r, "app", w, p),
                _text(r, "model", w, p),
                _count(r.get("requests"), w, "requests", p),
                _count(r.get("input_tokens"), w, "input_tokens", p),
                _count(r.get("output_tokens"), w, "output_tokens", p),
                _count(r.get("cached_input_tokens"), w, "cached_input_tokens", p),
                w,
            )
        )
    gpu = []
    for w, r in _read_jsonl(root / "data" / "gpu.jsonl", p):
        gpu.append(
            GpuUse(
                _date(r.get("date"), w, "date", p),
                _text(r, "app", w, p),
                _text(r, "sku", w, p),
                _decimal(r.get("hours_provisioned"), w, "hours_provisioned", p),
                _decimal(r.get("hours_busy"), w, "hours_busy", p),
                w,
            )
        )
    outcomes = []
    for w, r in _read_jsonl(root / "data" / "outcomes.jsonl", p):
        outcomes.append(
            Outcome(
                _date(r.get("date"), w, "date", p),
                _text(r, "app", w, p),
                _count(r.get("outcomes"), w, "outcomes", p),
                _count(r.get("active_users"), w, "active_users", p),
                w,
            )
        )

    days = [u.day for u in usage] + [g.day for g in gpu] + [o.day for o in outcomes]
    if not days and not p.items:
        p.add("data", "no usage, GPU or outcome records")
    if p.items:
        return None, p.items
    return (
        Dataset(
            root,
            prices,
            rates,
            teams,
            apps,
            budgets,
            shared,
            policy,
            usage,
            gpu,
            outcomes,
            max(days),
        ),
        [],
    )
