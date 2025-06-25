from pyomo.environ import *
import numpy as np
import pandas as pd
import query_utils
from pathlib import Path
import argparse
import yaml
from datetime import datetime, timezone
from datetime import timedelta
import Util
from logger import setup_logger
from debug import debug_model

# create parser
parser = argparse.ArgumentParser(description="Run A5 with config file")
parser.add_argument("-c", "--config", required=True, help="Path to config YAML file")
args = parser.parse_args() # Read arguments
with open(args.config, "r") as f: # Open and read config-file
    raw_data = yaml.safe_load(f)
    
# Extract API URL and Token
api_url = raw_data["params"]["apiEndpoint"]
api_token = raw_data["params"]["token"]
api_headers = {"Authorization": api_token}

app_name = raw_data["appModule"]

# Initialize query_utils with URL + headers    
query_utils.init(api_url, api_headers)
logger = setup_logger(
    log_file="query.log",
    loki_url="http://localhost:3100/loki/api/v1/push",  # Loki address
    loki_tags={"app_name": app_name},        # add more tags if needed
    level="INFO"
)

logger.info(f"{app_name} start.")

start_time = datetime.now(timezone.utc)

########################################################################
# Read and validate input
########################################################################
interval = raw_data["params"]["interval"]
min_period = raw_data["params"]["min_period"]

np = [{"time": r["time"], "value": r["value"]} for r in query_utils.get_last_prognosis_readings(raw_data["params"]["npPriceIdentifier"])] # elering
prod = [{"time": r["time"], "value": r["value"]/1000} for r in query_utils.get_last_prognosis_readings(raw_data["params"]["productionPrognosisIdentifier"])] # production prognosis
cons = [{"time": r["time"], "value": r["value"]/1000} for r in query_utils.get_last_prognosis_readings(raw_data["params"]["consumptionPrognosisIdentifier"])] # consumption prognosis

ESS_kW = query_utils.get_datapoint(raw_data["params"]["ess_max_P_dp_id"])[0]["lastReadingValue"]/1000 # salvesti võimsus - ess_max_P.last_reading
ESS_kWh = query_utils.get_datapoint(raw_data["params"]["ess_charge_dp_id"])[0]["lastReadingValue"]/1000 # salvesti efektiivne laetus optimeerimise alguses kWh-des (võib olla negatiivne) - ess_charge.last_reading
ESS_max_kWh = query_utils.get_datapoint(raw_data["params"]["ess_max_E_dp_id"])[0]["lastReadingValue"]/1000 # salvesti absoluutne mahutavus - ess_max_E.last_reading
P_imp_lim_kW = raw_data["params"]["pccImportLimitW"]/1000  # main.get_datapoint("pccImportLimitW")[0]["lastReadingValue"] # pcc max tarbimine - pccImportLimitW
P_exp_lim_kW = raw_data["params"]["pccExportLimitW"]/1000 # main.get_datapoint("pccExportLimitW")[0]["lastReadingValue"] # pcc max müük/tootlus (negatiivne) - pccExportLimitW
ESS_SOC_min = raw_data["params"]["ess_min_soc"] # main.get_datapoint("essMinSoc")[0]["lastReadingValue"] # within safe limits - essMinSoc
ESS_SOC_max = raw_data["params"]["ess_max_soc"] # main.get_datapoint("essMaxSoc")[0]["lastReadingValue"] # - essMaxSoc
ESS_safe_min = query_utils.get_datapoint(raw_data["params"]["essMinSafeLim"])[0]["lastReadingValue"] # - ess_min_batt_safe_lim.last_reading
# ESS_safe_min = raw_data["params"]["essMinSafeLim"] # - ess_min_batt_safe_lim.last_reading
ESS_END_kWh = query_utils.get_datapoint(raw_data["params"]["ess_charge_dp_id"])[0]["lastReadingValue"]/1000 # salvesti efektiivne laetus optimeerimise lõpus kWh-des - ess_charge.last_reading
kW_to_kWh = interval / 3600 # kordaja võimsuse teisendamiseks energiaks (intervallist tulenev)

current_dp_id = raw_data["params"]["essCurrentPowerPlanIdentifier"]
result_dp_id = query_utils.get_datapoint(raw_data["params"]["essResultPowerPlanIdentifier"])[0]["id"]

