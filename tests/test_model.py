from __future__ import annotations

from pathlib import Path

from finops.model import load_dataset

from .conftest import ROOT


def edit(root: Path, rel: str, old: str, new: str) -> None:
    p = root / rel
    text = p.read_text(encoding="utf-8")
    assert old in text, old
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


def problems(root: Path) -> list[str]:
    ds, errs = load_dataset(root)
    assert ds is None
    return errs


def test_the_sample_loads_without_problems() -> None:
    ds, errs = load_dataset(ROOT)
    assert errs == [] and ds is not None
    assert len(ds.apps) == 5 and len(ds.teams) == 4 and len(ds.shared) == 3
    assert str(ds.as_of) == "2026-11-14"
    assert len(ds.usage) == 45 * 7


def test_missing_files_are_reported_together(tmp_path: Path) -> None:
    errs = problems(tmp_path)
    assert any("prices.toml" in e and "not found" in e for e in errs)
    assert any("org.toml" in e for e in errs)
    assert any("usage.jsonl" in e for e in errs)


def test_prices_must_not_be_floats(sample_root: Path) -> None:
    edit(sample_root, "config/prices.toml", 'input_per_mtok = "3.00"', "input_per_mtok = 3.0")
    assert any("never a float" in e for e in problems(sample_root))


def test_bad_number_and_negative_money(sample_root: Path) -> None:
    edit(sample_root, "config/prices.toml", 'hourly = "3.50"', 'hourly = "cheap"')
    edit(sample_root, "config/org.toml", 'monthly_usd = "10000"', 'monthly_usd = "-5"')
    errs = problems(sample_root)
    assert any("not a number" in e for e in errs)
    assert any(">= 0" in e for e in errs)


def test_bad_dates(sample_root: Path) -> None:
    edit(
        sample_root,
        "config/prices.toml",
        'effective_from = "2026-11-01"',
        'effective_from = "Nov 1"',
    )
    edit(sample_root, "data/usage.jsonl", '"date": "2026-10-01"', '"date": "yesterday"')
    errs = problems(sample_root)
    assert sum("ISO date" in e for e in errs) >= 2


def test_bad_json_and_non_objects_name_the_line(sample_root: Path) -> None:
    (sample_root / "data" / "usage.jsonl").write_text('{"date": 1\n[1, 2]\n\n', encoding="utf-8")
    errs = problems(sample_root)
    assert any(e.startswith("usage.jsonl:1") and "not valid JSON" in e for e in errs)
    assert any(e.startswith("usage.jsonl:2") and "JSON object" in e for e in errs)


def test_count_types(sample_root: Path) -> None:
    (sample_root / "data" / "outcomes.jsonl").write_text(
        '{"date": "2026-10-01", "app": "doc-search", "outcomes": true, "active_users": 1.5}\n',
        encoding="utf-8",
    )
    errs = problems(sample_root)
    assert any("`outcomes` must be a whole number" in e for e in errs)
    assert any("`active_users` must be a whole number" in e for e in errs)


def test_duplicate_ids_and_enums(sample_root: Path) -> None:
    edit(sample_root, "config/org.toml", 'id = "growth"', 'id = "risk"')
    edit(sample_root, "config/org.toml", 'environment = "dev"', 'environment = "lab"')
    edit(sample_root, "config/org.toml", 'driver = "even"', 'driver = "vibes"')
    errs = problems(sample_root)
    assert any("duplicate team id `risk`" in e for e in errs)
    assert any("`environment` must be one of" in e for e in errs)
    assert any("`driver` must be one of" in e for e in errs)


def test_duplicate_app_and_budget(sample_root: Path) -> None:
    edit(sample_root, "config/org.toml", 'id = "doc-search"', 'id = "fraud-triage"')
    edit(sample_root, "config/org.toml", '[[budget]]\nteam = "growth"', '[[budget]]\nteam = "risk"')
    errs = problems(sample_root)
    assert any("duplicate app id" in e for e in errs)
    assert any("duplicate budget" in e for e in errs)


def test_missing_policy(sample_root: Path) -> None:
    (sample_root / "config" / "org.toml").write_text(
        '[[team]]\nid = "a"\nname = "A"\ncost_center = "CC"\n', encoding="utf-8"
    )
    assert any("missing [policy]" in e for e in problems(sample_root))


def test_missing_required_text_and_wrong_types(sample_root: Path) -> None:
    edit(sample_root, "config/org.toml", 'name = "Growth"\n', "")
    edit(sample_root, "config/org.toml", 'team = "risk"\ncost_center', "team = 7\ncost_center")
    errs = problems(sample_root)
    assert any("missing `name`" in e for e in errs)
    assert any("`team` must be text" in e for e in errs)


def test_tables_must_be_arrays(sample_root: Path) -> None:
    (sample_root / "config" / "prices.toml").write_text(
        'model = "oops"\ngpu = 3\n', encoding="utf-8"
    )
    errs = problems(sample_root)
    assert any("must be an array of tables" in e for e in errs)


def test_invalid_toml_and_invalid_utf8(sample_root: Path) -> None:
    (sample_root / "config" / "org.toml").write_text("[[team\n", encoding="utf-8")
    (sample_root / "data" / "gpu.jsonl").write_bytes(b"\xff\xfe\x00")
    errs = problems(sample_root)
    assert any("not valid TOML" in e for e in errs)
    assert any("not valid UTF-8" in e for e in errs)


def test_no_records_at_all(sample_root: Path) -> None:
    for f in ("usage", "gpu", "outcomes"):
        (sample_root / "data" / f"{f}.jsonl").write_text("", encoding="utf-8")
    assert problems(sample_root) == ["data: no usage, GPU or outcome records"]
