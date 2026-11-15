"""Deterministic synthetic usage for the example organisation.

The shape is deliberate: weekday and weekend rhythm, slow growth, an underused GPU pool, one
runaway loop on 10 and 11 November, and one app with no outcome data. The numbers are invented.
Only `random.Random.random()` is used, which is stable across Python versions, so the committed
files are reproducible byte for byte and CI checks it.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from datetime import date, timedelta

START = date(2026, 10, 1)
END = date(2026, 11, 14)
SEED = 20261115
RUNAWAY_APP = "marketing-gen"
RUNAWAY_DAYS = (date(2026, 11, 10), date(2026, 11, 11))
RUNAWAY_FACTOR = 6


@dataclass(frozen=True)
class Stream:
    app: str
    model: str
    requests: int
    input_mean: int
    output_mean: int
    cached_share: float


STREAMS = [
    Stream("support-copilot", "frontier-large", 30000, 1800, 350, 0.45),
    Stream("support-copilot", "frontier-small", 20000, 900, 200, 0.30),
    Stream("doc-search", "embed-small", 120000, 600, 0, 0.0),
    Stream("doc-search", "frontier-small", 15000, 2500, 300, 0.20),
    Stream("marketing-gen", "frontier-large", 14000, 1200, 600, 0.20),
    Stream("fraud-triage", "frontier-small", 40000, 700, 80, 0.50),
    Stream("eval-sandbox", "frontier-large", 900, 1500, 300, 0.0),
]
# app -> (outcomes per request of the app's main stream, base active users)
OUTCOMES = {
    "support-copilot": ("frontier-large", 0.30, 420),
    "doc-search": ("frontier-small", 0.85, 1900),
    "marketing-gen": ("frontier-large", 0.08, 65),
    "fraud-triage": ("frontier-small", 0.50, 38),
}
GPUS = {"doc-search": (48, 0.35), "fraud-triage": (24, 0.80)}


def _rhythm(d: date, index: int) -> float:
    weekday = (1.0, 1.0, 1.0, 1.0, 1.0, 0.45, 0.35)[d.weekday()]
    return weekday * (1 + 0.004 * index)


def generate() -> dict[str, str]:
    rng = random.Random(SEED)
    usage: list[str] = []
    gpu: list[str] = []
    outcomes: list[str] = []
    day = START
    index = 0
    while day <= END:
        base = _rhythm(day, index)
        requests_by: dict[tuple[str, str], int] = {}
        for s in STREAMS:
            noise = 1 + 0.24 * (rng.random() - 0.5)
            factor = base * noise
            if s.app == RUNAWAY_APP and day in RUNAWAY_DAYS:
                factor *= RUNAWAY_FACTOR
            requests = round(s.requests * factor)
            requests_by[(s.app, s.model)] = requests
            total_in = requests * s.input_mean * (1 + 0.1 * (rng.random() - 0.5))
            cached = round(total_in * s.cached_share)
            usage.append(
                json.dumps(
                    {
                        "date": day.isoformat(),
                        "app": s.app,
                        "model": s.model,
                        "requests": requests,
                        "input_tokens": round(total_in) - cached,
                        "output_tokens": round(
                            requests * s.output_mean * (1 + 0.1 * (rng.random() - 0.5))
                        ),
                        "cached_input_tokens": cached,
                    }
                )
            )
        for app, (provisioned, util) in sorted(GPUS.items()):
            busy = provisioned * min(0.98, util * (1 + 0.2 * (rng.random() - 0.5)))
            gpu.append(
                json.dumps(
                    {
                        "date": day.isoformat(),
                        "app": app,
                        "sku": "gpu-80gb",
                        "hours_provisioned": f"{provisioned:.1f}",
                        "hours_busy": f"{busy:.1f}",
                    }
                )
            )
        for app, (model, per_request, users) in sorted(OUTCOMES.items()):
            noise = 1 + 0.1 * (rng.random() - 0.5)
            if app == RUNAWAY_APP and day in RUNAWAY_DAYS:
                noise /= RUNAWAY_FACTOR  # a runaway loop produces requests, not outcomes
            outcomes.append(
                json.dumps(
                    {
                        "date": day.isoformat(),
                        "app": app,
                        "outcomes": round(requests_by[(app, model)] * per_request * noise),
                        "active_users": round(users * base * noise),
                    }
                )
            )
        day += timedelta(days=1)
        index += 1
    return {
        "data/usage.jsonl": "\n".join(usage) + "\n",
        "data/gpu.jsonl": "\n".join(gpu) + "\n",
        "data/outcomes.jsonl": "\n".join(outcomes) + "\n",
    }