########################################################################
logger.info(f"len(prod): {len(prod)}")
logger.info(f"len(cons): {len(cons)}")
logger.info(f"len(np): {len(np)}")
########################################################################
print("=========================")
print(f"ESS_kW -- ,{ESS_kW}!")
print(f"ESS_kWh -- ,{ESS_kWh}!")
print(f"ESS_max_kWh -- ,{ESS_max_kWh}!")
print(f"P_imp_lim_kW -- ,{P_imp_lim_kW}!")
print(f"P_exp_lim_kW -- ,{P_exp_lim_kW}!")
print(f"ESS_SOC_min -- ,{ESS_SOC_min}!")
print(f"ESS_SOC_max -- ,{ESS_SOC_max}!")
print(f"ESS_safe_min -- ,{ESS_safe_min}!")
print(f"ESS_END_kWh -- ,{ESS_END_kWh}!")
print(f"kW_to_kWh -- ,{kW_to_kWh}!")
print(f"interval -- ,{interval}!")
print(f"min_period -- ,{min_period}!")
print(f"current_dp_id -- ,{current_dp_id}!")
print(f"result_dp_id -- ,{result_dp_id}!")
########################################################################

ESS_eff_kWh = (ESS_max_kWh*(ESS_SOC_max - ESS_SOC_min)/100) # Salvesti efektiivne mahutavus
ESS_SOC_0 = (ESS_max_kWh*ESS_SOC_min/100 + ESS_kWh)/ESS_max_kWh*100
ESS_SOC_END = (ESS_END_kWh/ESS_eff_kWh + ESS_safe_min)*100
ESS_SOC_END = (ESS_max_kWh*ESS_SOC_min/100 + ESS_END_kWh)/ESS_max_kWh*100
ESS_SOC_0 = 0 if ESS_SOC_0 < 0 else ESS_SOC_0
ESS_SOC_0 = 100 if ESS_SOC_0 > 100 else ESS_SOC_0
ESS_SOC_END = ESS_SOC_min if ESS_SOC_END < ESS_SOC_min else ESS_SOC_END
ESS_SOC_END = ESS_SOC_max if ESS_SOC_END > ESS_SOC_max else ESS_SOC_END

########################################################################
print("=========================")
print(f"ESS_eff_kWh -- ,{ESS_eff_kWh}!")
print(f"ESS_SOC_0 -- ,{ESS_SOC_0}!")
print(f"ESS_SOC_END -- ,{ESS_SOC_END}!")
########################################################################

# Convert list-of-dict model into a DataFrame
def model_to_df(m):
    st = 0
    en = len(m.T)

    periods = range(st, en)
    print(f"periods: , {len(periods)}")
    load = [value(m.P_kW[i]) for i in periods]
    pv = [value(m.PV_kW[i]) for i in periods]
    pcc_export = [value(m.PCC_EXPORT_kW[i]) for i in periods]
    pcc_import_kW = [value(m.PCC_IMPORT_kW[i]) for i in periods]
    ess = [value(m.ESS_kW[i]) for i in periods]
    ess_soc = [value(m.ESS_SoC[i]) for i in periods]
    pcc = [value(m.PCC_IMPORT_kW[i])-value(m.PCC_EXPORT_kW[i]) for i in periods]
    spot = [value(m.SPOT_EUR_kWh[i]) for i in periods]

    df_dict = {
        'Period': periods,
        'Load': load,
        'PV': pv,
        'ESS': ess,
        'ESS effective SoC': ess_soc,
        'PCC Export': pcc_export,
        'PCC Import': pcc_import_kW,
        'PCC': pcc,
        'Spot Price': spot
    }

    df = pd.DataFrame(df_dict)
    print(df)
    return df

# Find a common time range for two or more different forecasts
time_range = Util.find_common_time_range([np, cons, prod])
# Calculate the length of the common time range
period = datetime.fromisoformat(time_range["end"]) - datetime.fromisoformat(time_range["start"])
# If common time range is bigger than given min_period
if int(period.total_seconds()) > min_period:
    time_range_start = datetime.fromisoformat(time_range["start"])
    time_range_end = datetime.fromisoformat(time_range["end"])
    count = Util.calculate_count(np, start_time, interval)
    initial = query_utils.get_datapoint(raw_data["params"]["npPriceIdentifier"])[0]["lastReadingValue"]

    print(f"count: {count}")
    print(f"time_range: {time_range}")
    print(f"initial: {initial}")
    print(f"period: {period.total_seconds()} seconds")
    
    # regenerates prognosis values starting with start time and initial value and with given interval
    np_extracted = Util.generate_result_series(np, start_time, time_range_end, interval, initial)
    # extracts prognosis values starting with start time, with given interval and common time range endtime
    cons_extracted = Util.extract_prognosis_values(cons, "consumption", start_time, time_range_end, interval)
    prod_extracted = Util.extract_prognosis_values(prod, "production", start_time, time_range_end, interval)


    ########################################################################
    logger.info(f"len(prod_extracted): {len(prod_extracted)}")
    # logger.info(f"prod_extracted: {prod_extracted}")
    logger.info(f"len(cons_extracted): {len(cons_extracted)}")
    # logger.info(f"cons_extracted: {cons_extracted}")
    logger.info(f"len(np_extracted): {len(np_extracted)}")
    # logger.info(f"np_extracted: {np_extracted}")
    ########################################################################
    assert len(prod_extracted) == len(cons_extracted), "len(prod_extracted) != len(cons_extracted)"
    assert len(prod_extracted) == len(np_extracted), "len(prod) != len(np_extracted)"

    data = pd.DataFrame({
        'Load': Util.extract_values_only(cons_extracted),
        'PV': Util.extract_values_only(prod_extracted),
        'Spot': Util.extract_values_only(np_extracted),
    })
