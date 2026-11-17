"""A5 economic optimisation: plans the ESS power for the coming forecast horizon at minimum energy cost (EUR).

Run by the platform's python-app scheduler with the site's config (default /app/config.yaml).
Requirements: docs/requirements-a5-improvements.md (A5-IMP), docs/requirements-a5-anti-flicker.md (A5-AF),
docs/requirements-opd-operational-datapoints.md (OPD: operational params as number or datapoint),
docs/requirements-client-credentials-glpk.md (A5-AUTH).
Exit codes: 0 = plan (or fallback plan) posted, 1 = configuration/input error or no plan possible.
"""
import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone

import yaml

import model as a5model
import query_utils
import Util
from debug import debug_model
from logger import setup_logger

logger = logging.getLogger("A5Runner")

DEFAULTS = {
    "essChargeEfficiency": 0.95,
    "essDischargeEfficiency": 0.95,
    "gridTariffEurPerKWh": 0.05,
    "essDegradationCostEurPerKWh": 0.05,
    "pccLimitPenaltyEurPerKWh": 10.0,
    "endEnergyPenaltyEurPerKWh": 1.0,
    "essRampPenaltyEurPerKw": 0.0001,
    "solverTimeLimitS": 300,
    "maxInputAgeS": 900,
    "lokiUrl": "http://localhost:3100/loki/api/v1/push",
    "writeDebugFile": "on-failure",
    "essEffectiveEndCharge": None,
}
REQUIRED = [
    "apiEndpoint", "clientId", "token",
    "npPriceIdentifier", "consumptionPrognosisIdentifier", "productionPrognosisIdentifier",
    "ess_max_P_charge_dp_id", "ess_max_P_discharge_dp_id", "ess_charge_dp_id", "ess_max_E_dp_id",
    "pccImportLimitW", "pccExportLimitW",
    "essResultPowerPlanIdentifier", "essCurrentPowerPlanIdentifier", "interval", "min_period",
]
# Removed or replaced params (OPD R5): present in the config = configuration error naming the replacement.
REMOVED = {
    "essMinSafeLim": "removed (not used by the model); delete it",
    "ess_max_P_dp_id": "replaced by ess_max_P_charge_dp_id and ess_max_P_discharge_dp_id",
    "essPowerLimitW": "replaced by ess_max_P_charge_dp_id and ess_max_P_discharge_dp_id",
    "ess_min_soc": "removed (SFU-A1): the SoC limits are embedded in ess_max_E_dp_id (usable capacity) "
                   "and the energy inputs (usable energy); delete it",
    "ess_max_soc": "removed (SFU-A1): the SoC limits are embedded in ess_max_E_dp_id (usable capacity) "
                   "and the energy inputs (usable energy); delete it",
}
# OPD operational params: a number (constant) or a non-empty string (datapoint identifier, latest value per run).
OPERATIONAL = [
    "pccImportLimitW", "pccExportLimitW",
    "ess_max_P_charge_dp_id", "ess_max_P_discharge_dp_id", "ess_max_E_dp_id",
]


class ConfigError(Exception):
    pass


class InputError(Exception):
    pass


def load_params(raw):
    """Merge defaults into params and validate (A5-IMP R6, R14). Raises ConfigError."""
    if not isinstance(raw, dict) or not isinstance(raw.get("params"), dict):
        raise ConfigError("config has no 'params' section")
    stale = [f"{k}: {why}" for k, why in REMOVED.items() if k in raw["params"]]
    if stale:
        raise ConfigError("removed or replaced params in the config: " + "; ".join(stale))
    params = dict(DEFAULTS)
    params.update(raw["params"])
    missing = [k for k in REQUIRED if params.get(k) in (None, "")]
    if missing:
        raise ConfigError(f"missing params: {', '.join(missing)}")
    checks = [
        (0 < float(params["essChargeEfficiency"]) <= 1, "essChargeEfficiency must be in (0, 1]"),
        (0 < float(params["essDischargeEfficiency"]) <= 1, "essDischargeEfficiency must be in (0, 1]"),
        (float(params["gridTariffEurPerKWh"]) >= 0, "gridTariffEurPerKWh must be >= 0"),
        (float(params["essDegradationCostEurPerKWh"]) >= 0, "essDegradationCostEurPerKWh must be >= 0"),
        (float(params["pccLimitPenaltyEurPerKWh"]) >= 0, "pccLimitPenaltyEurPerKWh must be >= 0"),
        (float(params["endEnergyPenaltyEurPerKWh"]) >= 0, "endEnergyPenaltyEurPerKWh must be >= 0"),
        (float(params["essRampPenaltyEurPerKw"]) >= 0, "essRampPenaltyEurPerKw must be >= 0"),
        (float(params["solverTimeLimitS"]) > 0, "solverTimeLimitS must be > 0"),
        (float(params["maxInputAgeS"]) > 0, "maxInputAgeS must be > 0"),
        (int(params["interval"]) > 0, "interval must be > 0"),
        (int(params["min_period"]) >= 0, "min_period must be >= 0"),
        (params["writeDebugFile"] in ("on-failure", "always", "never"),
         "writeDebugFile must be on-failure, always or never"),
    ]
    for k in OPERATIONAL:
        v = params[k]
        if isinstance(v, bool) or not (isinstance(v, (int, float)) or (isinstance(v, str) and v.strip())):
            raise ConfigError(f"{k} must be a number or a datapoint identifier")
    errors = [msg for ok, msg in checks if not ok]
    if errors:
        raise ConfigError("; ".join(errors))
    return params


