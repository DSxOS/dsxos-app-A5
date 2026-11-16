# Operational parameters as datapoints (OPD) — A1, A4, A5

Status: **FROZEN 2026-11-16**. The owner's request and decisions are in §2. The same document is committed in
dsxos-app-A1, dsxos-app-A4 and dsxos-app-A5. Each app implements §3 for itself. §5 covers the sites. Changes only as
numbered amendments in §8.

Bases: A1 main `89bdc62`, A4 main `996f54e`, A5 main `ee8a5d4`.

## 1. Facts (2026-11-16)

- **F1. Operational limits are numbers today.** In A1, A4 and A5, the PCC limits (`pccImportLimitW`,
  `pccExportLimitW`) and the SoC window (`ess_min_soc`, `ess_max_soc`) are numbers in the app YAML.
  - The ESS power (`ess_max_P_dp_id`, or the number `essPowerLimitW` in A1/A4) and the capacity (`ess_max_E_dp_id`,
    or `essMaxCharge` in A1/A4) are a datapoint or a number.
  - Changing a limit needs a config commit and an update-config run.
- **F2. One power limit for both directions.** Each model uses one `p_max` for charge and discharge:
  - bounds `ch, dis ∈ [0, p_max]`;
  - the exclusivity big-M `ch ≤ p_max·zc`, `dis ≤ p_max·(1−zc)`;
  - in A5 also the import/export big-M.

  On NRG the real operating caps are asymmetric: discharge 30 kW, charge 50 kW. They are hard-coded in `control.yml`.
- **F3. The PCC lower limit only allows export today.**
  - `pccExportLimitW` must be ≤ 0. It becomes an upper bound on export: `exp ≤ −pccExportLimitW/1000`.
  - NRG's operator datapoints `pcc_p_max_p` (150000 W) and `pcc_p_min_p` (**+15000 W**) define a **signed** PCC power
    window, with import positive. That is how `control.yml` uses them as `pccPowerLimitMin/Max`.
  - A positive lower limit (a minimum import) cannot be expressed by the apps.
- **F4. NRG A1 fails every run since 2026-11-15.**
  - Commit `3f93fd1` put the strings `"pcc_p_max_p"` / `"pcc_p_min_p"` into the numeric params of `a1.yaml`.
  - Log: `configuration error: could not convert string to float: 'pcc_p_min_p'`, observed for example at
    2026-11-16 20:30:40Z.
- **F5. Unused parameters** (read only for an INFO line, or not at all):
  - `essMinSafeLim` in A1, A4 and A5;
  - `npPriceIdentifier` in A1 and A4;
  - `essEffectiveEndCharge` in A1.

  Unknown params are silently ignored by all three apps.
- **F6. Shared code.** `Util.py` and `query_utils.py` are identical in the three apps, and so is `read_value` in
  `main.py`. A1/A4 have `value_or_datapoint`; A5 does not.
- **F7. Datapoints available on NRG.**
  - `pcc_p_max_p` and `pcc_p_min_p`: W, `[0, 300000]`, values set by hand.
  - There is no charge/discharge power, site-level SoC-limit or other limit datapoint.
  - Pixii per-unit SoC limits exist only as fractions 0..1.
  - `initialReadingValue` is written once when a datapoint is created (platform DPI).
- **F8. ps-dt.**
  - It pins old A1/A4/A5 versions with old parameter names.
  - It has none of the limit datapoints.

## 2. Owner decisions (2026-11-16)

| # | Decision |
|---|---|
| D1 | Remove unused parameters. |
| D2 | Operational parameters take a **datapoint identifier or a number**. A string is a datapoint, whose latest value is read at every run. A number is a constant. Execution parameters stay numeric: cron, interval, `min_period`, solver limit, penalties and weights, Loki/debug, credentials. |
| D3 | Separate `ess_max_P_charge_dp_id` and `ess_max_P_discharge_dp_id` in all three apps, both **positive magnitudes**. The same datapoint (or number) may be given for both. |
| D4 | NRG gets new operator datapoints `ess_max_P_charge` (50000 W) and `ess_max_P_discharge` (30000 W), matching today's `control.yml` caps. |
| D5 | NRG gets new operator datapoints `ess_min_soc` (15 %) and `ess_max_soc` (80 %), in percent. |
| D6 | ps-dt: the YAMLs are updated to the new parameters, but the apps stay `type: disabled` until ps-dt has real ESS data. |
| D7 | Efficiencies stay numeric parameters. They are physical properties and were not part of the request. |

