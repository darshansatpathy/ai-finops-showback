# Contributing

Thanks for taking the time to improve this project.

## Development setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
make check          # ruff, mypy --strict, pytest with an 85% coverage gate
make costs          # the checks CI runs on the example data
```

## What a change needs

- Change `config/` and `data/`, never `reports/` or `exports/`. Run `finops report` and commit the result; CI fails if they differ.
- Never edit a price record that has been used. Add a new record with a later `effective_from`, so earlier months keep their price.
- Write money as strings in TOML, never floats; the loader rejects floats.
- A new rule has an ID, a severity, a reason and a failing-case test, and boundary tests for any limit it uses.
- Anything that changes how cost is rounded, allocated or forecast gets an ADR in `docs/adr/`.
- Keep the sample synthetic. No real customer, vendor invoice or internal account data.
- Update `CHANGELOG.md` for anything a user would notice.

## Pull requests

Keep them focused, describe the behaviour change and how you tested it, and make sure
CI is green. Security issues go through private reporting, see [SECURITY.md](SECURITY.md).
