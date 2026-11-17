# SFU evidence, 2026-11-17 (A5)

Spec: `docs/requirements-sfu-soc-fraction-usable-energy.md`. Branch `fix/sfu` at `b00f9b9`, off `main` `5caba3b`.
Implemented by a module-worker. Validated by an independent validator agent, which reproduced the checks.

| AC | Verdict | Evidence |
|---|---|---|
| AC1 (a)-(d) | PASS | See the command below. The validator reviewed the diff against R1–R6: `0 <= min < max <= 1` with the percent hint; bounds without `/100`; every energy input converted with `capacity*min + clamp(u, 0, capacity*(max-min))` and a WARNING on clamp; the R4 INFO line; no objective, ramp or loss change; docs updated. |
| AC2 | NOT RUN | Needs the NRG deploy and the owner's config push. |

## AC1: pytest (validator, host `dsxos` = NRG VM)

`git archive fix/sfu`, extracted to a temp dir and run in a throwaway container of the deployed app image:

```
sudo docker run --rm -v $PWD:/w -w /w --entrypoint sh python-app-a5 -c 'pip install -q pytest==8.3.5 >/dev/null 2>&1; python -m pytest -q; echo EXIT=$?'
...
94 passed in 2.39s
EXIT=0
```

Teardown: the temp dirs and archives were removed (`ls -d /tmp/sfu*` reports none), and no running app containers were touched.
