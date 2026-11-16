# OPD: evidence, 2026-11-16 (A5)

Requirements: [requirements-opd-operational-datapoints.md](requirements-opd-operational-datapoints.md). Implementation 7d52cb2+703364d.

| AC | Verdict |
|---|---|
| AC1 | PASS |
| AC2 | PASS |
| AC3 | PASS (DSxOS-NRG, see below) |

Independent validator (NRG VM `dsxos`, `git archive 703364d`): py_compile 0; pytest 82 passed, exit 0. AC1 (a)-(f) PASS, AC2 PASS. In-test legacy copy equals `ee8a5d4:model.py` (renames only). Spot check: 40 random equal-limit cases (negative prices, PV, L≤0, binding import) — 0 diffs in cost, import and lower overrun.

## AC3: live on DSxOS-NRG (site `8c71b7f`; update-config 21:09:40Z and deploy 21:10:56Z, both Succeeded; first runs 21:15Z)

- **Operator datapoints**, created by update-config with `initialReadingValue`: `ess_max_P_charge` 50000 W,
  `ess_max_P_discharge` 30000 W, `ess_min_soc` 15, `ess_max_soc` 80. `pcc_p_max_p` is 150000 and `pcc_p_min_p` 15000.
- **Logs.** Each app logged all 7 limits with `(dp <id>)` sources and finished with exit 0:
  - A5 at 21:15:10: `ok/optimal`, 1531 steps, about 4 s, plan posted to `B1_PIXII_704_WSet`.
  - A4 at 21:15:10: `ok/optimal`, 1806 steps, about 1 s.
  - A1 at 21:15:40: `PCC window [15.0, 150.0] kW`, `ok/optimal`, 1531 steps, about 7 s, total correction 0 kWh. This is
    A1's first successful run since `3f93fd1` (2026-11-15).
- **Plans in the DB** (latest prognoses 49236, 49237, 49235):
  - A5 and A1: −30.00 … +50.00 kW;
  - A4: 0 kW (idle).
- **SoC recomputed from the plans** (E0 294.0 kWh, capacity 438 kWh, η 0.95):
  - A5 and A1: 16.92 … 80.00 %;
  - A4: 67.12 % throughout;
  - all end at 294.0 kWh.
- So the plans stay within the 15–80 % window and the [−30, +50] kW caps.
