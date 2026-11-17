"""A5-IMP AC1(c) input errors and AC1(i) fallback / outcomes, OPD AC1(a,b,c,f): end to end through main.run with a fake data server."""
from datetime import datetime, timedelta, timezone

import pytest
import yaml

import main
import model as a5model
import query_utils

NOW = datetime(2026, 11, 14, 10, 7, 30, tzinfo=timezone.utc)
START = datetime(2026, 11, 14, 10, 0, 0, tzinfo=timezone.utc)   # aligned to 900 s


def iso(t):
    return t.isoformat().replace("+00:00", "Z")


def series(hours, value, step_min=15, begin=START - timedelta(minutes=30)):
    return [{"time": iso(begin + timedelta(minutes=step_min * i)), "value": value(i)}
            for i in range(int(hours * 60 / step_min) + 1)]


class FakeServer:
    def __init__(self, hours=10):
        self.datapoints = {
            "ess_p_a5_test": {"id": 530},
            "pmax": {"lastReadingValue": 20000.0},
            "cap": {"lastReadingValue": 100000.0},
            "charge": {"lastReadingValue": 35000.0, "lastReadingTime": iso(NOW - timedelta(seconds=30))},
            "price": {"lastReadingValue": 80.0},
        }
        self.forecasts = {
            "price": series(hours, lambda i: 10.0 if i < 20 else 300.0),
            "cons": series(hours, lambda i: 10000.0, step_min=1),
            "prod": series(hours, lambda i: 0.0, step_min=1),
            "ess_p_a5_test": [],
        }
        self.posted = []

    def install(self, monkeypatch):
        monkeypatch.setattr(query_utils, "get_token", lambda cid, secret: "T")
        monkeypatch.setattr(query_utils, "get_datapoint",
                            lambda ident: [self.datapoints[ident]] if ident in self.datapoints else [])
        monkeypatch.setattr(query_utils, "get_last_prognosis_readings",
                            lambda ident, page_size=10000: [dict(r) for r in self.forecasts.get(ident, [])])
        monkeypatch.setattr(query_utils, "post_datapoint_prognosis",
                            lambda dp_id, t, readings: self.posted.append((dp_id, t, readings)) or {"id": 1})


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    params = {
        "apiEndpoint": "http://x/api", "clientId": "c", "token": "s", "lokiUrl": "",
        "npPriceIdentifier": "price", "consumptionPrognosisIdentifier": "cons", "productionPrognosisIdentifier": "prod",
        "ess_max_P_charge_dp_id": "pmax", "ess_max_P_discharge_dp_id": "pmax",
        "ess_max_E_dp_id": "cap", "ess_charge_dp_id": "charge",
        "essEffectiveEndCharge": "charge",
        "pccImportLimitW": 170000, "pccExportLimitW": 0,
        "essResultPowerPlanIdentifier": "ess_p_a5_test", "essCurrentPowerPlanIdentifier": "ess_p_a5_test",
        "interval": 900, "min_period": 21600, "solverTimeLimitS": 60,
    }
    path = tmp_path / "config.yaml"

    def write(**over):
        p = dict(params, **over)
        path.write_text(yaml.safe_dump({"appModule": "a5", "params": p}))
        return str(path)
    return write


def test_plan_is_posted_on_an_aligned_grid(cfg, monkeypatch):
    srv = FakeServer()
    srv.install(monkeypatch)
    assert main.run(cfg(), now=NOW) == 0
    dp_id, t, readings = srv.posted[0]
    assert dp_id == 530 and t == "2026-11-14T10:00:00Z"
    assert readings[0]["time"] == "2026-11-14T10:00:00Z" and readings[1]["time"] == "2026-11-14T10:15:00Z"
    assert len(readings) > 30   # ~9.5 h of 15-min steps


