# Adding an app, a model or a price change

## Purpose

A team starts using AI, a new model is adopted, or a provider changes a price.

## Triggers

- `FO001` reports an unregistered app.
- `FO002` or `FO003` reports a model or GPU with no price.
- A provider announces new prices.

## First checks

- Read what `finops check` actually says before changing anything.
- Confirm the data is current: rule `FO013` and the date in `reports/showback.md`.

## Steps

1. For a new app, add `[[app]]` to `config/org.toml` with its team, a cost centre, its environment and an `outcome_name`. Add a `[[budget]]` if the team has none.
2. For a new model or GPU, add a `[[model]]` or `[[gpu]]` record to `config/prices.toml`, as strings.
3. For a price change, add a *new* record with a later `effective_from`. Never edit the old one, because earlier months must keep their price.
4. Set `target_cost_per_outcome` once the app has a month of data.
5. Run `finops check`, `finops report`, and commit the config together with the regenerated reports.

## Verification

- `finops check` has no `FO001` to `FO007` findings for the new app.
- The new records appear in `reports/showback.md`.

## Escalation

The provider's invoice and these figures disagree: this tool prices usage, it does not read invoices. Take the difference to finance and the provider.
