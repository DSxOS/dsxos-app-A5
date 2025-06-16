from datetime import datetime, timedelta
from typing import List, Dict, Union
import math

class TaskFailException(Exception):
    """Exception for use in forecast validation."""
    pass

def calculate_count(prs, start, interval_seconds):
    if not prs:
        return 0

    first_time = datetime.fromisoformat(prs[0]["time"]) #.replace("+00:00", "Z"))
    start_difference = int((first_time - start).total_seconds())
    print(f"first_time: {first_time} --- start: {start} --- start difference: {start_difference}")
    if start_difference > 0: 
        count = len(prs) * (3600 // interval_seconds) + math.ceil(start_difference / interval_seconds)
    else: 
        count = 0
    return count

def validate_inputs(prs: List[Dict[str, Union[str, datetime, float]]], 
                    start: datetime, interval: int, count: int, initial: float):
    if not isinstance(prs, list):
        raise TypeError("prs must be list")
    if not all(isinstance(r, dict) for r in prs):
        raise TypeError("prs elements must be dict's")
    if not isinstance(start, datetime):
        raise TypeError("start must be datetime object")
    if not isinstance(interval, int) or interval <= 0:
        raise ValueError("interval must be positive integer")
    if not isinstance(count, int) or count <= 0:
        raise ValueError("count must be positive integer")
    if not isinstance(initial, (int, float)):
        raise TypeError("initial must be number")

def parse_time(time_val: Union[str, datetime]) -> datetime:
    if isinstance(time_val, datetime):
        return time_val
    elif isinstance(time_val, str):
        return datetime.fromisoformat(time_val) #.replace("Z", "+00:00"))
    else:
        raise TypeError("time must be string or datetime")

def generate_result_series(
    prs: List[Dict[str, Union[str, datetime, float]]],
    start: datetime,
    end: datetime,
    interval: int,
    initial: float
) -> List[Dict[str, Union[datetime, float]]]:
    if start >= end:
        raise ValueError("start must be before end")
    if interval <= 0:
        raise ValueError("interval must be positive")

    total_seconds = (end - start).total_seconds()
    count = int(total_seconds // interval) + 1  # include start

    for r in prs:
        r["time"] = parse_time(r["time"])

    prs = [r for r in prs if r["time"] <= end]  # lubame ka enne starti
    prs.sort(key=lambda r: r["time"])

    result = []
    current_idx = 0
    last_value = initial

    for i in range(count):
        current_time = start + timedelta(seconds=i * interval)

        while current_idx + 1 < len(prs) and prs[current_idx + 1]["time"] <= current_time:
            current_idx += 1

        if prs and prs[current_idx]["time"] <= current_time:
            last_value = prs[current_idx]["value"]

        result.append({"time": current_time, "value": last_value})

    return result

def extract_prognosis_values(
    prs: List[Dict[str, Union[str, datetime, float]]],
    label: str,
    start: Union[str, datetime],
    end: Union[str, datetime],
    interval: int
) -> List[Dict[str, Union[datetime, float]]]:
    if not prs:
        raise TaskFailException(f"No proper {label}.")

    if isinstance(start, str):
        start = datetime.fromisoformat(start.replace("Z", "+00:00"))
    if isinstance(end, str):
        end = datetime.fromisoformat(end.replace("Z", "+00:00"))

    if start >= end:
        raise ValueError("start must be before end")
    if interval <= 0:
        raise ValueError("interval must be positive")

    total_seconds = (end - start).total_seconds()
    count = int(total_seconds // interval) + 1

    for r in prs:
        r["time"] = parse_time(r["time"])

    prs = [r for r in prs if r["time"] <= end]  # võib olla ka enne starti
    prs.sort(key=lambda r: r["time"])
    times = [r["time"] for r in prs]

    result = []
    current_idx = 0

    for i in range(count):
        expected_time = start + timedelta(seconds=i * interval)
        # Leia viimane väärtus, mille aeg ≤ expected_time
        while current_idx + 1 < len(prs) and prs[current_idx + 1]["time"] <= expected_time:
            current_idx += 1

        if prs[current_idx]["time"] <= expected_time:
            value = prs[current_idx]["value"]
        else:
            raise TaskFailException(f"No valid {label} value for time {expected_time}")

        result.append({"time": expected_time, "value": value})

    return result

def find_common_time_range(series_list: List[List[Dict[str, str]]]) -> Dict[str, str]:
    """
    Leiab maksimaalse miinimumaja ja minimaalse maksimumaja aegridade loendist.

    Args:
        series_list: List massiive, kus iga massiiv on kujul [{"time": "...", "value": ...}, ...]

    Returns:
        Dict, kus on 'start' ja 'end' ISO 8601 kuupäevadena.
    """
    min_starts = []
    max_ends = []

    for series in series_list:
        if not series:
            continue  # ignoreeri tühje seeriaid
        times = [datetime.fromisoformat(point["time"]) for point in series]
        min_starts.append(min(times))
        max_ends.append(max(times))

    if not min_starts or not max_ends:
        raise ValueError("Kõik sisendseeriad on tühjad või puuduvad.")

    max_of_mins = max(min_starts)
    min_of_maxs = min(max_ends)

    return {
        "start": max_of_mins.isoformat(),
        "end": min_of_maxs.isoformat()
    }
    
def extract_values_only(series: List[Dict[str, Union[datetime, float]]]) -> List[float]:
    return [entry["value"] for entry in series]