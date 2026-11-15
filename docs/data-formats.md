# Data formats

Everything the tool reads is plain text in two directories. Nothing is fetched and nothing is executed.

## config/prices.toml

```toml
[[model]]
id = "frontier-large"
effective_from = "2026-11-01"       # applies from this day until a later record for the same model
input_per_mtok = "2.50"             # US dollars per million tokens
output_per_mtok = "12.50"
cached_input_per_mtok = "0.25"

[[gpu]]
sku = "gpu-80gb"
effective_from = "2026-01-01"
hourly = "3.50"                     # billed on provisioned hours
```

Money is written as a string, never a float: `3.0` is rejected. A usage record is priced by the latest record whose `effective_from` is on or before the usage day, so a price cut changes cost from its own date and leaves earlier months alone.

## config/org.toml

| Table | Keys |
|---|---|
| `[policy]` | `untagged_max_pct`, `budget_warn_pct`, `min_gpu_utilisation_pct`, `max_data_lag_days`, and the five `anomaly_*` settings. Every key is required. |
| `[[team]]` | `id`, `name`, `cost_center` |
| `[[app]]` | `id`, `team`, `environment` (`prod`, `staging`, `dev`), optional `cost_center`, `outcome_name`, `target_cost_per_outcome` |
| `[[budget]]` | `team`, `monthly_usd` |
| `[[shared]]` | `id`, `name`, `monthly_usd`, `driver` (`tokens`, `requests` or `even`) |

## data/usage.jsonl

One line per day, app and model, the way a billing export aggregates:

```json
{"date": "2026-11-03", "app": "support-copilot", "model": "frontier-large", "requests": 31204, "input_tokens": 30900000, "output_tokens": 10800000, "cached_input_tokens": 25400000}
```

`input_tokens` are the *uncached* input tokens. Cached input tokens are counted and priced separately, so nothing is counted twice.

## data/gpu.jsonl

```json
{"date": "2026-11-03", "app": "doc-search", "sku": "gpu-80gb", "hours_provisioned": "48.0", "hours_busy": "16.9"}
```

## data/outcomes.jsonl

```json
{"date": "2026-11-03", "app": "support-copilot", "outcomes": 9300, "active_users": 410}
```

An outcome is whatever the app exists to produce, named in `outcome_name`: a resolved ticket, an approved draft. It is the denominator of unit cost.

## Generated files

`finops report` writes `reports/*.md` and `exports/chargeback.csv`. `finops sample` regenerates the three data files from a fixed seed. CI fails if either differs from what is committed. The CSV columns are `month, team, cost_center, app, kind, item, requests, tokens, gpu_hours, cost_usd`. They are modelled on the idea of a common cost-and-usage format but do not claim conformance with the FinOps Foundation's FOCUS specification.
