# dsxos-app-A5 - Economic Optimisation Application

## Energy management application.

This application is designed to optimize the scheduling of Energy Storage Systems (ESS) for economic efficiency. By utilizing load and production forecasts, it models Point of Common Coupling (PCC) energy usage over a specified outlook period. These forecasts enable the application to determine the optimal ESS schedule, maximizing economic performance.

Energy management algorithm is described in detail [here](https://github.com/DSxOS/platform/blob/main/docs/workermodules/Economic_Optimisation_Description.pdf)

## Files

- main.py - Main entry point for running the peak shaving application.
- debug.py - Debugging tool for diagnosing model infeasibilities, logging variable/constraint states, and saving diagnostics.
- logger.py - Logging utility.
- query_utils.py - Helper methods for interacting with the database: 'get_datapoint' , 'get_last_reading', 'get_last_reading_value', 'get_last_prognosis_reading', 'get_datapoint_prognosis', 'post_prognosis_readings', 'post_datapoint_prognosis'.
- Query.py - Abstractions for HTTP-based data access (GET, POST, PUT, DELETE).
- Util.py - Data processing utilities: 'calculate_count', 'validate_inputs', 'parse_time', 'generate_result_series', 'extract_prognosis_values', 'find_common_time_range', 'extract_values_only'.
- requirements.txt - Required Python packages.
- example_config.yaml - Example configuration file used by main.py

## Requirements

Install the required dependencies:

```bash
pip install -r requirements.txt
```

## Running the Application

Ensure example_config.yaml is configured, then run:

```bash
python main.py
```
