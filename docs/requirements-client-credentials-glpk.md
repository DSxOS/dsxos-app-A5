# A5: API client credentials and GLPK solver (A5-AUTH)

Status: **FROZEN 2026-11-13** (owner request: integrate A5 into DSxOS-NRG with minimal changes). Branch
`feature/client-credentials-glpk` off `main` `56e2e09`.

## Facts

- **F1.** The data server issues short-lived JWTs. An app holds an API credential (`clientId` + secret) and exchanges
  it at `POST /api/auth/token` (form fields `grant_type=client_credentials`, `client_id`, `client_secret`). Token
  validity defaults to 3600 s (`microgrids.security.token-validity-seconds`).
- **F2.** A5 (`main.py`) sends the configured `params.token` directly as the `Authorization` header. A pasted token
  therefore stops working after at most 1 h. On Taltech-ps-dt, the deployed A5 fails every run with
  `401 Bearer token missing or invalid`, followed by `TypeError: 'NoneType' object is not subscriptable`.
- **F3.** A5 solves its model with Pyomo + GLPK (`SolverFactory('glpk')`), which needs the `glpsol` binary. The
  platform image installs OS packages only from the app's `packages.txt` (`cicd/python/app.Dockerfile`). A5 has no
  `packages.txt`, and the ps-dt container has no `glpsol`.
- **F4.** dsxos-app-A4 already implements F1 (`query_utils.get_token`, `add_header`; `main.py` reads
  `params.clientId`, with `params.token` as the client secret). Its `packages.txt` is `glpk-utils`.

## Requirements

- **R1.** `main.py` reads `params.clientId` and uses `params.token` as the client secret. Before any data request it
  obtains a JWT with the F1 flow, and every later request carries `Authorization: Bearer <jwt>`. This is the same
  config contract as A4.
- **R2.** If the token request fails (no response, or no `access_token`), A5 logs an error naming the cause (never the
  secret) and exits with a non-zero code **before** any data request. It must not fail later with a `TypeError`.
- **R3.** `packages.txt` contains `glpk-utils`.
- **R4.** No other behaviour change: the model, inputs and output are unchanged. `example_config.yaml` and the README
  document `clientId`/`token`.

## Acceptance criteria

- **AC1 (static).** `python -m py_compile` passes for all `*.py` files (Python 3.11 container).
- **AC2 (auth, offline).** With a stub HTTP server, a run sends `POST /auth/token` with the three form fields first,
  and the following `GET /datapoints` carries `Authorization: Bearer <returned token>`. With the token endpoint
  returning 401, the process exits non-zero with the R2 message and makes no other request.
- **AC3 (image).** The image built by the platform contains `glpsol` (`docker exec <ctr> which glpsol`).
- **AC4 (live, DSxOS-NRG; output to a test datapoint only).** The deployed A5 obtains a token (no 401), runs the
  solver, and posts a prognosis to `ess_p_a5_test`. Alternatively it logs a solver result that explains why no
  prognosis was posted. No device write is involved.
