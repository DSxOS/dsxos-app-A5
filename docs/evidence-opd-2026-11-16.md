# OPD: evidence, 2026-11-16 (A5)

Requirements: [requirements-opd-operational-datapoints.md](requirements-opd-operational-datapoints.md). Implementation 7d52cb2+703364d.

| AC | Verdict |
|---|---|
| AC1 | PASS |
| AC2 | PASS |
| AC3 | pending (live on DSxOS-NRG after the site config and pin update) |

Independent validator (NRG VM `dsxos`, `git archive 703364d`): py_compile 0; pytest 82 passed, exit 0. AC1 (a)-(f) PASS, AC2 PASS. In-test legacy copy equals `ee8a5d4:model.py` (renames only). Spot check: 40 random equal-limit cases (negative prices, PV, L≤0, binding import) — 0 diffs in cost, import and lower overrun.