@pytest.mark.parametrize("change,needle", [
    (lambda s: s.datapoints.pop("pmax"), "does not exist"),
    (lambda s: s.datapoints["cap"].update(lastReadingValue=None), "has no value"),
    (lambda s: s.datapoints["charge"].update(lastReadingTime=iso(NOW - timedelta(hours=2))), "s old"),
])
def test_input_errors_stop_without_posting(cfg, monkeypatch, caplog, change, needle):
    srv = FakeServer()
    change(srv)
    srv.install(monkeypatch)
    assert main.run(cfg(), now=NOW) == 1
    assert srv.posted == []
    assert needle in caplog.text


def test_configuration_error_stops(cfg, monkeypatch, caplog):
    FakeServer().install(monkeypatch)
    assert main.run(cfg(essChargeEfficiency=1.5), now=NOW) == 1
    assert "essChargeEfficiency" in caplog.text


def previous_plan():
    return [{"time": iso(START + timedelta(minutes=15 * i - 30)), "value": 1000.0 * i} for i in range(10)]


def test_not_enough_forecast_uses_the_fallback_plan(cfg, monkeypatch, caplog):
    srv = FakeServer(hours=2)          # common horizon < min_period (6 h)
    srv.forecasts["ess_p_a5_test"] = previous_plan()
    srv.install(monkeypatch)
    assert main.run(cfg(), now=NOW) == 0
    _, t, readings = srv.posted[0]
    assert t == "2026-11-14T10:00:00Z"
    assert readings[0]["time"] == "2026-11-14T10:00:00Z" and len(readings) == 8   # only times >= start
    assert "fallback plan" in caplog.text


def test_failed_solve_uses_the_fallback_plan(cfg, monkeypatch, caplog):
    srv = FakeServer()
    srv.forecasts["ess_p_a5_test"] = previous_plan()
    srv.install(monkeypatch)
    monkeypatch.setattr(main.a5model, "solve", lambda m, time_limit_s=300: a5model.PlanResult(ok=False, status="error/infeasible"))
    assert main.run(cfg(writeDebugFile="never"), now=NOW) == 0
    assert len(srv.posted) == 1 and "solver result error/infeasible" in caplog.text


def test_no_fallback_available_exits_1(cfg, monkeypatch, caplog):
    srv = FakeServer(hours=2)
    srv.install(monkeypatch)
    assert main.run(cfg(), now=NOW) == 1
    assert srv.posted == [] and "no previous plan" in caplog.text


# --- OPD (docs/requirements-opd-operational-datapoints.md) AC1 a, b, c, f ---------------------------------------------

BASE = {"pccImportLimitW": 170000, "pccExportLimitW": 0,
        "ess_max_P_charge_dp_id": 20000, "ess_max_P_discharge_dp_id": 20000, "ess_max_E_dp_id": 100000}


@pytest.mark.parametrize("name", sorted(BASE))
def test_each_operational_param_gives_the_same_plan_as_number_and_datapoint(cfg, monkeypatch, caplog, name):
    # same value, once as a number and once as a datapoint; the other params as numbers
    const_srv = FakeServer()
    const_srv.install(monkeypatch)
    assert main.run(cfg(**BASE), now=NOW) == 0
    assert f"{name}={BASE[name]:g} (const)" in caplog.text
    dp_srv = FakeServer()
    dp_srv.datapoints["opdp"] = {"lastReadingValue": float(BASE[name])}
    dp_srv.install(monkeypatch)
    assert main.run(cfg(**dict(BASE, **{name: "opdp"})), now=NOW) == 0
    assert f"{name}={BASE[name]:g} (dp opdp)" in caplog.text
    assert const_srv.posted == dp_srv.posted and len(dp_srv.posted) == 1


def test_the_datapoint_value_is_the_limit(cfg, monkeypatch):
    srv = FakeServer()
    srv.datapoints["opdp"] = {"lastReadingValue": 5000.0}
    srv.install(monkeypatch)
    assert main.run(cfg(**dict(BASE, ess_max_P_charge_dp_id="opdp")), now=NOW) == 0
    assert max(r["value"] for r in srv.posted[0][2]) <= 5000.0 + 1e-6


