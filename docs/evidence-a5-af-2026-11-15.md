# A5-AF: evidence, 2026-11-15

Requirements: [requirements-a5-anti-flicker.md](requirements-a5-anti-flicker.md). Commit `a1d3c74`.

| AC | Verdict | Evidence |
|---|---|---|
| AC1 | PASS | Independent validator, DSxOS-NRG VM (`hostname` = `dsxos`), throwaway `python:3.11-slim` + `glpk-utils`, tree `git archive a1d3c74`: `python -m pytest -q -rA -p no:cacheprovider tests` gives `29 passed in 1.66s`, exit 0. The five new tests pass. All existing tests pass unchanged |
| AC2 | PASS | Same container: `python -m py_compile *.py`, exit 0 |
| AC3 | PASS | DSxOS-NRG, site `fa9c70e` (submodule `a5` at `b3250d8`), container recreated 07:23:21Z. Independent validator, details below |

AC3, the run of 2026-11-15 07:30:10Z, with the NRG `a5.yaml` (it states the default `essRampPenaltyEurPerKw: 0.0001`):

- **Code check:** `sudo docker exec a5 grep -rl essRampPenaltyEurPerKw /` lists `/app/main.py`, so the running
  container has the change.
- **Log:**
  - `inputs: Pmax=200.0 kW, capacity=438.0 kWh, E0=184.4 kWh (SoC 42.1 %), Eend=184.4 kWh, ... start=2026-11-15T07:30:00Z`
  - `07:30:12,243 solved (ok/optimal): 916 steps 2026-11-15T07:30:00Z .. 22:45:00Z, cost 94.37 EUR (ramp 0.0377), end energy 184.4 kWh`
  - The solve took about 1.4 s.
- **DB (prognosis 47483 of `B1_PIXII_704_WSet`):** 916 readings at 1-min steps. No 15-min slot has more than 1 step
  with |ΔP| > 5 kW (limit 2). The previous plan, 47458, had up to 6 such steps in one slot, and 2 slots over the limit.
- **SoC, recomputed from the posted plan:** 42.10–53.49 % (limit 15–80 %). The end energy is 184.4 kWh, equal to Eend.
- **11:00–12:00Z:**
  - New plan: 0 kW ×9, 74 kW ×6, 90 kW ×30 (11:15–11:45), 0 kW ×15. Every step is flat within its price slot.
  - Previous plan 47458: 0 kW and ≈93 kW alternating minute to minute in the same slot.
  - Why not ≈47 kW as in §2: the forecasts had changed by the 07:30 run, and the plan now needs the whole cheap slot
    at ≈90 kW. That power is below the PCC limit, so the slot is no longer a partial, PCC-capped charge.

AC1(a)/(b), checked by the validator's probe on the same fixture:

| Penalty | Jumps with \|ΔP\| > 1 kW | Plan in the cheap slot | Objective without the ramp term |
|---|---|---|---|
| 0 | 24 | 0 / 77–81 kW alternating (the flicker) | 13.901240828259212 EUR |
| 0.0001 | 2 | flat 40 kW over 30 steps | 13.901240828259208 EUR |

Validator review of the diff `6db6c07..a1d3c74`: R1–R6 are met.

Non-blocking notes:
- The `jumps()` helper counts jumps over the whole plan, which is stricter than the AC wording.
- The AC1(c) default test checks the value that reaches `build_model`.

Cleanup: the VM's /tmp files are removed, and no `a5af-*` containers remain.

Implementer note: the first version of the fixture set the tariff and degradation to 0. That made charge/discharge
arbitrage profitable, so it was not the flicker case. The fixture now uses the A5 defaults (0.05 / 0.05), as on NRG.
