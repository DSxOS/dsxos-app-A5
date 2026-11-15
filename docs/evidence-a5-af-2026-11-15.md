# A5-AF: evidence, 2026-11-15

Requirements: [requirements-a5-anti-flicker.md](requirements-a5-anti-flicker.md). Commit `a1d3c74`.

| AC | Verdict | Evidence |
|---|---|---|
| AC1 | PASS | Independent validator, DSxOS-NRG VM (`hostname` = `dsxos`), throwaway `python:3.11-slim` + `glpk-utils`, tree `git archive a1d3c74`: `python -m pytest -q -rA -p no:cacheprovider tests` gives `29 passed in 1.66s`, exit 0. The five new tests pass. All existing tests pass unchanged |
| AC2 | PASS | Same container: `python -m py_compile *.py`, exit 0 |
| AC3 | pending | Live on DSxOS-NRG after the submodule pin and deploy |

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