@pytest.mark.parametrize("name", sorted(BASE))
@pytest.mark.parametrize("fault", ["missing", "no-value"])
def test_missing_or_empty_operational_datapoint_is_an_input_error(cfg, monkeypatch, caplog, name, fault):
    srv = FakeServer()
    if fault == "no-value":
        srv.datapoints["opdp"] = {"lastReadingValue": None}
    srv.install(monkeypatch)
    assert main.run(cfg(**dict(BASE, **{name: "opdp"})), now=NOW) == 1
    assert srv.posted == []
    assert "input error" in caplog.text and name in caplog.text and "'opdp'" in caplog.text


R2_CASES = [
    ({"ess_max_P_charge_dp_id": 0}, "ess_max_P_charge_dp_id"),
    ({"ess_max_P_discharge_dp_id": -5}, "ess_max_P_discharge_dp_id"),
    ({"ess_max_E_dp_id": 0}, "ess_max_E_dp_id"),
    ({"pccExportLimitW": 200000}, "pccExportLimitW <= pccImportLimitW"),
]


@pytest.mark.parametrize("over,needle", R2_CASES)
def test_r2_validation_of_numbers_is_a_configuration_error(cfg, monkeypatch, caplog, over, needle):
    srv = FakeServer()
    srv.install(monkeypatch)
    assert main.run(cfg(**dict(BASE, **over)), now=NOW) == 1
    assert srv.posted == []
    assert "configuration error" in caplog.text and needle in caplog.text


@pytest.mark.parametrize("over,needle", R2_CASES)
def test_r2_validation_of_datapoint_values_is_an_input_error(cfg, monkeypatch, caplog, over, needle):
    srv = FakeServer()
    for i, (k, v) in enumerate(over.items()):
        srv.datapoints[f"dp{i}"] = {"lastReadingValue": float(v)}
    srv.install(monkeypatch)
    assert main.run(cfg(**dict(BASE, **{k: f"dp{i}" for i, k in enumerate(over)})), now=NOW) == 1
    assert srv.posted == []
    assert "input error" in caplog.text and needle in caplog.text


def test_negative_export_limit_and_positive_lower_limit_are_valid(cfg, monkeypatch):
    for lower in (-1000000, 0, 5000):
        srv = FakeServer()
        srv.install(monkeypatch)
        assert main.run(cfg(**dict(BASE, pccExportLimitW=lower)), now=NOW) == 0
        assert len(srv.posted) == 1


@pytest.mark.parametrize("old,new", [
    ("essMinSafeLim", "essMinSafeLim"),
    ("ess_max_P_dp_id", "ess_max_P_charge_dp_id"),
    ("ess_max_P_dp_id", "ess_max_P_discharge_dp_id"),
    ("essPowerLimitW", "ess_max_P_charge_dp_id"),
    ("essPowerLimitW", "ess_max_P_discharge_dp_id"),
])
def test_removed_or_replaced_params_are_configuration_errors(cfg, monkeypatch, caplog, old, new):
    srv = FakeServer()
    srv.install(monkeypatch)
    assert main.run(cfg(**{old: "pmax"}), now=NOW) == 1
    assert srv.posted == []
    assert "configuration error" in caplog.text and old in caplog.text and new in caplog.text


def test_missing_new_power_params_are_configuration_errors(cfg, monkeypatch, caplog):
    FakeServer().install(monkeypatch)
    path = cfg()
    raw = yaml.safe_load(open(path))
    del raw["params"]["ess_max_P_discharge_dp_id"]
    open(path, "w").write(yaml.safe_dump(raw))
    assert main.run(path, now=NOW) == 1
    assert "missing params: ess_max_P_discharge_dp_id" in caplog.text


