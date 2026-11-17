# SoC limits as fractions, energy inputs as usable energy (SFU)

Status: **FROZEN 2026-11-17**. The owner decided D1–D2 on 2026-11-17. The same document is in `dsxos-app-A1`,
`dsxos-app-A4` and `dsxos-app-A5`. Changes only as numbered amendments in §7. Branch `fix/sfu` in each repo, off
`main` (A1 `8911c61`, A4 `142725f`, A5 `5caba3b`).

## 1. Facts (2026-11-17)

- **F1. New NRG inputs.** The owner points `ess_min_soc` and `ess_max_soc` at the PIXII operating-limit datapoints
  `ess_1_min_batt_op_lim` and `ess_1_max_batt_op_lim`. These are SCALAR fractions, 0..1; live values are 0.15 and
  0.80. The old operator datapoints `ess_min_soc` and `ess_max_soc` held percent (15 and 80).
- **F2. Silent failure today.** All three apps:
  - validate `0 <= ess_min_soc < ess_max_soc <= 100`;
  - compute `e_min = capacity * soc_min / 100` and `e_max = capacity * soc_max / 100`.

  With 0.15 and 0.80 the validation passes, and the bounds become 0.5–2.8 kWh for 350 kWh. `energy_bounds` widens them
  only to include the start energy, so the plan can only discharge.
- **F3. Energy input semantics (NRG).** `ess_max_E_dp_id` → `B1_PIXII_713_WHRtg` is the **gross** capacity
  (`ess_1_max_E`, 350,000 Wh).
  - The energy inputs → `B1_PIXII_713_WHAvail` (= `ess_charge`) are, by the owner's definition, the **usable** energy
    above the minimum SoC limit:
    `usable = gross × (max − min) × clamp((SoC − min)/(max − min), 0, 1)`, which equals `gross × (SoC − min)` within
    the window.
  - The usable energy ranges from 0 (at or below `min`) to `gross × (max − min)` (at or above `max`).
  - The energy inputs are A1 `essEffectiveCharge`, A4 `essEffectiveCharge` and `essEffectiveEndCharge`, and A5
    `ess_charge_dp_id` and `essEffectiveEndCharge`.
  - The models track **total** stored energy `E` within `[capacity × min, capacity × max]`, with `E[0]` fixed to the
    start-energy input.

## 2. Owner decisions (2026-11-17)

| # | Decision |
|---|---|
| D1 | `ess_min_soc` and `ess_max_soc` are **fractions only**: `0 <= ess_min_soc < ess_max_soc <= 1`. Percent values are rejected. |
| D2 | The energy inputs (start energy, and the end target where it exists) are **usable energy above `ess_min_soc`**, in Wh, as defined in F3. `ess_max_E_dp_id` is the gross capacity. The apps convert usable energy to total energy internally. |

## 3. Requirements

- **R1. Validation.**
  - After resolving the parameters (each is a number or a datapoint), each app checks
    `0 <= ess_min_soc < ess_max_soc <= 1`.
  - On failure it raises the app's existing configuration error.
  - The message names both parameters and their values. If a value is > 1, the message says the limits are
    fractions, for example "ess_min_soc=15 looks like percent; use 0.15".
- **R2. Bounds.** `e_min = capacity × ess_min_soc` and `e_max = capacity × ess_max_soc`, in kWh, without `/100`.
  Internal names, docstrings and comments that say `pct` or `%` for these values are renamed or reworded to
  fraction.
- **R3. Usable → total conversion.**
  - For each energy input `u` (kWh), the model receives `E_total = capacity × ess_min_soc + clamp(u, 0, capacity ×
    (ess_max_soc − ess_min_soc))`.
  - If `u` lies outside that range, the app logs a WARNING with the raw and clamped values.
  - Where an end target defaults to the start energy (no `essEffectiveEndCharge`), the default is the converted start
    energy.
- **R4. Resolved-inputs log line.** Before solving, each app logs one INFO line with:
  - the resolved `ess_min_soc` and `ess_max_soc` (fractions);
  - the capacity (kWh);
  - the usable start energy (kWh) and the converted total start energy (kWh);
  - for A4 and A5, the usable and total end target;
  - the charge and discharge power limits (kW);
  - the PCC limits (kW).
- **R5. Unchanged.** Everything else is unchanged:
  - the parameter names and the other parameters;
  - the units of power, capacity and PCC;
  - the objective, ramp and loss terms;
  - the outputs, posting and fallback.
- **R6. Docs.** `README.md`, `example_config.yaml` and the parameter table state:
  - fractions for `ess_min_soc` and `ess_max_soc`;
  - usable energy above the minimum SoC for the energy inputs;
  - gross capacity for `ess_max_E_dp_id`.

  Existing numeric examples (for example 15 and 90) become 0.15 and 0.90.

## 4. Acceptance criteria

