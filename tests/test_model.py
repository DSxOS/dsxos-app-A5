"""A5-IMP AC1(d)-(h): optimisation model (needs glpsol)."""
import pytest

import model as a5model


def inputs(**over):
    base = dict(interval_s=900, load_kw=[10.0] * 8, pv_kw=[0.0] * 8, price_eur_mwh=[10.0] * 4 + [300.0] * 4,
                p_max_kw=20.0, capacity_kwh=100.0, e0_kwh=50.0, e_end_kwh=50.0, soc_min_pct=15, soc_max_pct=80,
                import_limit_kw=1000.0, export_limit_kw=0.0, eta_charge=0.95, eta_discharge=0.95,
                grid_tariff_eur_kwh=0.0, degradation_eur_kwh=0.0, pcc_penalty_eur_kwh=10.0, end_penalty_eur_kwh=1.0)
    base.update(over)
    return a5model.PlanInputs(**base)


def solve(inp):
    r = a5model.solve(a5model.build_model(inp), time_limit_s=60)
    assert r.ok, r.status
    return r


def test_hand_checked_optimum_charges_cheap_discharges_expensive():
    inp = inputs()
    r = solve(inp)
    dt = 0.25
    charged = sum(max(p, 0) for p in r.ess_kw) * dt
    discharged = sum(max(-p, 0) for p in r.ess_kw) * dt
    # All 10 kWh of expensive load (4 steps x 10 kW x 0.25 h) come from the battery (no export allowed);
    # ending at E0 requires charging 10 / (0.95 * 0.95) kWh in the cheap block.
    assert discharged == pytest.approx(10.0, abs=1e-4)
    assert charged == pytest.approx(10.0 / 0.9025, abs=1e-4)
    assert all(p >= -1e-6 for p in r.ess_kw[:4]) and all(p <= 1e-6 for p in r.ess_kw[4:])
    assert all(15.0 - 1e-6 <= e <= 80.0 + 1e-6 for e in r.energy_kwh[1:])
    assert r.energy_kwh[-1] == pytest.approx(50.0, abs=1e-4)
    assert r.import_overrun_kwh == pytest.approx(0) and r.export_overrun_kwh == pytest.approx(0)


def test_efficiency_losses_over_a_cycle():
    r = solve(inputs())
    charged = sum(max(p, 0) for p in r.ess_kw)
    discharged = sum(max(-p, 0) for p in r.ess_kw)
    assert discharged / charged == pytest.approx(0.95 * 0.95, rel=1e-6)


def test_soc_window_is_enforced():
    # Very cheap then very expensive with a big battery: the plan wants to use the full window, not beyond it.
    inp = inputs(price_eur_mwh=[1.0] * 4 + [900.0] * 4, load_kw=[100.0] * 8, p_max_kw=200.0,
                 import_limit_kw=10000.0, e0_kwh=50.0, e_end_kwh=50.0)
    r = solve(inp)
    assert min(r.energy_kwh[1:]) >= 15.0 - 1e-6 and max(r.energy_kwh[1:]) <= 80.0 + 1e-6
    assert max(r.energy_kwh) == pytest.approx(80.0, abs=1e-3)  # charges up to the window's top


def test_start_outside_window_is_still_solvable():
    r = solve(inputs(e0_kwh=10.0, e_end_kwh=10.0))  # below Emin = 15
    assert min(r.energy_kwh) >= 10.0 - 1e-6


def test_soft_pcc_limit_reports_overrun_instead_of_failing():
    # 50 kW load, only 10 kW import allowed, ESS of 5 kW: the limit cannot hold; the plan still comes out.
    inp = inputs(load_kw=[50.0] * 4, pv_kw=[0.0] * 4, price_eur_mwh=[100.0] * 4,
                 p_max_kw=5.0, capacity_kwh=10.0, e0_kwh=5.0, e_end_kwh=5.0, import_limit_kw=10.0)
    r = solve(inp)
    assert r.import_overrun_kwh > 1.0


def test_end_energy_option_is_honoured():
    inp = inputs(interval_s=3600, load_kw=[0.0] * 4, pv_kw=[0.0] * 4, price_eur_mwh=[50.0] * 4,
                 e0_kwh=40.0, e_end_kwh=60.0, grid_tariff_eur_kwh=0.05, degradation_eur_kwh=0.05)
    r = solve(inp)
    assert r.energy_kwh[-1] == pytest.approx(60.0, abs=1e-4)
    assert sum(max(p, 0) for p in r.ess_kw) == pytest.approx(20.0 / 0.95, abs=1e-4)


def test_import_export_binaries_only_with_negative_prices():
    assert not hasattr(a5model.build_model(inputs()), "zi")
    assert hasattr(a5model.build_model(inputs(price_eur_mwh=[-5.0] + [10.0] * 7)), "zi")


def test_negative_price_case_solves():
    r = solve(inputs(price_eur_mwh=[-50.0] * 4 + [300.0] * 4))
    assert r.ok
