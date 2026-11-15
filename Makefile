.PHONY: install check test costs report audit

install:
	python -m venv .venv && .venv/bin/pip install -e ".[dev]"

check:
	ruff check . && ruff format --check . && mypy && pytest --cov=finops --cov-fail-under=85

test:
	pytest

# What CI runs against the example data (the date is fixed because the data is a fixed snapshot)
costs:
	finops check --fail-on high --today 2026-11-15 && finops report --check && finops sample --check

report:
	finops report

audit:
	pip-audit --skip-editable
