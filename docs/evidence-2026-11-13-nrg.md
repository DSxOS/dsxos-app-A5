# A5-AUTH: evidence, 2026-11-13

Requirements: [requirements-client-credentials-glpk.md](requirements-client-credentials-glpk.md). Commit `debf61d`.

| AC | Verdict | Evidence |
|---|---|---|
| AC1 | PASS | Python 3.11 container on Taltech-ps-dt (`dsxos`): `pip install -r requirements.txt` exit 0, `python -m py_compile *.py` exit 0. Implementer and independent validator |
| AC2 | PASS | Stub HTTP server: the first request is `POST /api/auth/token` (form `grant_type=client_credentials`, `client_id`, `client_secret`); every following request carries `Authorization: Bearer <token>`. With 401 from the token endpoint: exit 1, message "could not obtain an API token … Stopping.", no further request, no `TypeError`. The secret appears in no output or log. Implementer and independent validator |
| AC3 | PASS | DSxOS-NRG (site commit with submodule `a5` at `debf61d`; deploy Succeeded 2026-11-13 21:52:46Z): `docker exec a5 which glpsol` → `/usr/bin/glpsol`, `GLPSOL--GLPK LP/MIP Solver 5.0` |
| AC4 | PASS | DSxOS-NRG, run 2026-11-13 22:00:11Z: token obtained (no 401), `Termination condition: optimal` (about 21 s), "datapoint prognosis was posted: {'id': 45925, … 'datapointId': 530}". The DB has `ess_p_a5_test` (id 530) with lastPrognosisId 45925 and 454 readings, 22:00:11–05:33:11Z, −57.6 kW … +113 kW. No device write is involved |

The first deploy failed at "Check out submodules" because this repository was private and the site runner checks out
HTTPS submodules anonymously. The owner made the repository public; the redeploy succeeded.

Findings for the follow-up audit (not part of A5-AUTH):
- **Forecasts are truncated.** Readings are fetched without paging (`query_utils.get_last_prognosis_readings`), so the
  data server's default page of 500 applies: `len(prod) = len(cons) = 500` on NRG. The plan covers about 7.3 h instead
  of about 25 h.
- **SoC model.** `ESS_SOC_0` = 60.7 % while the battery is at about 46–49 %, because the start energy is read as
  "above ess_min_soc". The SoC bounds are 0..100 of a mixed absolute/effective quantity.