- **AC1 (unit).** `python -m pytest -q` passes in each repo, with new tests:
  - (a) validation rejects `ess_min_soc=15, ess_max_soc=80`, with the "fractions" hint in the message. It accepts
    `0.15/0.80`, and rejects `0.8/0.15` and `-0.1/0.5`.
  - (b) with capacity 350 kWh, min 0.15 and max 0.80, the model bounds are 52.5 and 280 kWh.
  - (c) usable 34.3 kWh converts to total 86.8 kWh (±0.01). Usable −5 clamps to total 52.5 kWh, and usable 300
    clamps to total 280 kWh, each with a WARNING. For A4 and A5, the end target converts the same way.
  - (d) a full solve with the AC1(b)/(c) inputs keeps every `E[k]` within [52.5, 280] kWh. Existing tests pass,
    changed only where they used percent.
- **AC2 (live, NRG, after deploy and the owner's config push).** In each app's next run log on NRG:
  - the R4 line shows `ess_min_soc` and `ess_max_soc` equal to the last readings of `ess_1_min_batt_op_lim` and
    `ess_1_max_batt_op_lim`;
  - it shows a capacity of `B1_PIXII_713_WHRtg`/1000;
  - it shows a usable start energy of `B1_PIXII_713_WHAvail`/1000, with total = capacity × min + usable;
  - the solve status is ok/optimal and a plan is posted.

  The values are compared with a SQL read of `datapoint.last_reading_value`, captured.

## 5. Out of scope

- The NRG site pipelines (`ess_charge`, `control.yml`). They are site configuration, handled in the NRG repo.
- The ps-dt app configs are updated to fractions in the ps-dt repo, but the apps there stay disabled.

## 6. Notes

None yet.

## 7. Amendments

- **SFU-A1 (owner, 2026-11-17): capacity is the usable capacity, the SoC limits are removed. Replaces D1, D2, R1–R3,
  R6 and AC1(a)–(c).**
  - **Fact.** On NRG the owner changed `B1_PIXII_713_WHRtg` (`ess_max_E_dp_id`) to the usable capacity, while
    `B1_PIXII_713_WHAvail` (the energy inputs) is the usable energy in the same basis:
    - `WHRtg = gross × (max − min)`, live 350 × (0.80 − 0.15) = 227.5 kWh;
    - `WHAvail = gross × (max − min) × clamp((SoC − min)/(max − min), 0, 1)`, which lies in `[0, WHRtg]`.

    0 is the minimum operating limit and `WHRtg` is the maximum, so the SoC limits are already embedded in both inputs.
    The integrator verified this on 2026-11-17.
  - **D3 (replaces D1 and D2).**
    - `ess_max_E_dp_id` is the **usable** capacity.
    - The energy inputs are usable energy in `[0, capacity]`, used directly as the model's energy.
    - `ess_min_soc` and `ess_max_soc` are removed.
  - **R1' (replaces R1).** `ess_min_soc` and `ess_max_soc` are no longer parameters.
    - They move into the app's existing `REMOVED` map with the reason "removed (SFU-A1): the SoC limits are embedded
      in ess_max_E_dp_id (usable capacity) and the energy inputs (usable energy); delete it". A config that still has
      them fails with the app's existing stale-parameter configuration error.
    - They are removed from the OPD operational lists, the unit maps, the validation and the resolution.
  - **R2' (replaces R2).** The model bounds are `e_min = 0` and `e_max = capacity` (kWh). The model's SoC fields and
    any `%`/fraction wording are removed.
  - **R3' (replaces R3).**
    - Each energy input `u` (kWh) goes to the model as `clamp(u, 0, capacity)`, with a WARNING (raw and clamped values)
      when it clamps. There is no usable→total conversion.
    - Where an end target defaults to the start energy, the default is the clamped start energy.
  - **R4' (replaces R4).** The resolved-inputs INFO line shows:
    - capacity (kWh, usable);
    - start energy (kWh), raw and used if clamped;
    - for A4 and A5, the end target;
    - charge and discharge limits (kW);
    - PCC limits (kW).

    It shows no SoC values.
  - **R6' (replaces R6).** README, `example_config.yaml` and the parameter table describe `ess_max_E_dp_id` as the
    usable capacity and the energy inputs as usable energy in `[0, capacity]`. `ess_min_soc` and `ess_max_soc` are
    removed and listed as removed.
  - **AC1' (replaces AC1(a)–(c); AC1(d) is adapted).**
    - (a) A config with `ess_min_soc` or `ess_max_soc` fails with the stale-parameter error naming it, and nothing is
      posted. A config without them passes validation.
    - (b) With capacity 227.5 kWh, the model bounds are 0 and 227.5.
    - (c) A start energy of 34.3 is used as 34.3. −5 clamps to 0 and 300 clamps to 227.5, each with a WARNING. For A4
      and A5 the end target behaves the same way, and with no end target it equals the clamped start.
    - (d) A full solve with these inputs keeps every `E[k]` within [0, 227.5].
    - Existing tests pass, changed only where they used the SoC parameters or the conversion.
  - **AC2' (replaces AC2).** In each app's next run log on NRG:
    - the R4' line shows capacity = `B1_PIXII_713_WHRtg`/1000 and start energy = `B1_PIXII_713_WHAvail`/1000;
    - the solve is ok/optimal and a plan is posted.

    The values are compared with a captured SQL read.
  - **Site (NRG, outside the apps).**
    - The app YAMLs drop `ess_min_soc` and `ess_max_soc`. That deploy must ship together with the new app pins.
    - `control.yml` `essChargeMaxWs` becomes `WHRtg × 3600`. Without that change the window would be applied twice.
