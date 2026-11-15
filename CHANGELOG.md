# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-11-13

### Added
- Cost engine: exact Decimal pricing with effective-dated prices, cached-token pricing, GPU capacity cost, and rounding that reconciles to the cent.
- Shared-cost allocation by tokens, requests or an even split, with largest-remainder rounding and pro-rating for partial months.
- Budgets with run-rate forecast and four states.
- Anomaly detection with a robust modified z-score and a dollar floor.
- Unit economics: cost per thousand requests, per outcome and per active user, against targets.
- Seventeen policy rules (FO001 to FO017), including a critical reconciliation rule.
- Synthetic dataset with a runaway loop, an idle GPU pool and an untagged app, regenerated from a fixed seed.
- Six generated outputs, five ADRs and three runbooks.

[0.1.0]: https://github.com/darshansatpathy/ai-finops-showback/releases/tag/v0.1.0
