"""A5 optimisation model (A5-IMP R1-R5): ESS schedule that minimises energy cost in EUR.

Units: power kW, energy kWh, price EUR/MWh (input) -> EUR/kWh, cost EUR. Positive ESS power = charging.
PCC power = load + pv + ESS (pv negative = generation); import positive, export positive in its own variable.
OPD (docs/requirements-opd-operational-datapoints.md): separate charge/discharge power limits (R3) and a signed soft
net PCC window [pcc_min_kw, import_limit_kw] (R4).
"""
from dataclasses import dataclass, field
from typing import List, Optional

import pyomo.environ as pyo
from pyomo.opt import SolverStatus, TerminationCondition


@dataclass
class PlanInputs:
    interval_s: int
    load_kw: List[float]            # consumption forecast per step
    pv_kw: List[float]              # production forecast per step (negative = generation)
    price_eur_mwh: List[float]      # energy price per step
    p_charge_kw: float              # ESS charge power limit (positive magnitude)
    p_discharge_kw: float           # ESS discharge power limit (positive magnitude)
    capacity_kwh: float             # ESS capacity
    e0_kwh: float                   # stored energy at the start (total)
    e_end_kwh: float                # target stored energy at the end
    soc_min: float                  # minimum SoC, fraction 0..1
    soc_max: float                  # maximum SoC, fraction 0..1
    import_limit_kw: float          # upper limit U of the net PCC power, import positive (soft)
    pcc_min_kw: float               # lower limit L of the net PCC power, signed: <0 export allowed, >0 minimum import (soft)
    eta_charge: float = 0.95
    eta_discharge: float = 0.95
    grid_tariff_eur_kwh: float = 0.05
    degradation_eur_kwh: float = 0.05
    pcc_penalty_eur_kwh: float = 10.0
    end_penalty_eur_kwh: float = 1.0
    ramp_penalty_eur_kw: float = 0.0001  # per kW of ESS power change between steps (A5-AF)


@dataclass
class PlanResult:
    ok: bool
    status: str
    ess_kw: List[float] = field(default_factory=list)       # per step, positive = charging
    energy_kwh: List[float] = field(default_factory=list)   # E[0..N]
    import_overrun_kwh: float = 0.0
    lower_overrun_kwh: float = 0.0   # energy below the lower PCC limit
    end_deviation_kwh: float = 0.0
    cost_eur: Optional[float] = None
    ramp_cost_eur: float = 0.0


def energy_bounds(inp: PlanInputs):
    """[Emin, Emax] from the SoC window, widened to include E[0] if it is already outside (R1)."""
    e_min = inp.capacity_kwh * inp.soc_min
    e_max = inp.capacity_kwh * inp.soc_max
    return min(e_min, inp.e0_kwh), max(e_max, inp.e0_kwh)


