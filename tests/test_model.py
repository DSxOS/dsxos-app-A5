"""A5-IMP AC1(d)-(h): optimisation model (needs glpsol)."""
import pytest

import model as a5model


def inputs(**over):
    base = dict(interval_s=900, load_kw=[10.0] * 8, pv_kw=[0.0] * 8, price_eur_mwh=[10.0] * 4 + [300.0] * 4,
                p_charge_kw=20.0, p_discharge_kw=20.0, capacity_kwh=100.0, e0_kwh=50.0, e_end_kwh=50.0, soc_min_pct=15, soc_max_pct=80,
                import_limit_kw=1000.0, pcc_min_kw=0.0, eta_charge=0.95, eta_discharge=0.95,
                grid_tariff_eur_kwh=0.0, degradation_eur_kwh=0.0, pcc_penalty_eur_kwh=10.0, end_penalty_eur_kwh=1.0)
    if "p_max_kw" in over:   # shorthand: equal charge and discharge limit
        over["p_charge_kw"] = over["p_discharge_kw"] = over.pop("p_max_kw")
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
    assert r.import_overrun_kwh == pytest.approx(0) and r.lower_overrun_kwh == pytest.approx(0)


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


# --- A5-AF anti-flicker (AC1 a, b) ---------------------------------------------------------------------------------

def flicker_inputs(ramp):
    """F2 shape: 60 s steps, one 30-step cheap slot between dearer slots, PCC import limit binding at full charge,
    the end target needs about half of the cheap slot at full power."""
    import math
    n = 90
    load = [90.0 + 3.0 * math.sin(1.7 * i) for i in range(n)]
    price = [50.0] * 30 + [10.0] * 30 + [50.0] * 30
    # max charge in the slot ~ 170 - 90 = 80 kW; 15 min at 80 kW, stored with eta 0.95 = 19 kWh
    return inputs(interval_s=60, load_kw=load, pv_kw=[0.0] * n, price_eur_mwh=price, p_max_kw=200.0,
                  capacity_kwh=100.0, e0_kwh=50.0, e_end_kwh=69.0, import_limit_kw=170.0,
                  grid_tariff_eur_kwh=0.05, degradation_eur_kwh=0.05,    # A5 defaults, as on NRG: no arbitrage
                  ramp_penalty_eur_kw=ramp)


def jumps(r, threshold_kw=1.0):
    return sum(1 for a, b in zip(r.ess_kw, r.ess_kw[1:]) if abs(b - a) > threshold_kw)


def test_fixture_reproduces_the_flicker_without_ramp_penalty():
    r = solve(flicker_inputs(0.0))
    assert abs(r.energy_kwh[-1] - 69.0) < 1e-3
    assert jumps(r) > 2, r.ess_kw


def test_ramp_penalty_gives_a_flat_plan():
    r = solve(flicker_inputs(0.0001))
    assert abs(r.energy_kwh[-1] - 69.0) < 1e-3
    assert jumps(r) <= 2, r.ess_kw
    assert all(abs(p) < 1e-6 for p in r.ess_kw[:30] + r.ess_kw[60:])    # charging only in the cheap slot
    assert r.ramp_cost_eur > 0


def test_ramp_penalty_has_small_economic_impact():
    off = solve(flicker_inputs(0.0))
    on = solve(flicker_inputs(0.0001))
    assert off.ramp_cost_eur == 0
    assert (on.cost_eur - on.ramp_cost_eur) - off.cost_eur <= 0.01


# --- OPD R3 separate power limits, R4 signed PCC window (AC1 d, e) --------------------------------------------------