def read_value(identifier, param, now=None, max_age_s=None):
    """Last value of a datapoint, with clear errors (A5-IMP R7). Raises InputError."""
    dp = query_utils.get_datapoint(identifier)
    if dp is None:
        raise InputError(f"reading datapoint '{identifier}' ({param}) failed")
    if not dp:
        raise InputError(f"datapoint '{identifier}' ({param}) does not exist")
    val = dp[0].get("lastReadingValue")
    if val is None:
        raise InputError(f"datapoint '{identifier}' ({param}) has no value")
    if max_age_s is not None:
        last_time = dp[0].get("lastReadingTime")
        if not last_time:
            raise InputError(f"datapoint '{identifier}' ({param}) has no reading time")
        age = (now - Util.parse_time(last_time)).total_seconds()
        if age > max_age_s:
            raise InputError(f"datapoint '{identifier}' ({param}) is {int(age)} s old (max {int(max_age_s)} s)")
    return float(val)


def value_or_datapoint(params, name):
    """Operational parameter (OPD R1): a number is a constant; a string is a datapoint whose latest value is read
    (no staleness check: operator setpoint). Returns (value, source) with source 'const' or 'dp <id>'."""
    v = params[name]
    if isinstance(v, str):
        return read_value(v.strip(), name), f"dp {v.strip()}"
    return float(v), "const"


def clamp_energy(u_kwh, capacity_kwh, name):
    """SFU-A1 R3': an energy input (usable energy, kWh) is used as clamp(u, 0, capacity); WARNING if it clamps."""
    clamped = min(max(u_kwh, 0.0), capacity_kwh)
    if clamped != u_kwh:
        logger.warning(f"{name}: energy {u_kwh:.3f} kWh is outside 0..{capacity_kwh:.3f} kWh; "
                       f"clamped to {clamped:.3f} kWh")
    return clamped


def validate_operational(vals, srcs):
    """OPD R2 on the resolved values (W, Wh). A violation is an input error if a datapoint is involved in it,
    otherwise a configuration error."""
    rules = [
        (["ess_max_P_charge_dp_id"], vals["ess_max_P_charge_dp_id"] > 0, "ess_max_P_charge_dp_id must be > 0"),
        (["ess_max_P_discharge_dp_id"], vals["ess_max_P_discharge_dp_id"] > 0, "ess_max_P_discharge_dp_id must be > 0"),
        (["ess_max_E_dp_id"], vals["ess_max_E_dp_id"] > 0, "ess_max_E_dp_id must be > 0"),
        (["pccExportLimitW", "pccImportLimitW"], vals["pccExportLimitW"] <= vals["pccImportLimitW"],
         "need pccExportLimitW <= pccImportLimitW"),
    ]
    for names, ok, msg in rules:
        if not ok:
            detail = ", ".join(f"{n}={vals[n]} ({srcs[n]})" for n in names)
            if any(srcs[n] != "const" for n in names):
                raise InputError(f"{msg}: {detail}")
            raise ConfigError(f"{msg}: {detail}")


def read_forecast(identifier, param):
    readings = query_utils.get_last_prognosis_readings(identifier)
    if readings is None:
        raise InputError(f"reading the forecast of '{identifier}' ({param}) failed")
    return [{"time": r["time"], "value": r["value"]} for r in readings if r.get("value") is not None]


