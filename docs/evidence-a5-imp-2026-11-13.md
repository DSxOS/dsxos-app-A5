# A5-IMP: evidence, 2026-11-13

Requirements: [requirements-a5-improvements.md](requirements-a5-improvements.md). Commit `4b28df2`.

| AC | Verdict | Evidence |
|---|---|---|
| AC1 | PASS | Taltech-ps-dt (`dsxos`), `python:3.11-slim` + `glpk-utils` (GLPK 5.0): `python -m pytest -q -rA tests` gives **24 passed**, exit 0. Implementer and independent validator. The hand-checked optimum holds (discharge 10.000 kWh, charge 11.0803 kWh = 10/0.95²) |
| AC2 | PASS | `py_compile *.py` exit 0; no `import *`; no assignment to `np`, `pd` or `value`. Implementer and independent validator |
| AC3 | PASS | DSxOS-NRG: site `ee50ec3` (submodule `a5` at `4b28df2`), deploy Succeeded 2026-11-13 22:42:37Z. See below |

AC3, the run of 2026-11-13 22:45:10Z, with the unchanged NRG `a5.yaml` (interval 60, import 170 kW, export 0, SoC 15–80 %):

- **Log:**
  - `inputs: Pmax=200.0 kW, capacity=438.0 kWh, E0=199.7 kWh (SoC 45.6 %), Eend=199.7 kWh, forecast values price/load/pv=99/2161/2000, start=2026-11-13T22:45:00Z`.
  - `solved (ok/optimal): 1441 steps 2026-11-13T22:45:00Z .. 2026-11-14T22:45:00Z, cost 263.78 EUR, end energy 199.7 kWh`.
  - The run took 5 s.
- **DB (prognosis 45955 of `ess_p_a5_test`):** 1441 readings over 24.0 h, 0 readings off a minute boundary,
  −110.7 … +118.5 kW.
- **SoC, recomputed from the posted plan:**
  - E_min 65.68 kWh = **15.00 %**; E_max 350.38 kWh = **80.00 %**; E_end 199.70 kWh = E0.
  - Discharged / charged = 270.5 / 299.7 = 0.9026 = 0.95².
- **Comparison with A5-AUTH (before this change):** 500 forecast values were read, the plan covered 7.3 h and SoC0 was
  60.7 %.

Independent validator findings (no defects against R1–R14). Weaknesses for a follow-up:
- **Battery cycling.** With a PV surplus, export 0 and a full battery, the plan cycles the battery to burn the surplus
  through losses (cheaper in the model than the export penalty).
- **Forecast after the aligned start.** A forecast that starts after the aligned start gives a fallback instead of a
  plan.
- **One extra step.** One step is planned past the forecast horizon.
- **Test coverage.** Some AC1 sub-items are proven only indirectly (paging sort, step count in `main`, the separate end
  datapoint, the import/export exclusivity assertion).
- **Error wording and config strictness.** A missing forecast datapoint says "reading … failed"; a non-numeric value
  only reaches the catch-all; a positive `pccExportLimitW` is now rejected.
