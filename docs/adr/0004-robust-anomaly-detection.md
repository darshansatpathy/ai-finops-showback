# ADR 0004: Anomalies use median and MAD, plus a dollar floor

## Status

Accepted

## Context

A mean and standard deviation are pulled up by the very spike they should catch, so a runaway that lasts two days hides on the second. A purely statistical rule also flags cheap noise.

## Decision

Each day is scored against the median and median absolute deviation of the previous window (modified z-score, threshold 3.5), and is flagged only if it also exceeds the median by a minimum dollar amount. When the history is perfectly flat the spread falls back to ten percent of the median. Fewer than the minimum days of history are never judged.

## Consequences

- A two-day runaway is caught on both days, and the tests show it.
- Seasonality is handled only by a short window and the weekday rhythm of the data; a business with a strong monthly cycle would need a model, not this.
- A slow ramp is not an anomaly by this method. Budgets and the forecast catch that.