def test_asymmetric_power_limits_end_to_end(cfg, monkeypatch):
    srv = FakeServer()
    srv.datapoints["pch"] = {"lastReadingValue": 50000.0}
    srv.datapoints["pdis"] = {"lastReadingValue": 30000.0}
    srv.install(monkeypatch)
    assert main.run(cfg(ess_max_P_charge_dp_id="pch", ess_max_P_discharge_dp_id="pdis", ess_max_E_dp_id=1000000), now=NOW) == 0
    values = [r["value"] for r in srv.posted[0][2]]
    assert max(values) <= 50000.0 + 1e-6 and min(values) >= -30000.0 - 1e-6


def test_positive_lower_pcc_limit_end_to_end(cfg, monkeypatch, caplog):
    # load 10 kW; price makes the plan want to discharge; a 5 kW minimum import caps the discharge at 5 kW
    srv = FakeServer()
    srv.datapoints["charge"]["lastReadingValue"] = 65000.0    # enough energy to discharge all day
    srv.datapoints["endlow"] = {"lastReadingValue": 0.0}    # may end empty, so discharging pays
    srv.forecasts["price"] = series(10, lambda i: 300.0)
    srv.install(monkeypatch)
    assert main.run(cfg(pccExportLimitW=5000, essEffectiveEndCharge="endlow"), now=NOW) == 0
    values = [r["value"] for r in srv.posted[0][2]]
    assert min(values) >= -5000.0 - 1e-6 and min(values) == pytest.approx(-5000.0, abs=1.0)
    assert "below the lower limit" not in caplog.text


def test_negative_ramp_penalty_is_a_configuration_error(cfg, monkeypatch, caplog):
    FakeServer().install(monkeypatch)
    assert main.run(cfg(essRampPenaltyEurPerKw=-0.1), now=NOW) == 1
    assert "essRampPenaltyEurPerKw" in caplog.text


def test_ramp_penalty_defaults_to_0_0001(cfg, monkeypatch):
    srv = FakeServer()
    srv.install(monkeypatch)
    seen = []
    real_build = a5model.build_model
    monkeypatch.setattr(main.a5model, "build_model", lambda inp: seen.append(inp.ramp_penalty_eur_kw) or real_build(inp))
    assert main.run(cfg(), now=NOW) == 0
    assert seen == [0.0001]


# --- SFU-A1 (docs/requirements-sfu-soc-fraction-usable-energy.md, section 7) AC1' a-d -------------------------------

@pytest.mark.parametrize("name", ["ess_min_soc", "ess_max_soc"])
def test_sfu_a1_ac1a_soc_params_are_stale_parameters(cfg, monkeypatch, caplog, name):
    srv = FakeServer()
    srv.install(monkeypatch)
    assert main.run(cfg(**{name: 0.5}), now=NOW) == 1
    assert srv.posted == []
    assert "removed or replaced params" in caplog.text and f"{name}: removed (SFU-A1)" in caplog.text


def test_sfu_a1_ac1a_config_without_soc_params_passes(cfg, monkeypatch):
    srv = FakeServer()
    srv.install(monkeypatch)
    assert main.run(cfg(), now=NOW) == 0
    assert len(srv.posted) == 1


def test_sfu_a1_ac1b_model_bounds_are_zero_and_capacity():
    inp = a5model.PlanInputs(interval_s=900, load_kw=[1.0], pv_kw=[0.0], price_eur_mwh=[1.0], p_charge_kw=1.0,
                             p_discharge_kw=1.0, capacity_kwh=227.5, e0_kwh=100.0, e_end_kwh=100.0,
                             import_limit_kw=10.0, pcc_min_kw=0.0)
    assert a5model.energy_bounds(inp) == pytest.approx((0.0, 227.5))


@pytest.mark.parametrize("raw,used,warns", [(34.3, 34.3, False), (-5.0, 0.0, True), (300.0, 227.5, True)])
def test_sfu_a1_ac1c_clamp_energy(caplog, raw, used, warns):
    assert main.clamp_energy(raw, 227.5, "ess_charge_dp_id") == pytest.approx(used, abs=1e-9)
    assert ("clamped" in caplog.text) == warns
    if warns:
        assert any(r.levelname == "WARNING" and f"{raw:.3f}" in r.getMessage() and f"{used:.3f}" in r.getMessage()
                   for r in caplog.records)


