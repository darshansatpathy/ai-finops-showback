# Methodology

How each number is produced, and where it stops being trustworthy.

## Cost of a usage record

`input_tokens x input price + output_tokens x output price + cached_input_tokens x cached price`, all per million, using the price in effect on that day, rounded to the cent once (half to even). Every total above that is a sum of cents, which is why the team table, the app table and the chargeback CSV agree exactly. See [ADR 0001](adr/0001-reconcile-to-the-cent.md).

## Cost of GPU capacity

`hours_provisioned x hourly rate`. Busy hours do not change the bill; they change the utilisation figure. Idle cost is `(provisioned - busy) x rate` and is reported by rule `FO015`, not subtracted from anything.

## Shared costs

A shared cost has a monthly amount and a driver: tokens, requests, or an even split. It is split across apps that spent in that month with the largest-remainder method, so the parts equal the whole. In a partial month the amount is scaled by the share of the month the data covers, so a half month does not carry a whole month's platform cost. See [ADR 0003](adr/0003-shared-costs-have-an-explicit-driver.md).

## Budget and forecast

Spend is direct plus allocated shared cost for a team in a month. The forecast is spend divided by the share of the month covered: a straight line. It knows nothing about weekends, launches or month-end jobs. States:

- `over`: spend already exceeds the budget.
- `forecast-over`: it does not yet, but the run-rate will.
- `warn`: used at least `budget_warn_pct` and the forecast stays within budget. Mid-month this is rare, because a team that has used 80% of its budget half-way through is usually forecast over, which is the stronger signal.
- `ok`.

## Anomalies

For each app, a day's direct spend is compared with the median of the previous `anomaly_window_days` days. The score is the modified z-score, `0.6745 x (x - median) / MAD`, flagged above `anomaly_threshold` (3.5 is the value Iglewicz and Hoaglin suggest) *and* when the increase is at least `anomaly_min_increase_usd`. The dollar floor stops a statistically odd but cheap day from paging anyone. Median and MAD are used so that a first runaway day does not hide the second. See [ADR 0004](adr/0004-robust-anomaly-detection.md).

## Unit economics

Per app per month: cost (direct plus allocated) divided by requests, by outcomes and by the month's peak daily active users. A partial month compares like with like because requests, outcomes and pro-rated shared cost all cover the same days.

## What none of this knows

Reserved or committed-use discounts, spot pricing, network and storage charges, vendor invoices, credits, and taxes. The tool prices what the usage records say at the prices in the catalogue. Reconciling that to a real invoice is a separate job that this repository does not do.
