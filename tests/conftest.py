from __future__ import annotations

import shutil
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from finops.model import Dataset, GpuUse, Usage, load_dataset

ROOT = Path(__file__).resolve().parent.parent
TODAY = date(2026, 11, 15)


@pytest.fixture(scope="session")
def ds() -> Dataset:
    loaded, problems = load_dataset(ROOT)
    assert problems == []
    assert loaded is not None
    return loaded


@pytest.fixture
def sample_root(tmp_path: Path) -> Path:
    for d in ("config", "data"):
        shutil.copytree(ROOT / d, tmp_path / d)
    return tmp_path


def usage(
    day: date,
    app: str = "support-copilot",
    model: str = "frontier-small",
    requests: int = 1000,
    i: int = 4_000_000,
    o: int = 800_000,
    c: int = 2_000_000,
) -> Usage:
    return Usage(day, app, model, requests, i, o, c, f"test:{day}:{app}:{model}")


def gpu(
    day: date, app: str = "doc-search", sku: str = "gpu-80gb", prov: str = "10", busy: str = "5"
) -> GpuUse:
    from decimal import Decimal

    return GpuUse(day, app, sku, Decimal(prov), Decimal(busy), f"test-gpu:{day}:{app}")


def mini(ds: Dataset, *, usage_rows: list[Usage], as_of: date, **changes: object) -> Dataset:
    """A dataset with only the given usage, no GPU or outcome rows unless provided."""
    base = {"usage": usage_rows, "gpu": [], "outcomes": [], "as_of": as_of}
    return replace(ds, **{**base, **changes})  # type: ignore[arg-type]
