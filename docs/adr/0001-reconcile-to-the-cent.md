# ADR 0001: Every priced record is rounded once, and every total is a sum of cents

## Status

Accepted

## Context

Cost reports disagree in the last digit when each one rounds on its own: the team table says one thing and the chargeback CSV another. People then stop trusting the numbers, and finance reconciles by hand.

## Decision

Each usage or GPU record is priced exactly in `Decimal` and rounded to the cent once, half to even, the way an invoice line is. Every higher-level figure is a sum of those cents. Allocation of shared costs uses the largest-remainder method, so the parts add up to the whole. Rule `FO016` is critical and fails the build if the allocated shared cost is not exactly what was configured.

## Consequences

- Totals in every report and in the CSV agree to the cent, and a test checks that.
- Rounding per record means a day with many tiny records can differ by a few cents from pricing the day's total once. That is the same as an invoice and is accepted.
- Half-to-even is a choice, not a law; it avoids a systematic upward drift.
