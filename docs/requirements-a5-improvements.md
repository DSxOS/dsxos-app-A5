# A5 improvements after the NRG integration (A5-IMP)

Status: **FROZEN 2026-11-14**. Owner decisions on audit items #1–#16 were given 2026-11-14. Branch
`feature/a5-improvements` off `feature/client-credentials-glpk` `9f86143` (A5-AUTH, deployed on DSxOS-NRG).
Changes only as numbered amendments in §6.

## 1. Facts (from the audit, A5-AUTH evidence and the NRG run 2026-11-13 22:00Z)

- **F1.** Forecast readings are fetched without paging, so the data server's default page of 500 applies (max page
  10000). On NRG, production and consumption gave 500 values and the plan covered 7 h 19 min.
- **F2.** The SoC model starts from an *absolute* SoC `(cap·min% + E)/cap` and steps in % of the min–max *window*
  (`/ESS_eff_kWh`), with bounds 0..100. The configured min/max SoC is not enforced.
- **F3.** On a failed or infeasible solve no plan is posted. The fallback to the previous plan is only reached when the
  solver succeeds with an empty result, which cannot happen. With too little forecast data the run crashes with
  `NameError`.
- **F4.** The plan starts at the run time (22:00:11) instead of an interval boundary.
- **F5.** Every plan value is posted in its own HTTP request, with no check of the response. `POST
  /prognosis-readings/batch` exists and takes a list of `{time, value, datapointPrognosisId}`.
- **F6.** Inputs on NRG (owner, 2026-11-14: "match the input data and format currently provided"):
  - `ess_charge_dp_id`: **total** stored energy, Wh (`B1_PIXII_713_WHAvail`).
  - `ess_max_E_dp_id`: capacity, Wh.
  - `ess_max_P_dp_id`: power rating, W.
  - Forecasts: W, PV negative.
  - Price: EUR/MWh.
- **F7.** `params.logLevel` is read by neither the platform's `run.py` nor A5.

## 2. Owner decisions (audit item → decision)

| # | Decision |
|---|---|
| 1 | Page through forecast readings. |
| 2 | Match the current input format (F6): the start energy is the **total** stored energy. One consistent absolute-SoC model. |
| 3 | Soft PCC limits (slack with penalty), so that there is always a plan; report the overrun. |
| 4 | Too little forecast data, or a failed solve: **use the fallback plan** (the previous plan). |
| 5 | Align the plan start to the interval. |
| 6 | Charge and discharge efficiency as parameters, default **0.95** each. |
| 7–10 | Input checks with clear messages and an age limit for the current ESS energy; batch posting with a response check; `Binary` domain, with binaries skipped where they are not needed; pinned dependencies. |
| 11 | `essEffectiveEndCharge` stays as an **option**: if set, the end energy may differ from the start. Today it is configured to be the same. `essMinSafeLim` and `count` are removed. |
| 12 | The hard-coded values become configurable `params`. |
| 13 | No name shadowing; explicit imports. |
| 14 | Code split into functions; `pytest` tests. |
| 15 | Cleanup (debug file, unused code, README, `print` → logger). |
| 16 | EUR throughout. |

## 3. Requirements

**Model (R1–R6)**

- **R1. Energy state.** The model tracks the stored energy `E[k]` in kWh, k = 0..N (N = number of steps).
  - `E[0]` = the last reading of `ess_charge_dp_id` / 1000.
  - `E[k+1] = E[k] + (ch[k]·η_ch − dis[k]/η_dis)·Δt`, where Δt = `interval`/3600 h.
  - For k ≥ 1: `E[k] ∈ [Emin, Emax]`, where `Emin = cap·ess_min_soc/100` and `Emax = cap·ess_max_soc/100`.
  - If `E[0]` is already outside that window, the violated bound is widened to `E[0]`. The plan may not move further
    out, but it is still solvable.
- **R2. ESS power.** `ch[k], dis[k] ∈ [0, Pmax]` with `Pmax` = the last reading of `ess_max_P_dp_id` / 1000.
  - They are mutually exclusive through one `Binary` per step.
  - The plan's ESS power is `ch − dis` (positive = charging), posted in W.
- **R3. PCC balance and soft limits.**
  - Balance: `imp[k] − exp[k] = load[k] + pv[k] + ch[k] − dis[k]`, where load comes from the consumption forecast and
    pv from the production forecast (negative = generation), both W → kW.
  - Limits: `imp ≤ pccImportLimitW/1000 + oImp[k]` and `exp ≤ −pccExportLimitW/1000 + oExp[k]`, with `oImp, oExp ≥ 0`.
  - Import and export are made mutually exclusive by a `Binary` only if any price is negative. With non-negative prices,
    importing costs more than exporting earns, so both at once is never optimal.
- **R4. End energy.**
  - The target is `E[N] = Eend`. `Eend` = the last reading of `essEffectiveEndCharge` / 1000 if that param is set and
    non-empty; otherwise `Eend = E[0]`. It is clipped into `[Emin, Emax]` widened as in R1.
  - The target is soft: deviation variables, penalised by `endEnergyPenaltyEurPerKWh`.
- **R5. Objective, in EUR.** Minimise Σ_k Δt · ( `imp·(price/1000 + gridTariffEurPerKWh)` − `exp·price/1000` +
  `ch·essDegradationCostEurPerKWh` + `(oImp + oExp)·pccLimitPenaltyEurPerKWh` ) + `|E[N] − Eend|·endEnergyPenaltyEurPerKWh`.
  Price is EUR/MWh → /1000 = EUR/kWh.