def legacy_single_limit_solve(inp, p_max):
    """Reference: the pre-OPD model (one p_max for both directions, import/export limits as separate soft bounds,
    export limit = -pcc_min_kw for pcc_min_kw <= 0). Kept here only to prove that the new model is identical."""
    import pyomo.environ as pyo
    n = len(inp.load_kw)
    dt = inp.interval_s / 3600.0
    e_min, e_max = a5model.energy_bounds(inp)
    e_end = min(max(inp.e_end_kwh, e_min), e_max)
    m = pyo.ConcreteModel()
    m.T = pyo.RangeSet(0, n - 1)
    m.K = pyo.RangeSet(0, n)
    m.ch = pyo.Var(m.T, bounds=(0, p_max))
    m.dis = pyo.Var(m.T, bounds=(0, p_max))
    m.zc = pyo.Var(m.T, domain=pyo.Binary)
    m.ch_on = pyo.Constraint(m.T, rule=lambda m, t: m.ch[t] <= p_max * m.zc[t])
    m.dis_on = pyo.Constraint(m.T, rule=lambda m, t: m.dis[t] <= p_max * (1 - m.zc[t]))
    m.imp = pyo.Var(m.T, domain=pyo.NonNegativeReals)
    m.exp = pyo.Var(m.T, domain=pyo.NonNegativeReals)
    m.o_imp = pyo.Var(m.T, domain=pyo.NonNegativeReals)
    m.o_exp = pyo.Var(m.T, domain=pyo.NonNegativeReals)
    m.balance = pyo.Constraint(m.T, rule=lambda m, t:
                               m.imp[t] - m.exp[t] == inp.load_kw[t] + inp.pv_kw[t] + m.ch[t] - m.dis[t])
    m.imp_limit = pyo.Constraint(m.T, rule=lambda m, t: m.imp[t] <= inp.import_limit_kw + m.o_imp[t])
    m.exp_limit = pyo.Constraint(m.T, rule=lambda m, t: m.exp[t] <= -inp.pcc_min_kw + m.o_exp[t])
    if any(p < 0 for p in inp.price_eur_mwh):
        big_m = max(abs(l + v) for l, v in zip(inp.load_kw, inp.pv_kw)) + p_max + 1.0
        m.zi = pyo.Var(m.T, domain=pyo.Binary)
        m.imp_on = pyo.Constraint(m.T, rule=lambda m, t: m.imp[t] <= big_m * m.zi[t])
        m.exp_on = pyo.Constraint(m.T, rule=lambda m, t: m.exp[t] <= big_m * (1 - m.zi[t]))
    m.E = pyo.Var(m.K)
    m.E[0].fix(inp.e0_kwh)
    for k in range(1, n + 1):
        m.E[k].setlb(e_min)
        m.E[k].setub(e_max)
    m.energy = pyo.Constraint(m.T, rule=lambda m, t:
                              m.E[t + 1] == m.E[t] + (m.ch[t] * inp.eta_charge - m.dis[t] / inp.eta_discharge) * dt)
    m.dev_up = pyo.Var(domain=pyo.NonNegativeReals)
    m.dev_down = pyo.Var(domain=pyo.NonNegativeReals)
    m.end_target = pyo.Constraint(expr=m.E[n] - e_end == m.dev_up - m.dev_down)
    m.TR = pyo.Set(initialize=list(range(1, n)))
    m.ramp = pyo.Var(m.TR, domain=pyo.NonNegativeReals)
    m.ramp_up = pyo.Constraint(m.TR, rule=lambda m, t: m.ramp[t] >= (m.ch[t] - m.dis[t]) - (m.ch[t - 1] - m.dis[t - 1]))
    m.ramp_down = pyo.Constraint(m.TR, rule=lambda m, t: m.ramp[t] >= (m.ch[t - 1] - m.dis[t - 1]) - (m.ch[t] - m.dis[t]))
    m.cost = pyo.Objective(sense=pyo.minimize, expr=sum(
        dt * (m.imp[t] * (inp.price_eur_mwh[t] / 1000.0 + inp.grid_tariff_eur_kwh)
              - m.exp[t] * inp.price_eur_mwh[t] / 1000.0 + m.ch[t] * inp.degradation_eur_kwh
              + (m.o_imp[t] + m.o_exp[t]) * inp.pcc_penalty_eur_kwh) for t in m.T)
        + (m.dev_up + m.dev_down) * inp.end_penalty_eur_kwh + sum(m.ramp[t] for t in m.TR) * inp.ramp_penalty_eur_kw)
    res = pyo.SolverFactory("glpk").solve(m)
    assert str(res.solver.termination_condition) == "optimal"
    return ([pyo.value(m.ch[t]) - pyo.value(m.dis[t]) for t in m.T], pyo.value(m.cost),
            sum(pyo.value(m.o_imp[t]) for t in m.T) * dt, sum(pyo.value(m.o_exp[t]) for t in m.T) * dt)