## 3. Requirements (each app)

- **R1. Operational parameters.** Each of these params accepts a datapoint identifier (non-empty string) or a number:

  | Param | Meaning | Unit | Apps |
  |---|---|---|---|
  | `pccImportLimitW` | upper limit of the net PCC power (import positive) | W | A1, A4, A5 |
  | `pccExportLimitW` | lower limit of the net PCC power (signed: negative = export allowed, 0 = no export, positive = minimum import) | W | A1, A4, A5 |
  | `ess_min_soc`, `ess_max_soc` | SoC window | % | A1, A4, A5 |
  | `ess_max_P_charge_dp_id`, `ess_max_P_discharge_dp_id` | charge / discharge power limit, positive magnitudes | W | A1, A4, A5 |
  | `ess_max_E_dp_id` | ESS capacity | Wh | A1, A4, A5 |

  - **Datapoint form.** The value is the datapoint's `lastReadingValue`, read once per run through the shared
    `read_value`.
    - A datapoint that is missing, or has no value, is an **input error**: exit 1, nothing posted, with an error that
      names the param and the datapoint. This is today's behaviour for input datapoints.
    - There is no staleness check: these are operator setpoints.
  - **Number form.** The value is used as is.
  - The resolved value and its source (`dp <id>` or `const`) are logged once per run in the `inputs` line.
- **R2. Validation per run, after resolving R1.** A violation is an input error for a datapoint source and a
  configuration error for a number. Both exit 1.
  - The power limits are > 0. The capacity is > 0.
  - `0 ≤ ess_min_soc < ess_max_soc ≤ 100`.
  - `pccExportLimitW ≤ pccImportLimitW`.
- **R3. Model: separate power limits.**
  - `ch ∈ [0, Pch]` and `dis ∈ [0, Pdis]`.
  - Exclusivity: `ch ≤ Pch·zc`, `dis ≤ Pdis·(1−zc)`.
  - A5's import/export big-M uses `max(Pch, Pdis)`.
  - When `Pch == Pdis`, every result is identical to the single-`p_max` model.
- **R4. Model: signed PCC window.**
  - The soft limits apply to the net PCC power `net = imp − exp = load + pv + ch − dis`:
    - `net ≤ U + oU`;
    - `net ≥ L − oL`;
    - `oU, oL ≥ 0`, penalised as today's overruns.
  - `U = pccImportLimitW/1000` and `L = pccExportLimitW/1000`.
  - For `L ≤ 0` this is equivalent to today's export limit `exp ≤ −L + o`. The existing tests keep their expected
    results.
  - Overrun reporting: "import" for `oU`, "below the lower limit" for `oL`.
  - **A1:** A1 checks and corrects the A5 plan against the same window and the same separate power limits.
- **R5. Removed and replaced parameters.**
  - Removed (D1): `essMinSafeLim`; `npPriceIdentifier` in A1/A4 (A5 still uses it); `essEffectiveEndCharge` in A1.
  - Replaced:
    - `ess_max_P_dp_id` and `essPowerLimitW` → `ess_max_P_charge_dp_id` + `ess_max_P_discharge_dp_id`;
    - `essMaxCharge` → `ess_max_E_dp_id` (number form).
  - Any removed or replaced param present in the YAML is a **configuration error** whose message names the
    replacement. A stale config must not run with silently different limits.
  - Other unknown params stay ignored as today.
- **R6. Required parameters.**
  - `pccImportLimitW`, `pccExportLimitW`, `ess_min_soc`, `ess_max_soc`, `ess_max_P_charge_dp_id`,
    `ess_max_P_discharge_dp_id` and `ess_max_E_dp_id` are required in all three apps.
  - The A1 and A4 SoC defaults 0/100 are removed.
