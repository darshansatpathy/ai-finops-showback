# ADR 0005: Reports are generated from data only, committed, and checked for freshness

## Status

Accepted

## Context

A report that reads the clock or the network changes between runs, so CI cannot tell a stale file from a current one, and a diff shows noise.

## Decision

Reports and the chargeback CSV depend only on the committed config and data. `as_of` is the newest record, not today. Only rule `FO013` (freshness of the export) takes a date, and it takes it as an argument. `finops report --check` and `finops sample --check` fail when a committed file differs. The tool uses only the Python standard library.

## Consequences

- The same inputs always give the same bytes, which makes review of a cost change a normal diff.
- A real deployment would feed new exports in on a schedule; this repository ships a fixed synthetic example.
- Generated files add review noise, which is the cost of knowing they are current.
