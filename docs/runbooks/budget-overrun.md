# A team is over budget or forecast to be

## Purpose

Rule `FO008` (over) or `FO009` (forecast over) names a team.

## Triggers

- `finops budget` exits 1.
- Rule `FO008` or `FO009` fires in CI.

## First checks

- Read what `finops check` actually says before changing anything.
- Confirm the data is current: rule `FO013` and the date in `reports/showback.md`.

## Steps

1. Run `finops budget --month <YYYY-MM>` and read spent, forecast and state.
2. Open `reports/showback.md` and see which app and which kind (tokens, GPU, shared) drives the team's total.
3. Check `reports/anomalies.md`: a one-off spike is a different problem from sustained growth.
4. Check `reports/unit-economics.md`: if cost per outcome is flat while volume grows, the overrun is success, and the budget may be what is wrong.
5. Agree one of: reduce spend (smaller model, caching, batching, less GPU), raise the budget with a named approver, or accept the overrun this month.
6. Record the decision in the pull request that changes `[[budget]]` or the app.

## Verification

- `finops budget` shows the team as `ok` after the change, or the new budget is recorded with its approver.

## Escalation

The team disagrees with the allocation of shared costs: that is a policy decision, see ADR 0003, and belongs to whoever owns the shared service and finance.
