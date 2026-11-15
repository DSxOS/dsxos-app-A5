# A5 anti-flicker: ramp penalty (A5-AF)

Status: **FROZEN 2026-11-15**. The owner chose the approach in session ("Ramp penalty"). Base: A5 main `6db6c07`
(A5-IMP). Changes only as numbered amendments in §6.

## 1. Facts (DSxOS-NRG, 2026-11-15)

- **F1.** In the A5 plan of the 07:00Z run (prognosis 47458 of `B1_PIXII_704_WSet`), the ESS power flickers between
  0 and ≈93 kW from one minute to the next during 11:15–11:45Z.
- **F2.** In that slot the Nord Pool price is constant at 10 EUR/MWh, the cheapest slot of the day. The charge power is
  capped by the 170 kW PCC import limit (load ≈92 kW, PV ≈−15 kW). The plan charges ≈15.4 of the 30 minutes.
- **F3. Cause.** Within a constant-price slot, every arrangement of the charging minutes has the same cost under the
  A5-IMP R5 objective, so the LP/MIP optimum is degenerate. GLPK returns an arbitrary vertex: an on/off pattern.

## 2. Owner decision

| # | Decision |
|---|---|
| 1 | Break the tie with a small linear **ramp penalty** on the change of ESS power between consecutive steps, rather than a switch-count penalty (more binaries) or a coarser `interval`. The expected plan for F1 is a flat ≈47 kW over the slot. |

## 3. Requirements

- **R1. Ramp variables.** For k = 1..N−1, `r[k] ≥ P[k] − P[k−1]` and `r[k] ≥ P[k−1] − P[k]`, with `r[k] ≥ 0` and
  `P[k] = ch[k] − dis[k]`. No new binaries. No ramp term for step 0. The power before the plan is not an input.
- **R2. Objective.** The A5-IMP R5 objective plus `Σ_{k=1..N−1} r[k] · essRampPenaltyEurPerKw`. The term is **not**
  multiplied by Δt: the cost is per kW of change, independent of `interval`.
- **R3. Parameter.** `essRampPenaltyEurPerKw`, optional, default **0.0001** (EUR per kW of change). `0` disables the
  term, and the model is then the A5-IMP model. A negative value is a configuration error (A5-IMP R10).
- **R4. Reporting.** `PlanResult` reports the ramp cost separately (`ramp_cost_eur`). The `solved` log line shows it.
  The existing `cost_eur` remains the full objective value.
- **R5. Docs.** The README parameter table and the cost formula include the new term. `example_config.yaml` lists the
  parameter with its default.
- **R6. Unchanged.** All other A5-IMP requirements stay as they are, and all existing tests pass unchanged.

## 4. Acceptance criteria

- **AC1.** `python -m pytest -q tests` passes (python:3.11-slim + glpk-utils), including new tests for:
  - (a) **Flat plan.** A fixture with the F2 shape: 60 s steps; one 30-step constant cheap-price slot between dearer
    slots; PCC import limit binding at full charge power; enough room in the battery for only about half of the slot at
    full power. With the default penalty, there are at most 2 steps with |ΔP| > 1 kW inside the cheap slot or at its
    edges. With `essRampPenaltyEurPerKw = 0`, the fixture must produce more than 2 such steps, so the fixture does
    reproduce the flicker.
  - (b) **Small economic impact.** In (a), the objective without the ramp term is at most 0.01 EUR higher with the
    default penalty than with the penalty off.
  - (c) **Config.** A negative `essRampPenaltyEurPerKw` is a configuration error. If the parameter is absent, the
    default 0.0001 is used.
- **AC2.** `python -m py_compile *.py` passes.
- **AC3 (live, DSxOS-NRG).** With the submodule at this branch and the unchanged NRG `a5.yaml`, the first A5 run after
  the deploy:
  - logs `solved (ok/optimal)`, with a solve time of at most 60 s;
  - posts a plan in which **no 15-min price slot contains more than 2 steps with |ΔP| > 5 kW**;
  - keeps SoC within 15–80 %, recomputed from the posted plan as in the A5-IMP AC3 evidence.

## 5. Out of scope

- Ramp cost relative to the ESS power before the plan starts.
- Run-to-run stability of the plan beyond what the ramp penalty gives.
- The NRG `a5.yaml` content. The default applies; the owner commits and pushes the NRG pin.

## 6. Amendments

None.
