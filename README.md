# dsxos-app-A5 - Economic optimisation of an ESS

A5 plans the power of an energy storage system (ESS) for the coming forecast horizon so that the site's energy
cost (EUR) is minimal. It uses the price forecast, the load and PV forecasts, and the ESS state. The plan is
written as a prognosis of a datapoint (W, positive = charging). A5 runs as a DSxOS python app (its own container,
started by the platform on the app's `cron`).

Requirements: [docs/requirements-a5-improvements.md](docs/requirements-a5-improvements.md) (model, data, outcomes),
[docs/requirements-client-credentials-glpk.md](docs/requirements-client-credentials-glpk.md) (authentication, solver).
The original algorithm description: [Economic_Optimisation_Description.pdf](https://github.com/DSxOS/platform/blob/main/docs/workermodules/Economic_Optimisation_Description.pdf).

## Files

| File | Purpose |
|---|---|
| `main.py` | Orchestration: config, authentication, inputs, time grid, model, solve, output, fallback, exit code |
| `model.py` | The optimisation model (Pyomo + GLPK): `PlanInputs`, `build_model`, `solve`, `PlanResult` |
| `query_utils.py` | Data server access: token, datapoints, paged forecasts, batch output |
| `Query.py` | Small HTTP query builder |
| `Util.py` | Time grid and forecast resampling helpers |
| `debug.py` | Writes `debug_output.txt` (infeasible constraints, variables) - by default only when solving fails |
| `logger.py` | Console, `query.log` and Loki logging |
| `packages.txt` | OS packages for the platform image (`glpk-utils`) |
| `requirements.txt` / `requirements-dev.txt` | Pinned Python dependencies / plus pytest |
| `tests/` | pytest suite (`pip install -r requirements-dev.txt && pytest`; model tests need `glpsol`) |

## Model

Per time step k (length `interval`):

- **ESS:** charge `ch` and discharge `dis` in [0, Pmax], never both. The stored energy is
  `E[k+1] = E[k] + (ch·η_ch − dis/η_dis)·Δt` and must stay within [`ess_min_soc`, `ess_max_soc`] % of the capacity.
  If the start is already outside, the window is widened to the start value.
- **PCC:** import − export = load + pv + ch − dis, with pv negative for generation. Import ≤ `pccImportLimitW` and
  export ≤ −`pccExportLimitW` are **soft**: exceeding them costs `pccLimitPenaltyEurPerKWh` and is logged as a
  WARNING, so there is always a plan.
- **End:** the energy at the end should equal the start energy, or the value of `essEffectiveEndCharge` if that is set
  (soft, `endEnergyPenaltyEurPerKWh`).
- **Cost (EUR), minimised:** import · (price + grid tariff) − export · price + charged energy · degradation cost +
  penalties.

The time grid starts at the run time rounded down to `interval` and ends with the shortest forecast. If that is
shorter than `min_period`, or the solver gives no usable result, A5 re-posts the remaining part of the previous plan
(fallback). Exit code 0 = a plan or fallback was posted; 1 = configuration/input error or nothing could be posted.

## Configuration (`params` in the app YAML)

| Param | Unit | Default | Meaning |
|---|---|---|---|
| `apiEndpoint` | URL | required | Data server API, e.g. `http://localhost:8080/api` |
| `clientId`, `token` | | required | API credential: client ID and secret (exchanged for a short-lived token) |
| `npPriceIdentifier` | EUR/MWh | required | Price datapoint (forecast; its last value is used before the first forecast point) |
| `consumptionPrognosisIdentifier` | W | required | Load forecast (gross load, if PV is given separately) |
| `productionPrognosisIdentifier` | W | required | PV forecast, negative = generation |
| `ess_max_P_dp_id` | W | required | ESS power limit (last value) |
| `ess_max_E_dp_id` | Wh | required | ESS capacity (last value) |
| `ess_charge_dp_id` | Wh | required | Total stored energy now (last value; at most `maxInputAgeS` old) |
| `essEffectiveEndCharge` | Wh | start energy | Optional datapoint for the target energy at the end |
| `ess_min_soc`, `ess_max_soc` | % | required | Allowed SoC window |
| `pccImportLimitW` | W | required | PCC import limit (soft) |
| `pccExportLimitW` | W | required | PCC export limit as a negative number, 0 = no export (soft) |
| `essResultPowerPlanIdentifier` | W | required | Datapoint that receives the plan |
| `essCurrentPowerPlanIdentifier` | W | required | Datapoint whose latest plan is the fallback |
| `interval` | s | required | Plan time step |
| `min_period` | s | required | Minimum common forecast horizon |
| `essChargeEfficiency`, `essDischargeEfficiency` | | 0.95 | ESS efficiencies, (0, 1] |
| `gridTariffEurPerKWh` | EUR/kWh | 0.05 | Network tariff on imported energy |
| `essDegradationCostEurPerKWh` | EUR/kWh | 0.05 | Cost per kWh charged |
| `pccLimitPenaltyEurPerKWh` | EUR/kWh | 10 | Penalty for exceeding the PCC limits |
| `endEnergyPenaltyEurPerKWh` | EUR/kWh | 1 | Penalty for missing the end energy |
| `solverTimeLimitS` | s | 300 | GLPK time limit |
| `maxInputAgeS` | s | 900 | Maximum age of the stored-energy reading |
| `lokiUrl` | URL | `http://localhost:3100/loki/api/v1/push` | Loki push URL; empty = no Loki logging |
| `writeDebugFile` | | `on-failure` | `on-failure`, `always` or `never` |
| `essMinSafeLim` | | - | Accepted for compatibility, ignored |

`logLevel` (top level of the app YAML) is not used by A5.

## API credentials

A5 authenticates like A4: create an API credential for the app on the site (Monitoring, API credentials) and put
its client ID in `params.clientId` and its secret in `params.token`. On every run A5 exchanges them at
`<apiEndpoint>/auth/token` (`grant_type=client_credentials`) for a short-lived token. If that fails, A5 logs the
reason and stops before reading any data.
