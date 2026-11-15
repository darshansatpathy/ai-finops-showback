# ADR 0002: Money is Decimal, and prices are written as strings

## Status

Accepted

## Context

Binary floating point cannot represent most prices exactly. Errors are tiny per record and become visible after millions of tokens and many records.

## Decision

All money is `decimal.Decimal`. Prices in TOML are strings, and the loader rejects a float with a message that says to write a string. Token counts are integers. Nothing converts money through `float`.

## Consequences

- A price pasted as `3.0` fails loudly instead of silently becoming an inexact number.
- Authors have to quote prices, which looks fussy.
- Percentages and scores in reports are display values and are computed from Decimals too.