def run_sfu(cfg, monkeypatch, charge_wh, end_wh=None):
    srv = FakeServer()
    srv.datapoints["cap"] = {"lastReadingValue": 227500.0}
    srv.datapoints["charge"]["lastReadingValue"] = charge_wh
    srv.datapoints["endc"] = {"lastReadingValue": end_wh}
    srv.install(monkeypatch)
    over = dict(ess_max_P_charge_dp_id=100000, ess_max_P_discharge_dp_id=100000, ess_max_E_dp_id="cap",
                pccImportLimitW=500000, pccExportLimitW=-500000)
    over["essEffectiveEndCharge"] = "endc" if end_wh is not None else None
    captured = {}
    real = a5model.build_model

    def spy(inp):
        captured["inp"] = inp
        return real(inp)
    monkeypatch.setattr(a5model, "build_model", spy)
    assert main.run(cfg(**over), now=NOW) == 0
    return srv, captured["inp"]


@pytest.mark.parametrize("charge_wh,start", [(34300.0, 34.3), (-5000.0, 0.0), (300000.0, 227.5)])
def test_sfu_a1_ac1c_start_energy_is_clamped_with_a_warning(cfg, monkeypatch, caplog, charge_wh, start):
    _, inp = run_sfu(cfg, monkeypatch, charge_wh)
    assert inp.e0_kwh == pytest.approx(start, abs=1e-9) and inp.capacity_kwh == pytest.approx(227.5)
    assert ("clamped" in caplog.text) == (charge_wh != 34300.0)
    # no end target: the default is the clamped start energy
    assert inp.e_end_kwh == inp.e0_kwh


@pytest.mark.parametrize("end_wh,end", [(100000.0, 100.0), (-5000.0, 0.0), (300000.0, 227.5)])
def test_sfu_a1_ac1c_end_target_is_clamped_like_the_start(cfg, monkeypatch, caplog, end_wh, end):
    _, inp = run_sfu(cfg, monkeypatch, 34300.0, end_wh)
    assert inp.e0_kwh == pytest.approx(34.3) and inp.e_end_kwh == pytest.approx(end, abs=1e-9)
    assert ("essEffectiveEndCharge" in caplog.text and "clamped" in caplog.text) == (end_wh != 100000.0)


def test_sfu_a1_r4_resolved_inputs_line_has_no_soc(cfg, monkeypatch, caplog):
    caplog.set_level("INFO")
    run_sfu(cfg, monkeypatch, 34300.0, 100000.0)
    line = next(r.getMessage() for r in caplog.records if "capacity=227.5 kWh" in r.getMessage())
    for part in ("capacity=227.5 kWh (usable)", "start energy=34.300 kWh", "end target=100.000 kWh",
                 "Pch=100 kW", "Pdis=100 kW", "PCC -500 .. 500 kW"):
        assert part in line
    assert "soc" not in line.lower()
    run_sfu(cfg, monkeypatch, 300000.0, -5000.0)
    line = [r.getMessage() for r in caplog.records if "capacity=227.5 kWh" in r.getMessage()][-1]
    assert "300.000 (raw) -> 227.500 (used)" in line and "-5.000 (raw) -> 0.000 (used)" in line


def test_sfu_a1_ac1d_full_solve_keeps_energy_within_zero_and_capacity(cfg, monkeypatch):
    srv, inp = run_sfu(cfg, monkeypatch, 34300.0, 100000.0)
    r = a5model.solve(a5model.build_model(inp), time_limit_s=60)
    assert r.ok and len(srv.posted) == 1
    assert all(-1e-6 <= e <= 227.5 + 1e-6 for e in r.energy_kwh)
    assert r.energy_kwh[0] == pytest.approx(34.3, abs=1e-6)
