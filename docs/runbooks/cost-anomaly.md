# Responding to a cost anomaly

## Purpose

`finops anomalies` or rule `FO012` reports a day of spend far above an app's normal.

## Triggers

- Rule `FO012` fires, or `finops anomalies` exits 1.
- An alert from the provider or a team about unusual usage.

## First checks

- Read what `finops check` actually says before changing anything.
- Confirm the data is current: rule `FO013` and the date in `reports/showback.md`.

## Steps

1. Run `finops anomalies` and note the app, the day and how far above typical it is.
2. Open `reports/showback.md` for the month and find which model or GPU moved. A jump in one model points at a prompt or a loop; a jump in every model points at traffic.
3. Ask the owning team (the `team` in `org.toml`) what shipped or changed that day. Check for retries, an agent loop, a missing cache or a leaked key.
4. If spend is still running, throttle or revoke at the source first. This repository only reports; it cannot stop a loop.
5. Once understood, record the cause in the pull request that fixes it, with the dollar impact.

## Verification

- `finops anomalies` shows no day after the fix has been live for a full day.
- The app's unit cost in `reports/unit-economics.md` returns to its normal range.

## Escalation

Spend is rising and nobody owns the app: escalate to the team's lead and the platform owner together. If a credential may be exposed, treat it as a security incident first.