- **R6. Configurable parameters** (all optional, default in brackets):
  - `essChargeEfficiency` [0.95], `essDischargeEfficiency` [0.95]
  - `gridTariffEurPerKWh` [0.05], `essDegradationCostEurPerKWh` [0.05]
  - `pccLimitPenaltyEurPerKWh` [10], `endEnergyPenaltyEurPerKWh` [1]
  - `solverTimeLimitS` [300], `maxInputAgeS` [900], `lokiUrl` [`http://localhost:3100/loki/api/v1/push`]
  - `writeDebugFile` [`on-failure`; one of `on-failure`, `always`, `never`]

  Values out of range (efficiency not in (0,1], negative costs or penalties, non-positive time limit or age) are
  configuration errors (R10).

**Data (R7–R9)**

- **R7. Inputs.**
  - Forecast readings of the latest prognosis are fetched sorted by time, page size 10000, through all pages.
  - Every datapoint used must exist and have a last value; otherwise there is a clear error naming the datapoint and
    the param.
  - The `ess_charge_dp_id` reading must be at most `maxInputAgeS` old.
  - The price before the first price-forecast point is the price datapoint's last value; if that is missing, the first
    forecast value is used.
- **R8. Time grid.**
  - `start` = the run time rounded **down** to a multiple of `interval` (UTC epoch).
  - Steps are `start + k·interval` up to the end of the common forecast horizon.
  - The plan is posted as a prognosis with `time = start` and readings at those steps.
- **R9. Output.** One `POST /datapoint-prognoses`, then one `POST /prognosis-readings/batch` with all readings. If either
  response is missing, or the batch count differs, it is an error.

**Run outcome (R10–R11)**

- **R10. Outcomes and exit codes.**
  - Optimal or feasible solve: plan posted, exit 0. A positive PCC overrun is logged as WARNING with the amount.
  - Too little common forecast (`< min_period`), or any other solver result: **fallback** (R11).
  - Configuration or input error (R7, R6): ERROR and exit 1. Nothing is posted.
- **R11. Fallback.**
  - The readings of the latest prognosis of `essCurrentPowerPlanIdentifier` with time ≥ `start` are re-posted
    (R9 format) to `essResultPowerPlanIdentifier`. WARNING, exit 0.
  - If no such readings exist: ERROR, exit 1.

**Code quality (R12–R14)**

- **R12. Code structure.** `main.py` only orchestrates. Reading inputs, building the model, solving and posting are
  separate testable functions. No shadowing of `numpy`, `value` etc.; no wildcard imports; logger instead of `print`.
- **R13. Cleanup.**
  - Remove `debug_output.txt` from the repo, plus the unused `RemoteLogger.py`, `Util.calculate_count`,
    `Util.validate_inputs` and `parse_time` duplicates if unused.
  - The README describes the app, all params and the model.
  - `debug_model` runs according to `writeDebugFile`.
  - `requirements.txt` is pinned to the versions verified on NRG: numpy 2.4.6, pandas 3.1.1, pyomo 6.10.1, PyYAML 6.0.3,
    requests 2.34.2; pytest is in a separate `requirements-dev.txt`.
- **R14. Config contract.**
  - All existing params keep working. `essMinSafeLim` is accepted but ignored, with an INFO line.
  - The A5-AUTH flow (`clientId` + secret) is unchanged.

## 4. Acceptance criteria

All run in a `python:3.11-slim` container with `glpk-utils` (Taltech-ps-dt) unless stated.

- **AC1.** `pytest` passes with tests for:
  - (a) paging: 3 pages → all readings, sorted;
  - (b) the time grid: start rounded down to the interval, step count;
  - (c) input errors: a missing datapoint, a missing value, a stale ESS energy, each a clear error;
  - (d) a model case with a hand-checked optimum. Flat load, no PV, a cheap then expensive price, efficiencies 0.95: the
    plan charges in the cheap block and discharges in the expensive one, and `E` stays within `[Emin, Emax]` at every
    step;
  - (e) efficiency: the energy delivered < the energy charged by the factor η_ch·η_dis over a cycle;
  - (f) a soft PCC limit: an impossible import limit still gives a plan with the overrun reported;
  - (g) the `essEffectiveEndCharge` option is honoured;
  - (h) a negative price switches the import/export binaries on;
  - (i) fallback on too little data, fallback on a failed solve, exit 1 when no fallback exists;
  - (j) the output uses the batch endpoint and checks the count.
- **AC2.** `python -m py_compile *.py` passes; no `import *`, and no assignment to the names `np`, `pd`, `value`.
- **AC3 (live, DSxOS-NRG).** With the submodule at this branch and the unchanged NRG `a5.yaml`:
  - the run posts a plan to `ess_p_a5_test` covering the full common horizon (more than 20 h, not about 7 h);
  - its readings start on an interval boundary;
  - the SoC implied by the plan, from `WHAvail` and η, stays within 15–80 %;
  - exit 0, and the run time is under the 15-min cron.
  - No device write is involved.

## 5. Out of scope

- The platform's core `A5` task (`A5Runner`).
- Credentials from the site secrets store (future secrets audit).
- The Taltech-ps-dt `demo-a5`.

## 6. Amendments

None yet.
