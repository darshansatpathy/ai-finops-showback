# Security policy

## Reporting a vulnerability

Please do not open a public issue for security problems. Use GitHub's
[private vulnerability reporting](https://github.com/darshansatpathy/ai-finops-showback/security/advisories/new)
for this repository. You should get an acknowledgement within three working days.

## Scope

In scope: the `finops` tool, in particular anything that makes a total wrong without an error, reads or writes outside the given directory, or executes input. Out of scope: the invented prices and usage in the example, and the accuracy of any cost figure for a real provider.

## Operating it safely

- The repository contains no secrets and no real billing data. Prices, teams and usage are synthetic.
- `finops` reads TOML and JSON Lines and writes only to `reports/`, `exports/` and `data/` (the last only through `finops sample`). It executes nothing from the files it reads and makes no network calls.
- Usage exports from a real provider can reveal account structure and spend. Do not commit them to a public repository.