else: logger.error(f"Not enough current prognosis")


########################################################################
# Build Model
########################################################################
m = ConcreteModel()

# Fixed Parameters
m.T = Set(initialize=data.index.tolist(), doc='Indexes', ordered=True)
m.P_kW = Param(m.T, initialize=data.Load, doc='Load [kW]', within=Any)
m.PV_kW = Param(m.T, initialize=data.PV, doc='PV generation [kW]', within=Any)
m.SPOT_EUR_kWh = Param(m.T, initialize=data.Spot, doc='Spot Market Price [€/kWh]', within=Any)

# Variable Parameters
m.PCC_exp_z = Var(m.T, bounds=(0,1), within=NonNegativeIntegers)
m.PCC_imp_z = Var(m.T, bounds=(0,1), within=NonNegativeIntegers)
m.PCC_EXPORT_kW = Var(m.T, within=NonNegativeReals)
m.PCC_IMPORT_kW = Var(m.T, within=NonNegativeReals)
m.ESS_kW = Var(m.T, bounds=(-ESS_kW, ESS_kW), doc='ESS P [kW]')
m.ESS_kW_charge = Var(m.T, within=NonNegativeReals, doc='ESS P charge [kW]')
m.ESS_kW_discharge = Var(m.T, within=NonNegativeReals, doc='ESS P discharge [kW]')
m.ESS_kW_charge_z = Var(m.T, bounds=(0,1), within=NonNegativeIntegers)
m.ESS_kW_discharge_z = Var(m.T, bounds=(0,1), within=NonNegativeIntegers)
m.ESS_SoC = Var(m.T, bounds=(0, 100), initialize=ESS_SOC_0, doc='ESS effective SoC [%]',  within=NonNegativeReals)

# Rules
def sim_import_export_restrict_rule(m, t):
    "Prohibit simultaneous PCC export and import"
    return m.PCC_exp_z[t] + m.PCC_imp_z[t] <= 1

m.sim_import_export_restrict = Constraint(m.T, rule=sim_import_export_restrict_rule)

def pcc_export_kW_rule(m, t):
    "PCC export calculation"
    return m.PCC_EXPORT_kW[t] <= -P_exp_lim_kW*m.PCC_exp_z[t]

m.pcc_export = Constraint(m.T, rule=pcc_export_kW_rule)

def pcc_import_kW_rule(m, t):
    "PCC import calculation"
    return m.PCC_IMPORT_kW[t] <= P_imp_lim_kW*m.PCC_imp_z[t]

m.pcc_import_kW = Constraint(m.T, rule=pcc_import_kW_rule)

def sim_charge_discharge_restrict_rule(m, t):
    "Prohibit ESS simultaneous charging and discharging"
    return m.ESS_kW_charge_z[t] + m.ESS_kW_discharge_z[t] <= 1

m.sim_charge_discharge_restrict = Constraint(m.T, rule=sim_charge_discharge_restrict_rule)

def ESS_kW_charge_rule(m, t):
    "ESS charge kW Calculation"
    return m.ESS_kW_charge[t] <= ESS_kW*m.ESS_kW_charge_z[t]

m.ESS_kW_charging = Constraint(m.T, rule=ESS_kW_charge_rule)

def ESS_kW_discharge_rule(m, t):
    "ESS discharge kW Calculation"
    return m.ESS_kW_discharge[t] <= ESS_kW*m.ESS_kW_discharge_z[t]

m.ESS_kW_discharging = Constraint(m.T, rule=ESS_kW_discharge_rule)