def build_series(price, load, pv, price_initial, start, interval_s, min_period_s):
    """Common time grid from start to the end of the shortest forecast (A5-IMP R8).
    Returns (times, price_eur_mwh, load_kw, pv_kw) or None if the horizon is too short / a forecast is unusable."""
    if not price or not load or not pv:
        logger.warning(f"forecast missing: price={len(price)}, load={len(load)}, pv={len(pv)} values")
        return None
    end = Util.parse_time(Util.find_common_time_range([price, load, pv])["end"])
    if (end - start).total_seconds() < min_period_s:
        logger.warning(f"common forecast horizon {start.isoformat()} .. {end.isoformat()} is shorter than "
                       f"min_period {min_period_s} s")
        return None
    try:
        price_s = Util.generate_result_series(price, start, end, interval_s, price_initial)
        load_s = Util.extract_prognosis_values(load, "consumption", start, end, interval_s)
        pv_s = Util.extract_prognosis_values(pv, "production", start, end, interval_s)
    except (Util.TaskFailException, ValueError) as e:
        logger.warning(f"forecast cannot cover the planning window: {e}")
        return None
    n = min(len(price_s), len(load_s), len(pv_s))
    times = [start + timedelta(seconds=k * interval_s) for k in range(n)]
    return (times,
            [r["value"] for r in price_s[:n]],
            [r["value"] / 1000.0 for r in load_s[:n]],
            [r["value"] / 1000.0 for r in pv_s[:n]])


def iso(t):
    return t.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def post_plan(result_dp_id, start, times, values_w):
    readings = [{"time": iso(t), "value": float(v)} for t, v in zip(times, values_w)]
    return query_utils.post_datapoint_prognosis(result_dp_id, iso(start), readings)


def run_fallback(params, start, result_dp_id, reason):
    """Re-post the remaining part of the previous plan (A5-IMP R11). Returns the exit code."""
    previous = query_utils.get_last_prognosis_readings(params["essCurrentPowerPlanIdentifier"])
    remaining = [r for r in (previous or [])
                 if r.get("value") is not None and Util.parse_time(r["time"]) >= start]
    if not remaining:
        logger.error(f"{reason}; no previous plan to fall back on - nothing posted.")
        return 1
    readings = [{"time": r["time"], "value": float(r["value"])} for r in remaining]
    query_utils.post_datapoint_prognosis(result_dp_id, iso(start), readings)
    logger.warning(f"{reason}; posted the fallback plan ({len(readings)} values from the previous plan).")
    return 0


