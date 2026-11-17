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