- **R7. Docs.** README parameter tables, `example_config.yaml` and the module docstrings follow R1–R6.
- **R8. Unchanged.** Execution parameters, efficiencies, objective terms (A5-AF/A4-AF ramp, A4-A1 losses), forecast
  handling, fallback, auth and output behave as before.

## 4. Acceptance criteria (each app)

- **AC1 (pytest).** `python -m pytest -q -rA tests` passes (python:3.11-slim + glpk-utils), including new tests:
  - (a) each R1 param in datapoint form and in number form gives the same plan for the same value;
  - (b) a missing datapoint and a datapoint without a value each give exit 1 with a message naming the param, and
    nothing is posted;
  - (c) the R2 validation cases;
  - (d) asymmetric limits (charge 50 kW, discharge 30 kW): the plan never charges above 50 or discharges above 30;
    with equal limits the plan equals the old single-limit result;
  - (e) a positive lower PCC limit (minimum import) is respected: the plan keeps `net ≥ L` when feasible, and reports
    an overrun otherwise. For `L ≤ 0` the existing PCC tests keep their expected values;
  - (f) a removed or replaced param in the config is a configuration error naming the replacement.
- **AC2.** `python -m py_compile *.py` passes. README and `example_config.yaml` contain no removed params.
- **AC3 (live, DSxOS-NRG).** After the NRG config update and deploy, the first run of each app:
  - logs the resolved limits with their `dp` sources;
  - exits 0 and posts a plan, so A1 runs again (F4);
  - posts a plan whose ESS power stays within [−30 kW, +50 kW] (discharge/charge);
  - keeps SoC within 15–80 %, recomputed from the plan.

## 5. Site configuration

- **S1 (NRG datapoints).** Operator datapoints are added with `initialReadingValue`, for example in a new
  `config/datapoints/operation_limits_dps.yml` enabled in `enabled_datapoints.yml`:
  - `ess_max_P_charge` (W, 50000) and `ess_max_P_discharge` (W, 30000), each with limits `[0, 300000]`;
  - `ess_min_soc` (%, 15) and `ess_max_soc` (%, 80), each with limits `[0, 100]`.

  `pcc_p_max_p` and `pcc_p_min_p` already exist and are used as they are.
- **S2 (NRG app YAMLs).** `a1.yaml`, `a4.yaml` and `a5.yaml` use:
  - `pccImportLimitW: pcc_p_max_p`, `pccExportLimitW: pcc_p_min_p`;
  - `ess_min_soc: ess_min_soc`, `ess_max_soc: ess_max_soc`;
  - `ess_max_P_charge_dp_id: ess_max_P_charge`, `ess_max_P_discharge_dp_id: ess_max_P_discharge`;
  - `ess_max_E_dp_id: bess_max_E`.

  Removed params are deleted from the YAMLs, along with wrong comments: a5's "essEffectiveEndCharge not used" and
  "essMinSafeLim must exist". The owner's TODO lines in `a5.yaml` are removed once done.
  - Consequence: A4 and A5 then use the shared `pcc_p_max_p` (150 kW) instead of their own 170 kW / 150 kW numbers.
  - They also use the 30/50 kW caps instead of the 200 kW rating (A4) or `ess_p_a5_test` (A5).
- **S3 (NRG pins).** The submodules `external-modules/python/a1|a4|a5` move to the merged app commits.
- **S4 (ps-dt, D6).**
  - `config/external-modules/a1.yaml`, `a4.yaml` and `a5.yaml` are rewritten to the new parameters, with numbers for
    the operational limits, because ps-dt has no such datapoints.
  - Each is set to `type: disabled`.
  - ps-dt's submodule pins move to the same commits as NRG's.
  - ps-dt's `demo-a5` container is not started (disabled).
- **S5.** The NRG device-write guard runs before the NRG push. `control.yml`'s own hard-coded caps (30/50 kW) are out
  of scope.

## 6. Out of scope

- `control.yml` and the Modbus write path.
- Reading the efficiencies from datapoints.
- Pixii-derived SoC limits.
- ps-dt demo datapoints and running the apps on ps-dt.

## 7. Notes

None yet.

## 8. Amendments

None.
