# SFU evidence, 2026-11-17 (A5)

Spec: `docs/requirements-sfu-soc-fraction-usable-energy.md`. Branch `fix/sfu` at `b00f9b9`, off `main` `5caba3b`.
Implemented by a module-worker. Validated by an independent validator agent, which reproduced the checks.

| AC | Verdict | Evidence |
|---|---|---|
| AC1 (a)-(d) | PASS | See the command below. The validator reviewed the diff against R1–R6: `0 <= min < max <= 1` with the percent hint; bounds without `/100`; every energy input converted with `capacity*min + clamp(u, 0, capacity*(max-min))` and a WARNING on clamp; the R4 INFO line; no objective, ramp or loss change; docs updated. |
| AC2 | PASS | See "AC2 live" below. |

## AC1: pytest (validator, host `dsxos` = NRG VM)

`git archive fix/sfu`, extracted to a temp dir and run in a throwaway container of the deployed app image:

```
sudo docker run --rm -v $PWD:/w -w /w --entrypoint sh python-app-a5 -c 'pip install -q pytest==8.3.5 >/dev/null 2>&1; python -m pytest -q; echo EXIT=$?'
...
94 passed in 2.39s
EXIT=0
```

Teardown: the temp dirs and archives were removed (`ls -d /tmp/sfu*` reports none), and no running app containers were touched.

## AC2 live (NRG, after the deploy of NRG `defb40b`, deploy job Succeeded 18:48:40Z)

First run after the deploy, 2026-11-17 19:00:10Z (`sudo docker logs a5` on host `dsxos`):
- The R4 line shows `ess_min_soc=0.15, ess_max_soc=0.8`, `capacity=350 kWh`, and usable start=0.000 kWh -> total start=52.500 kWh, usable end=0.000 kWh -> total end=52.500 kWh.
- Result: solved (ok/optimal): 1666 steps, cost 428.38 EUR; plan posted to B1_PIXII_704_WSet.

SQL read of `datapoint.last_reading_value` at 19:00:35–38Z:
- `ess_1_min_batt_op_lim` = 0.15 and `ess_1_max_batt_op_lim` = 0.8, equal to the logged values.
- `B1_PIXII_713_WHRtg` = 350000, so the capacity is 350 kWh, as logged.
- `B1_PIXII_713_WHAvail` = 0, so usable energy is 0 kWh, as logged. `bess_SOC` = 0.143 is below the 0.15 limit.
- Total = 350 × 0.15 + 0 = 52.5 kWh, as logged.

## SFU-A1 (usable capacity, SoC limits removed)

Branch `fix/sfu-a1` at `b51e152`. Validated by an independent validator agent.

| AC | Verdict | Evidence |
|---|---|---|
| AC1'(a)-(d) | PASS | The validator reviewed `git diff main..fix/sfu-a1`. `ess_min_soc` and `ess_max_soc` are in REMOVED (stale-parameter error) and gone from operational, validation, units and resolution. Bounds are [0, capacity]. Every energy input is clamped to [0, capacity] with a WARNING, and the default end target is the clamped start. No conversion or `/100` is left. The R4' line has no SoC values. The objective, ramp and loss terms are untouched, and every changed existing test keeps its intent. |
| AC2' | PASS | See "AC2' live" below. |

pytest on host `dsxos` (NRG VM), from `git archive fix/sfu-a1` in a mktemp dir, run with `sudo docker run --rm -v $PWD:/w -w /w --entrypoint sh python-app-a5 -c 'pip install -q pytest==8.3.5 >/dev/null 2>&1; python -m pytest -q …'`:

```
85 passed in 3.03s
```

The worker's own run gave the same count with `EXIT=0` from pytest.

Cosmetic leftovers, not blocking: stale "SoC" wording in a comment or docstring, and one continuation-line indent.

### AC2' live (NRG `3a0b78a`, deploy job Succeeded 19:44:43Z)

First quarter-hour run after the deploy, 2026-11-17 20:00:10Z, on host `dsxos`:
- The log line shows capacity=227.5 kWh (usable), start energy=59.850 kWh, end target=59.850 kWh, with no SoC values.
- Result: solved (ok/optimal): 1606 steps, cost 421.09 EUR; plan posted to B1_PIXII_704_WSet.

SQL read at 20:01:20Z:
- `B1_PIXII_713_WHRtg` = 227500, so the capacity is 227.5 kWh.
- `B1_PIXII_713_WHAvail` = 59850, so the start energy is 59.85 kWh.

Both equal the logged values.

Note: the device register `ess_1_max_E` switches between 350000 and 438000 Wh (87.5 kWh per PIXII unit, 4 or 5 units). `WHRtg` therefore switches between 227.5 and 284.7 kWh. The 19:45 run used 284.7 kWh, which equalled `WHRtg` at that time.
