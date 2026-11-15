"""Spend anomalies: a day that is far above what the same app spent in the preceding weeks.

Method: modified z-score (Iglewicz and Hoaglin) against the median and median absolute deviation
of the preceding window. Median and MAD are used because a single runaway day must not raise the
baseline that the next day is judged against. A day is flagged only if the score is above the
threshold and the increase is large enough in dollars to matter.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from statistics import median

from finops.cost import Line
from finops.model import Policy

MAD_SCALE = Decimal("0.6745")


@dataclass(frozen=True)
class Anomaly:
    day: date
    app: str
    cost: Decimal
    baseline: Decimal
    score: Decimal


def detect(app: str, series: dict[date, Decimal], policy: Policy) -> list[Anomaly]:
    found: list[Anomaly] = []
    for day in sorted(series):
        start = day - timedelta(days=policy.anomaly_window_days)
        history = [v for d, v in series.items() if start <= d < day]
        if len(history) < policy.anomaly_min_history:
            continue
        base = median(history)
        mad = median([abs(v - base) for v in history])
        if mad == 0:
            mad = max(base * Decimal("0.1"), Decimal("0.01"))
        score = MAD_SCALE * (series[day] - base) / mad
        increase = series[day] - base
        if score > policy.anomaly_threshold and increase >= policy.anomaly_min_increase_usd:
            found.append(Anomaly(day, app, series[day], base, score.quantize(Decimal("0.1"))))
    return found


def anomalies(lines: list[Line], policy: Policy) -> list[Anomaly]:
    """Daily direct spend per app (tokens and GPU, never allocated shared cost)."""
    per_app: dict[str, dict[date, Decimal]] = {}
    for ln in lines:
        if ln.day is None:
            continue
        series = per_app.setdefault(ln.app, {})
        series[ln.day] = series.get(ln.day, Decimal(0)) + ln.cost
    out: list[Anomaly] = []
    for app in sorted(per_app):
        out.extend(detect(app, per_app[app], policy))
    return sorted(out, key=lambda a: (a.day, a.app))
