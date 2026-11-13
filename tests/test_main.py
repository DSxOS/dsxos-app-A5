"""A5-IMP AC1(c) input errors and AC1(i) fallback / outcomes, end to end through main.run with a fake data server."""
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
            "charge": {"lastReadingValue": 50000.0, "lastReadingTime": iso(NOW - timedelta(seconds=30))},
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
        "ess_max_P_dp_id": "pmax", "ess_max_E_dp_id": "cap", "ess_charge_dp_id": "charge",
        "essEffectiveEndCharge": "charge", "essMinSafeLim": "whatever",
        "ess_min_soc": 15, "ess_max_soc": 80, "pccImportLimitW": 170000, "pccExportLimitW": 0,
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


def test_essMinSafeLim_is_accepted_and_ignored(cfg, monkeypatch, caplog):
    srv = FakeServer()
    srv.install(monkeypatch)
    assert main.run(cfg(), now=NOW) == 0
    assert "essMinSafeLim is ignored" in caplog.text