def ESS_kW_calc_rule(m, t):
    "ESS kW Calculation"
    return m.ESS_kW[t] == m.ESS_kW_charge[t] - m.ESS_kW_discharge[t]

m.ESS_kW_calculation = Constraint(m.T, rule=ESS_kW_calc_rule)

def ess_SoC_rule(m, t):
    "ESS SOC Calculation"
    if t >= 1:
        return m.ESS_SoC[t] == m.ESS_SoC[t-1] + ((m.ESS_kW[t-1]*kW_to_kWh)/ESS_eff_kWh)*100
    else:
        return m.ESS_SoC[t] == ESS_SOC_0

m.ess_SoC_const = Constraint(m.T, rule=ess_SoC_rule)

def soc_end_target_rule(m):
    "End SoC value"
    return m.ESS_SoC[len(m.ESS_SoC)-1] + ((m.ESS_kW[len(m.ESS_SoC)-1]*kW_to_kWh)/ESS_eff_kWh)*100 == ESS_SOC_END

m.soc_end_target = Constraint(rule=soc_end_target_rule)

def pcc_self_consumption_rule(m, t):
    return m.PCC_IMPORT_kW[t] - m.PCC_EXPORT_kW[t] == m.P_kW[t] + m.PV_kW[t] + m.ESS_kW[t]

m.pcc_self_consumption = Constraint(m.T, rule=pcc_self_consumption_rule)

########################################################################
# Cost function and optimization objective
########################################################################

# Value constants
ESS_DEG_COST = 0.05
GRID_TARIFF_COMPONENT = 0.05

# Cost function
cost = sum(( (m.PCC_IMPORT_kW[t]/1000)*kW_to_kWh*(m.SPOT_EUR_kWh[t]/1000 + GRID_TARIFF_COMPONENT) - 
            (m.PCC_EXPORT_kW[t]/1000)*kW_to_kWh*m.SPOT_EUR_kWh[t]/1000 + 
            (m.ESS_kW_charge[t]/1000)*kW_to_kWh*ESS_DEG_COST ) for t in m.T) #
m.objective = Objective(expr = cost, sense=minimize)

########################################################################
# Solve
# ######################################################################
solver = SolverFactory('glpk', options={'tmlim': 300})
results = solver.solve(m)
results.write()

# Debug the model to log infeasible constraints, variable values, and constraint statuses 
# and save diagnostic output to a file
debug_model(m)

# results_path = Path(f"results_{start_time.strftime('%Y.%m.%d_%H.%M.%S')}.json").resolve()

# Check that the solver completed successfully with an optimal or feasible result
if (results.solver.status == SolverStatus.ok) and (
    (results.solver.termination_condition == TerminationCondition.optimal) 
    or (results.solver.termination_condition == TerminationCondition.feasible)
    ):
    # Format results as data frame
    results_df = model_to_df(m)
    
    # # Save to JSON
    # try:
    #     results_df.to_json(results_path, orient="records", indent=2)
    #     logger.info(f"Results saved to {results_path.resolve()}")
    # except Exception as e:
    #     logger.error(f"Failed to save results to JSON: {e}")
    
    # Use the variable from 'results_df' if available;  
    # otherwise, fall back to the previous prognosis and readings.
    if (len(results_df) == 0):
        # Use old prognosis, if it exists
        logger.warning(f"Optimization failed - empty result. Using old power prognosis.")
        essPowerPrognosisRaw = [r["value"] for r in query_utils.get_last_prognosis_readings(current_dp_id)]
    else:
        # use optimized results
        essPowerPrognosisRaw = results_df["ESS"].values * 1000
        
    # Create a list of prognosis readings with corresponding timestamps
    essPowerPlanned =[]
    for i, value in enumerate(essPowerPrognosisRaw):
        reading_time = start_time + timedelta(seconds=i * interval)  
        essPowerPlanned.append({
            "time": reading_time.isoformat().replace('+00:00', 'Z'),
            "value": value
        })

    # Construct the prognosis payload with datapoint ID, timestamp, and planned ESS power readings
    prognosis_payload = {
        "datapointId": result_dp_id,
        "time": start_time.isoformat().replace('+00:00', 'Z'),
        "readings":essPowerPlanned
    }
    # POST datapoint prognosis and prognosis readings
    response = query_utils.post_datapoint_prognosis(prognosis_payload)
    logger.info(f"datapoint prognosis was posted: {response}")
        
else: 
    logger.error(f"Solver failed - empty result")

logger.info(f"{app_name} finished")