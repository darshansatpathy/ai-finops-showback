# ADR 0003: Shared costs are allocated by a named driver, in proportion, and pro-rated in partial months

## Status

Accepted

## Context

A gateway, a tracing platform or an evaluation harness serves everyone. Leaving it unallocated understates every team; allocating it by a hidden rule starts arguments.

## Decision

Each shared cost declares its driver in `org.toml`: `tokens`, `requests` or `even`. It is split across the apps that spent in that month, in proportion to the driver, with exact reconciliation. In the current partial month the amount is scaled by the share of the month the data covers. If every weight is zero the split falls back to even.

## Consequences

- The rule is written down and can be changed in a pull request, not buried in a spreadsheet.
- A driver is a policy choice. Another driver would give another answer, and none of them is the true cost.
- An even split charges a tiny sandbox as much as a large product; that is sometimes what is wanted and the report shows it.