def build_model(inp: PlanInputs) -> pyo.ConcreteModel:
    n = len(inp.load_kw)
    if n == 0 or len(inp.pv_kw) != n or len(inp.price_eur_mwh) != n:
        raise ValueError("load, pv and price series must be non-empty and of equal length")
    dt_h = inp.interval_s / 3600.0
    e_min, e_max = energy_bounds(inp)
    e_end = min(max(inp.e_end_kwh, e_min), e_max)
    p_ch, p_dis = inp.p_charge_kw, inp.p_discharge_kw

    m = pyo.ConcreteModel(name="A5")
    m.dt_h = dt_h                         # plain attribute: step length in hours, used when reporting
    m.T = pyo.RangeSet(0, n - 1)          # steps
    m.K = pyo.RangeSet(0, n)              # energy states

    # ESS power, mutually exclusive charge/discharge (R2)
    m.ch = pyo.Var(m.T, bounds=(0, p_ch))
    m.dis = pyo.Var(m.T, bounds=(0, p_dis))
    m.zc = pyo.Var(m.T, domain=pyo.Binary)
    m.ch_on = pyo.Constraint(m.T, rule=lambda m, t: m.ch[t] <= p_ch * m.zc[t])
    m.dis_on = pyo.Constraint(m.T, rule=lambda m, t: m.dis[t] <= p_dis * (1 - m.zc[t]))

    # PCC balance with soft limits (R3)
    m.imp = pyo.Var(m.T, domain=pyo.NonNegativeReals)
    m.exp = pyo.Var(m.T, domain=pyo.NonNegativeReals)
    m.o_imp = pyo.Var(m.T, domain=pyo.NonNegativeReals)
    m.o_low = pyo.Var(m.T, domain=pyo.NonNegativeReals)
    m.balance = pyo.Constraint(m.T, rule=lambda m, t:
                               m.imp[t] - m.exp[t] == inp.load_kw[t] + inp.pv_kw[t] + m.ch[t] - m.dis[t])
    # Signed net PCC window (OPD R4): L - o_low <= net <= U + o_imp, net = imp - exp. For L <= 0 this is exp <= -L + o_low.
    m.imp_limit = pyo.Constraint(m.T, rule=lambda m, t: m.imp[t] - m.exp[t] <= inp.import_limit_kw + m.o_imp[t])
    m.low_limit = pyo.Constraint(m.T, rule=lambda m, t: m.imp[t] - m.exp[t] >= inp.pcc_min_kw - m.o_low[t])
    if any(p < 0 for p in inp.price_eur_mwh):
        # With a negative price, importing and exporting at once could look profitable: forbid it.
        big_m = max(abs(l + v) for l, v in zip(inp.load_kw, inp.pv_kw)) + max(p_ch, p_dis) + 1.0
        m.zi = pyo.Var(m.T, domain=pyo.Binary)
        m.imp_on = pyo.Constraint(m.T, rule=lambda m, t: m.imp[t] <= big_m * m.zi[t])
        m.exp_on = pyo.Constraint(m.T, rule=lambda m, t: m.exp[t] <= big_m * (1 - m.zi[t]))

    # Stored energy (R1)
    m.E = pyo.Var(m.K)
    m.E[0].fix(inp.e0_kwh)
    for k in range(1, n + 1):
        m.E[k].setlb(e_min)
        m.E[k].setub(e_max)
    m.energy = pyo.Constraint(m.T, rule=lambda m, t:
                              m.E[t + 1] == m.E[t] + (m.ch[t] * inp.eta_charge - m.dis[t] / inp.eta_discharge) * dt_h)

    # Soft end target (R4)
    m.dev_up = pyo.Var(domain=pyo.NonNegativeReals)
    m.dev_down = pyo.Var(domain=pyo.NonNegativeReals)
    m.end_target = pyo.Constraint(expr=m.E[n] - e_end == m.dev_up - m.dev_down)

    # Ramp of the ESS power between consecutive steps (A5-AF R1): breaks ties inside constant-price slots
    m.TR = pyo.Set(initialize=list(range(1, n)))
    m.ramp = pyo.Var(m.TR, domain=pyo.NonNegativeReals)
    m.ramp_up = pyo.Constraint(m.TR, rule=lambda m, t:
                               m.ramp[t] >= (m.ch[t] - m.dis[t]) - (m.ch[t - 1] - m.dis[t - 1]))
    m.ramp_down = pyo.Constraint(m.TR, rule=lambda m, t:
                                 m.ramp[t] >= (m.ch[t - 1] - m.dis[t - 1]) - (m.ch[t] - m.dis[t]))
    m.ramp_cost = pyo.Expression(expr=sum(m.ramp[t] for t in m.TR) * inp.ramp_penalty_eur_kw)

    # Cost in EUR (R5; A5-AF R2: ramp term per kW of change, not scaled by dt)
    def cost(m):
        energy_cost = sum(
            dt_h * (m.imp[t] * (inp.price_eur_mwh[t] / 1000.0 + inp.grid_tariff_eur_kwh)
                    - m.exp[t] * inp.price_eur_mwh[t] / 1000.0
                    + m.ch[t] * inp.degradation_eur_kwh
                    + (m.o_imp[t] + m.o_low[t]) * inp.pcc_penalty_eur_kwh)
            for t in m.T)
        return energy_cost + (m.dev_up + m.dev_down) * inp.end_penalty_eur_kwh + m.ramp_cost
    m.cost = pyo.Objective(rule=cost, sense=pyo.minimize)
    return m


def solve(m: pyo.ConcreteModel, time_limit_s: float = 300, solver_name: str = "glpk") -> PlanResult:
    """Solve and extract the plan. ok=False for any result without a usable solution."""
    solver = pyo.SolverFactory(solver_name)
    if solver_name == "glpk":
        solver.options["tmlim"] = int(time_limit_s)
    results = solver.solve(m, load_solutions=False)
    term = results.solver.termination_condition
    status = f"{results.solver.status}/{term}"
    usable = term in (TerminationCondition.optimal, TerminationCondition.feasible) or (
        term == TerminationCondition.maxTimeLimit and len(results.solution) > 0)
    if results.solver.status not in (SolverStatus.ok, SolverStatus.warning) or not usable:
        return PlanResult(ok=False, status=status)
    m.solutions.load_from(results)

    ess_kw = [pyo.value(m.ch[t]) - pyo.value(m.dis[t]) for t in m.T]
    energy = [pyo.value(m.E[k]) for k in m.K]
    return PlanResult(
        ok=True,
        status=status,
        ess_kw=[v + 0.0 for v in ess_kw],          # + 0.0: never -0.0
        energy_kwh=energy,
        import_overrun_kwh=sum(pyo.value(m.o_imp[t]) for t in m.T) * m.dt_h,
        lower_overrun_kwh=sum(pyo.value(m.o_low[t]) for t in m.T) * m.dt_h,
        end_deviation_kwh=pyo.value(m.dev_up) - pyo.value(m.dev_down),
        cost_eur=pyo.value(m.cost),
        ramp_cost_eur=pyo.value(m.ramp_cost),
    )