EQUAL_LIMIT_CASES = {
    "arbitrage": dict(),
    "no-export-binding-import": dict(load_kw=[50.0] * 8, import_limit_kw=45.0, price_eur_mwh=[10.0] * 4 + [300.0] * 4),
    "export-allowed": dict(pcc_min_kw=-30.0, pv_kw=[-40.0] * 8, load_kw=[10.0] * 8),
    "negative-prices": dict(price_eur_mwh=[-50.0] * 4 + [300.0] * 4, pcc_min_kw=-15.0, pv_kw=[-25.0] * 8),
    "overrun": dict(load_kw=[50.0] * 4, pv_kw=[0.0] * 4, price_eur_mwh=[100.0] * 4, p_max_kw=5.0, capacity_kwh=10.0,
                    e0_kwh=5.0, e_end_kwh=5.0, import_limit_kw=10.0),
}


@pytest.mark.parametrize("name", sorted(EQUAL_LIMIT_CASES))
def test_equal_power_limits_equal_the_single_limit_model(name):
    inp = inputs(**EQUAL_LIMIT_CASES[name])
    assert inp.p_charge_kw == inp.p_discharge_kw
    ess, cost, o_imp, o_exp = legacy_single_limit_solve(inp, inp.p_charge_kw)
    r = solve(inp)
    assert r.cost_eur == pytest.approx(cost, abs=1e-6)
    assert r.ess_kw == pytest.approx(ess, abs=1e-4)
    assert r.import_overrun_kwh == pytest.approx(o_imp, abs=1e-6)
    assert r.lower_overrun_kwh == pytest.approx(o_exp, abs=1e-6)


def test_asymmetric_power_limits_are_respected():
    # 100 kW load, cheap then dear; charge limit 50 kW, discharge limit 30 kW, both binding.
    kw = dict(load_kw=[100.0] * 8, price_eur_mwh=[10.0] * 4 + [300.0] * 4, capacity_kwh=1000.0, e0_kwh=500.0,
              e_end_kwh=516.0, soc_min_pct=0, soc_max_pct=100, import_limit_kw=1000.0)
    r = solve(inputs(p_charge_kw=50.0, p_discharge_kw=30.0, **kw))
    assert max(r.ess_kw) == pytest.approx(50.0, abs=1e-4)
    assert min(r.ess_kw) == pytest.approx(-30.0, abs=1e-4)
    r = solve(inputs(p_charge_kw=30.0, p_discharge_kw=50.0, **dict(kw, e_end_kwh=500.0)))
    assert max(r.ess_kw) <= 30.0 + 1e-6 and min(r.ess_kw) >= -50.0 - 1e-6
    assert min(r.ess_kw) == pytest.approx(-50.0, abs=1e-4)


def test_asymmetric_limits_with_negative_prices_solve_within_limits():
    r = solve(inputs(p_charge_kw=50.0, p_discharge_kw=30.0, price_eur_mwh=[-50.0] * 4 + [300.0] * 4,
                     load_kw=[20.0] * 8, capacity_kwh=1000.0, soc_min_pct=0, soc_max_pct=100, e0_kwh=500.0,
                     e_end_kwh=500.0, pcc_min_kw=-100.0))
    assert max(r.ess_kw) <= 50.0 + 1e-6 and min(r.ess_kw) >= -30.0 - 1e-6


def test_positive_lower_pcc_limit_is_respected_when_feasible():
    # Dear energy: the plan would discharge to cover the whole 10 kW load; a 5 kW minimum import limits it to 5 kW.
    inp = inputs(price_eur_mwh=[300.0] * 8, e_end_kwh=15.0, pcc_min_kw=5.0)
    r = solve(inp)
    net = [l + p for l, p in zip(inp.load_kw, r.ess_kw)]
    assert all(x >= 5.0 - 1e-6 for x in net)
    assert min(r.ess_kw) == pytest.approx(-5.0, abs=1e-4)
    assert r.lower_overrun_kwh == pytest.approx(0, abs=1e-6) and r.import_overrun_kwh == pytest.approx(0, abs=1e-6)


def test_positive_lower_pcc_limit_reports_overrun_when_infeasible():
    # Net power cannot exceed load + charge limit = 30 kW; a 50 kW minimum is missed by 20 kW for 8 x 0.25 h = 40 kWh.
    inp = inputs(price_eur_mwh=[100.0] * 8, capacity_kwh=1000.0, soc_min_pct=0, soc_max_pct=100, e0_kwh=500.0,
                 e_end_kwh=500.0, pcc_min_kw=50.0)
    r = solve(inp)
    assert r.lower_overrun_kwh == pytest.approx(40.0, abs=1e-4)
    assert r.import_overrun_kwh == pytest.approx(0, abs=1e-6)
