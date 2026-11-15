"""The repository must agree with itself: claims, links, workflows and generated files."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest
import yaml

import finops
from finops import cli, rules
from finops.model import Dataset

from .conftest import ROOT, TODAY

README = (ROOT / "README.md").read_text(encoding="utf-8")
MD = [
    ROOT / "README.md",
    ROOT / "CONTRIBUTING.md",
    ROOT / "SECURITY.md",
    ROOT / "CHANGELOG.md",
    *(ROOT / "docs").rglob("*.md"),
]
SKIP_DIRS = {".git", ".venv", "__pycache__", ".ruff_cache", ".mypy_cache", ".pytest_cache"}


def test_version_matches_pyproject() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["version"] == finops.__version__
    assert f"## [{project['version']}]" in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")


def test_markdown_links_resolve() -> None:
    broken = []
    for f in MD:
        for m in re.finditer(r"\]\(([^)#\s][^)]*)\)", f.read_text(encoding="utf-8")):
            target = m.group(1)
            if target.startswith("http"):
                continue
            if not (f.parent / target.split("#")[0]).resolve().exists():
                broken.append(f"{f.relative_to(ROOT)}: {target}")
    assert broken == []


def test_readme_numbers_match_the_code(ds: Dataset) -> None:
    assert f"{len(rules.REGISTRY)} rules" in README and len(rules.REGISTRY) == 17
    assert "Mutation checks: 38 deliberate bugs" in README
    assert "Five apps across four teams, 45 days of usage" in README
    assert len(ds.apps) == 5 and len(ds.teams) == 4
    assert len(ds.usage) // 7 == 45


def test_readme_rule_table_matches_the_registry() -> None:
    rows = re.findall(r"^\| `(FO\d{3})` \| (\w+) \| (.+) \|$", README, re.MULTILINE)
    assert [(i, s, t) for i, s, t, _ in rules.catalog()] == rows


@pytest.mark.parametrize(
    "argv",
    [
        ["check", "--today", TODAY.isoformat()],
        ["budget", "--month", "2026-11"],
        ["anomalies"],
        ["unit", "--month", "2026-11"],
    ],
)
def test_readme_command_output_is_what_the_tool_prints(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    cli.main([*argv, "--root", str(ROOT)])
    assert capsys.readouterr().out.strip() in README


def test_every_command_is_documented() -> None:
    for cmd in ("check", "budget", "anomalies", "unit", "report", "sample", "rules"):
        assert f"`{cmd}`" in README, cmd


def test_adrs_are_numbered_complete_and_linked() -> None:
    adrs = sorted((ROOT / "docs" / "adr").glob("*.md"))
    assert [p.name[:4] for p in adrs] == [f"{i:04d}" for i in range(1, len(adrs) + 1)]
    for p in adrs:
        text = p.read_text(encoding="utf-8")
        for heading in ("## Status", "## Context", "## Decision", "## Consequences"):
            assert heading in text, f"{p.name} lacks {heading}"
        assert p.name in README


@pytest.mark.parametrize(
    "path", sorted((ROOT / "docs" / "runbooks").glob("*.md")), ids=lambda p: p.stem
)
def test_runbooks_are_complete_and_linked(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for h in (
        "## Purpose",
        "## Triggers",
        "## First checks",
        "## Steps",
        "## Verification",
        "## Escalation",
    ):
        assert h in text, f"{path.name} lacks {h}"
    assert path.name in README


def test_docs_only_name_commands_and_rules_that_exist() -> None:
    known = {"check", "budget", "anomalies", "unit", "report", "sample", "rules"}
    ids = {r.id for r in rules.REGISTRY}
    for f in MD:
        text = f.read_text(encoding="utf-8")
        for cmd in re.findall(r"`finops (\w+)", text):
            assert cmd in known, (f.name, cmd)
        for rid in re.findall(r"\bFO\d{3}\b", text):
            assert rid in ids, (f.name, rid)


def test_workflows_exist_and_parse() -> None:
    for name in ("ci.yml", "codeql.yml"):
        doc = yaml.safe_load((ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8"))
        assert doc["jobs"], name


def test_ci_runs_every_gate() -> None:
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    for cmd in (
        "finops check --fail-on high --today 2026-11-15",
        "finops report --check",
        "finops sample --check",
        "--cov-fail-under=85",
        "mypy",
        "pip-audit",
    ):
        assert cmd in ci, cmd
    assert "permissions:\n  contents: read" in ci


def test_makefile_matches_ci() -> None:
    mk = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert (
        "finops check --fail-on high --today 2026-11-15 && finops report --check && finops sample --check"
        in mk
    )


def test_codeowners_and_dependabot_are_present() -> None:
    assert (ROOT / ".github" / "CODEOWNERS").read_text(
        encoding="utf-8"
    ).strip() == "* @darshansatpathy"
    dep = yaml.safe_load((ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8"))
    assert {u["package-ecosystem"] for u in dep["updates"]} == {"pip", "github-actions"}


SECRET_PATTERNS = [
    r"ghp_[A-Za-z0-9]{20,}",
    r"AKIA[0-9A-Z]{16}",
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    r"sk-ant-[A-Za-z0-9-]{20,}",
]


def test_no_secrets_or_private_addresses_in_the_repository() -> None:
    hits = []
    for f in ROOT.rglob("*"):
        if not f.is_file() or SKIP_DIRS & set(f.relative_to(ROOT).parts) or f == Path(__file__):
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        hits += [f"{f.relative_to(ROOT)}: {p}" for p in SECRET_PATTERNS if re.search(p, text)]
        if "gmail.com" in text:
            hits.append(f"{f.relative_to(ROOT)}: personal email address")
    assert hits == []


def test_example_data_names_no_real_vendor_or_model() -> None:
    text = (ROOT / "config" / "prices.toml").read_text(encoding="utf-8").lower()
    for real in ("gpt", "claude", "gemini", "llama", "openai", "anthropic", "mistral"):
        assert real not in text, real