def run(config_path, now=None):
    with open(config_path, "r") as f:
        raw = yaml.safe_load(f)
    app_name = raw.get("appModule", "a5") if isinstance(raw, dict) else "a5"
    loki_url = (raw.get("params") or {}).get("lokiUrl", DEFAULTS["lokiUrl"]) if isinstance(raw, dict) else None
    setup_logger(app_name="A5Runner", log_file="query.log", loki_url=loki_url, loki_tags={"app_name": app_name})
    logger.info(f"{app_name} start.")

    try:
        params = load_params(raw)
    except (ConfigError, ValueError, TypeError) as e:
        logger.error(f"configuration error: {e}")
        return 1

    query_utils.init(params["apiEndpoint"], {})
    jwt_token = query_utils.get_token(params["clientId"], params["token"])
    if not jwt_token:
        logger.error(f"{app_name}: could not obtain an API token from {params['apiEndpoint']}/auth/token "
                     f"for clientId '{params['clientId']}' (check the credential in the app config). Stopping.")
        return 1
    query_utils.add_header("Authorization", f"Bearer {jwt_token}")

    now = now or datetime.now(timezone.utc)
    interval_s = int(params["interval"])
    start = Util.align_start(now, interval_s)

    try:
        result_dp = query_utils.get_datapoint(params["essResultPowerPlanIdentifier"])
        if not result_dp:
            raise InputError(f"result datapoint '{params['essResultPowerPlanIdentifier']}' does not exist")
        result_dp_id = result_dp[0]["id"]
        vals, srcs = {}, {}
        for name in OPERATIONAL:
            vals[name], srcs[name] = value_or_datapoint(params, name)
        validate_operational(vals, srcs)
        p_charge_kw = vals["ess_max_P_charge_dp_id"] / 1000.0
        p_discharge_kw = vals["ess_max_P_discharge_dp_id"] / 1000.0
        capacity_kwh = vals["ess_max_E_dp_id"] / 1000.0
        u0_kwh = read_value(params["ess_charge_dp_id"], "ess_charge_dp_id",
                            now=now, max_age_s=float(params["maxInputAgeS"])) / 1000.0
        e0_kwh = clamp_energy(u0_kwh, capacity_kwh, "ess_charge_dp_id")
        end_id = params.get("essEffectiveEndCharge")
        if end_id:
            u_end_kwh = read_value(end_id, "essEffectiveEndCharge") / 1000.0
            e_end_kwh = clamp_energy(u_end_kwh, capacity_kwh, "essEffectiveEndCharge")
        else:
            u_end_kwh, e_end_kwh = u0_kwh, e0_kwh
        price_dp = query_utils.get_datapoint(params["npPriceIdentifier"])
        price_initial = price_dp[0].get("lastReadingValue") if price_dp else None
        price = read_forecast(params["npPriceIdentifier"], "npPriceIdentifier")
        load = read_forecast(params["consumptionPrognosisIdentifier"], "consumptionPrognosisIdentifier")
        pv = read_forecast(params["productionPrognosisIdentifier"], "productionPrognosisIdentifier")
    except InputError as e:
        logger.error(f"input error: {e}")
        return 1
    except ConfigError as e:
        logger.error(f"configuration error: {e}")
        return 1

    if price_initial is None and price:
        price_initial = sorted(price, key=lambda r: Util.parse_time(r["time"]))[0]["value"]
    logger.info("inputs: " + ", ".join(f"{n}={vals[n]:g} ({srcs[n]})" for n in OPERATIONAL))
    start_txt = f"{e0_kwh:.3f}" if e0_kwh == u0_kwh else f"{u0_kwh:.3f} (raw) -> {e0_kwh:.3f} (used)"
    end_txt = f"{e_end_kwh:.3f}" if e_end_kwh == u_end_kwh else f"{u_end_kwh:.3f} (raw) -> {e_end_kwh:.3f} (used)"
    logger.info(f"inputs: capacity={capacity_kwh:g} kWh (usable), start energy={start_txt} kWh, "
                f"end target={end_txt} kWh, "
                f"Pch={p_charge_kw:g} kW, Pdis={p_discharge_kw:g} kW, "
                f"PCC {vals['pccExportLimitW'] / 1000.0:g} .. {vals['pccImportLimitW'] / 1000.0:g} kW, "
                f"forecast values price/load/pv={len(price)}/{len(load)}/{len(pv)}, start={iso(start)}")

    series = build_series(price, load, pv, price_initial, start, interval_s, int(params["min_period"]))
    if series is None:
        return run_fallback(params, start, result_dp_id, "not enough forecast data")
    times, price_s, load_s, pv_s = series

    inp = a5model.PlanInputs(
        interval_s=interval_s, load_kw=load_s, pv_kw=pv_s, price_eur_mwh=price_s,
        p_charge_kw=p_charge_kw, p_discharge_kw=p_discharge_kw,
        capacity_kwh=capacity_kwh, e0_kwh=e0_kwh, e_end_kwh=e_end_kwh,
        import_limit_kw=vals["pccImportLimitW"] / 1000.0,
        pcc_min_kw=vals["pccExportLimitW"] / 1000.0,
        eta_charge=float(params["essChargeEfficiency"]), eta_discharge=float(params["essDischargeEfficiency"]),
        grid_tariff_eur_kwh=float(params["gridTariffEurPerKWh"]),
        degradation_eur_kwh=float(params["essDegradationCostEurPerKWh"]),
        pcc_penalty_eur_kwh=float(params["pccLimitPenaltyEurPerKWh"]),
        end_penalty_eur_kwh=float(params["endEnergyPenaltyEurPerKWh"]),
        ramp_penalty_eur_kw=float(params["essRampPenaltyEurPerKw"]),
    )
    m = a5model.build_model(inp)
    result = a5model.solve(m, time_limit_s=float(params["solverTimeLimitS"]))
    if params["writeDebugFile"] == "always" or (params["writeDebugFile"] == "on-failure" and not result.ok):
        debug_model(m)
    if not result.ok:
        return run_fallback(params, start, result_dp_id, f"solver result {result.status}")

    logger.info(f"solved ({result.status}): {len(times)} steps {iso(times[0])} .. {iso(times[-1])}, "
                f"cost {result.cost_eur:.2f} EUR (ramp {result.ramp_cost_eur:.4f}), end energy {result.energy_kwh[-1]:.1f} kWh")
    if result.import_overrun_kwh > 1e-6 or result.lower_overrun_kwh > 1e-6:
        logger.warning(f"plan exceeds the PCC limits: import {result.import_overrun_kwh:.2f} kWh, "
                       f"below the lower limit {result.lower_overrun_kwh:.2f} kWh over the horizon")
    if abs(result.end_deviation_kwh) > 1e-6:
        logger.warning(f"end energy misses its target by {result.end_deviation_kwh:.2f} kWh")
    post_plan(result_dp_id, start, times, [v * 1000.0 for v in result.ess_kw])
    logger.info(f"{app_name} finished: plan posted to '{params['essResultPowerPlanIdentifier']}'.")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run A5 with config file")
    parser.add_argument("-c", "--config", required=False, help="Path to config YAML file", default="/app/config.yaml")
    args = parser.parse_args(argv)
    try:
        return run(args.config)
    except Exception:  # last resort: a clear message instead of a bare traceback
        logger.exception("A5 failed with an unexpected error")
        return 1


if __name__ == "__main__":
    sys.exit(main())
