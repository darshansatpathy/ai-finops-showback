# AI FinOps showback

[![CI](https://github.com/darshansatpathy/ai-finops-showback/actions/workflows/ci.yml/badge.svg)](https://github.com/darshansatpathy/ai-finops-showback/actions/workflows/ci.yml)
[![CodeQL](https://github.com/darshansatpathy/ai-finops-showback/actions/workflows/codeql.yml/badge.svg)](https://github.com/darshansatpathy/ai-finops-showback/actions/workflows/codeql.yml)
![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue)
![Typed](https://img.shields.io/badge/mypy-strict-informational)
![Dependencies](https://img.shields.io/badge/runtime%20dependencies-0-success)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**Who spent what on AI, is it on budget, did something go wrong, and what did each outcome cost? Answered from usage exports, with totals that agree to the cent.**

AI spend is awkward to manage: it is metered in tokens, priced per model, changes without notice, and the biggest fixed cost (GPU capacity) is paid for whether or not it is used. This repository turns daily usage exports into showback by team and app, allocates shared platform costs by an explicit rule, tracks budgets with a forecast, flags runaway spend, and reports unit cost against a target. It is a command-line tool with no runtime dependencies; the example organisation is synthetic.

## What it answers

| Question | Where |
|---|---|
| Who spent what, on which model or GPU? | `reports/showback.md`, `exports/chargeback.csv` |
| Will each team stay within budget? | `finops budget`, `reports/budgets.md` |
| Did something run away? | `finops anomalies`, `reports/anomalies.md` |
| What does an outcome cost, against what we expected? | `finops unit`, `reports/unit-economics.md` |
| Can these numbers be trusted? | `finops check`: 17 rules, from "every record has an owner" to "shared costs add up to the cent" |

## The example

Five apps across four teams, 45 days of usage (1 October to 14 November 2026), invented prices, and four things planted in the data for the tool to find: a runaway loop on 10 and 11 November, a GPU pool that is mostly idle, a team heading for a budget overrun, and a sandbox with no cost centre and no outcome data.

```
$ finops check --today 2026-11-15
MEDIUM   FO009 growth: $3,870.86 so far, forecast $8,294.70 against $7,500.00 (110.6%) for 2026-11
MEDIUM   FO012 marketing-gen: 2026-11-10: $867.56 against a typical $158.19 (score 10.6)
MEDIUM   FO012 marketing-gen: 2026-11-11: $1,058.98 against a typical $158.19 (score 13.5)
MEDIUM   FO014 marketing-gen: 0.2612 per outcome against a target of 0.20 in 2026-11
MEDIUM   FO015 doc-search: `gpu-80gb` busy 35.1% of 672.0 provisioned hours in 2026-11; about $1,526.00 spent on idle hours
LOW      FO017 eval-sandbox: spends in 2026-11 but reports no outcomes, so it has no unit cost
17 rules: 6 findings
```

What that says: the growth team's `marketing-gen` app spent about six times its usual on 10 and 11 November (the loop made requests but produced no approved drafts, which is why its cost per outcome is also over target); `doc-search` pays for a GPU pool that is busy about a third of the time; and the run-rate says growth will finish the month about 11% over its budget.

```
$ finops budget --month 2026-11
2026-11 data-platform  ok            spent $3,967.50 of $11,000.00 (36.1%), forecast $8,501.79 (77.3%)
2026-11 growth         forecast-over spent $3,870.86 of $7,500.00 (51.6%), forecast $8,294.70 (110.6%)
2026-11 risk           ok            spent $1,710.52 of $4,000.00 (42.8%), forecast $3,665.40 (91.6%)
2026-11 support-eng    ok            spent $3,651.36 of $10,000.00 (36.5%), forecast $7,824.34 (78.2%)

$ finops anomalies
2026-11-10 marketing-gen: $867.56 against a typical $158.19 (score 10.6)
2026-11-11 marketing-gen: $1,058.98 against a typical $158.19 (score 13.5)
2 anomalous days

$ finops unit --month 2026-11
2026-11 doc-search       cost   $3,755.40  per 1k requests    2.0508  per outcome   0.0219  target   0.0300
2026-11 eval-sandbox     cost     $212.10  per 1k requests   17.6779  per outcome      n/a  target      n/a
2026-11 fraud-triage     cost   $1,710.52  per 1k requests    3.1430  per outcome   0.0063  target   0.0100
2026-11 marketing-gen    cost   $3,870.86  per 1k requests   11.1872  per outcome   0.2612  target   0.2000
2026-11 support-copilot  cost   $3,651.36  per 1k requests    5.3692  per outcome   0.0296  target   0.0500
```

The rule that is not in this output matters most: `FO016`, critical, fails if the allocated shared costs do not add up to exactly what was configured. It passes, so the team table, the app table and the CSV all give the same total.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

finops check --today 2026-11-15   # policy rules (the date is for the freshness rule)
finops budget                     # state and forecast per team and month
finops anomalies                  # days of anomalous spend
finops unit                       # cost per request, outcome and active user
finops report                     # markdown reports and the chargeback CSV
finops sample --check             # the sample data is reproducible from its seed
make check                        # ruff, mypy --strict, pytest with an 85% coverage gate
```

Commands: `check`, `budget`, `anomalies`, `unit`, `report`, `sample`, `rules`. `report` and `sample` take `--check` to fail when committed files are stale. To use your own data, put a `config/` and a `data/` directory in the same formats ([data formats](docs/data-formats.md)) and pass `--root`.

## What is in it

| Path | What |
|---|---|
| `config/` | Prices (effective-dated), teams, apps, budgets, shared costs, policy |
| `data/` | Daily usage, GPU and outcome records (synthetic, generated from a fixed seed) |
| `reports/`, `exports/` | Showback, budgets, anomalies, unit economics, rules, and `chargeback.csv` (generated) |
| `docs/` | [Data formats](docs/data-formats.md), [methodology](docs/methodology.md), ADRs, runbooks |

## Policy rules

| Rule | Severity | Checks |
|---|---|---|
| `FO001` | high | Every record belongs to a registered app |
| `FO002` | high | Every model used has a price in effect on that day |
| `FO003` | high | Every GPU SKU used has a rate in effect on that day |
| `FO004` | high | Busy GPU hours never exceed provisioned hours |
| `FO005` | high | No duplicate usage or GPU records for the same day |
| `FO006` | high | Every app belongs to a registered team |
| `FO007` | medium | Every team that spends has a budget, and every budget has a team |
| `FO008` | high | No team is over budget this month |
| `FO009` | medium | No team is forecast to exceed its budget |
| `FO010` | low | No team has used most of its budget |
| `FO011` | medium | Spend without a cost centre stays under the policy limit |
| `FO012` | medium | No recent day of spend is anomalous |
| `FO013` | medium | The usage export is fresh |
| `FO014` | medium | Cost per outcome is within the app's target |
| `FO015` | medium | GPU capacity is used |
| `FO016` | critical | Shared costs are allocated in full, to the cent |
| `FO017` | low | Every app that spends reports outcomes |

## Design decisions

- [ADR 0001](docs/adr/0001-reconcile-to-the-cent.md): every priced record is rounded once, and every total is a sum of cents.
- [ADR 0002](docs/adr/0002-money-is-decimal-and-prices-are-strings.md): money is `Decimal` and prices are strings.
- [ADR 0003](docs/adr/0003-shared-costs-have-an-explicit-driver.md): shared costs are allocated by a named driver and pro-rated in partial months.
- [ADR 0004](docs/adr/0004-robust-anomaly-detection.md): anomalies use median and MAD plus a dollar floor.
- [ADR 0005](docs/adr/0005-reports-are-a-function-of-the-data.md): reports depend only on the data, and are checked for freshness.

Runbooks: [a cost anomaly](docs/runbooks/cost-anomaly.md), [a budget overrun](docs/runbooks/budget-overrun.md), [adding an app, model or price change](docs/runbooks/onboarding-an-app-or-model.md).

## What has and has not been verified

Verified, by running it:

- The whole suite, including every rule failing on a purpose-built case, and boundary tests for every limit ("exactly at the threshold" is fine, one step past it is not).
- Allocation reconciles to the cent for 300 random totals and weight sets, and in the sample for both months.
- Mutation checks: 38 deliberate bugs in pricing, allocation, forecasting, anomaly detection and the rules, each caught by at least one test. The first run found 11 boundary gaps, which now have tests.
- The wheel installs into a clean environment and runs on a copy of the data (CI).

Not verified, or not claimed:

- **Prices, teams, usage and budgets are invented.** The models are fictional and the prices are not any vendor's. Nothing here says what real AI costs.
- **It does not read a real provider export.** The input format is a simple daily aggregate. Mapping a real billing export onto it, and reconciling the result to an invoice, is work this repository does not do.
- **Cost is usage times a catalogue price.** Committed-use or reserved discounts, spot capacity, credits, network, storage and taxes are not modelled.
- **The forecast is a straight line.** It knows nothing about weekends, launches or month-end jobs.
- **Shared-cost drivers are policy choices.** Another driver gives another split, and none is the true cost.
- **Anomaly detection suits a steady daily rhythm.** A strongly seasonal business would need a better model, and a slow ramp is a budget problem, not an anomaly.
- **The CSV is not FOCUS-conformant.** Its columns are modelled on the idea, not checked against the specification.
- Written and tested by an AI assistant (Claude) working with the repository owner; the design and numbers have not had an independent review.

## Contributing and security

See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md). Real usage exports reveal account structure and spend; do not commit them to a public repository.

## Licence

MIT. See [LICENSE](LICENSE).
