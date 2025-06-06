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
    count = len(prs) * (3600 // interval_seconds) + math.ceil(start_difference / interval_seconds)
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

def generate_result_series(prs: List[Dict[str, Union[str, datetime, float]]], start: datetime, interval: int, count: int, initial: float) -> List:
    validate_inputs(prs, start, interval, count, initial)
    # print(f"prs: -- -- --", prs)
    # print(f"start: -- -- --", start)
    # print(f"interval: -- -- --", interval)
    # print(f"count: -- -- --", count)
    # print(f"initial: -- -- --", initial)
    
    for r in prs:
        r["time"] = parse_time(r["time"])
    # print(f"r: -- -- --", r)
    
    prs.sort(key=lambda r: r["time"])  #  ajaliselt sorteeritud
    times = [r["time"] for r in prs]
    # print(f"times: ", times, len(times))
    
    result = [initial] + [0.0] * (count - 1)

    # algväärtus + ülejäänud kohad
    # print(f"result -- generate_result_series:  ", result, len(result))


    def find_j_for_time(target_time: datetime) -> int:
        low, high = 0, len(times) - 1
        best_idx = 0
        while low <= high:
            mid = (low + high) // 2
            if times[mid] <= target_time:
                best_idx = mid
                low = mid + 1
            else:
                high = mid - 1
        return best_idx

    for i in range(1, count):
        current_time = start + timedelta(seconds=i * interval)
        prev_time = start + timedelta(seconds=(i - 1) * interval)
        j = find_j_for_time(current_time)

        if times[j] < prev_time:
            result[i] = result[i - 1]
        else:
            result[i] = prs[j]["value"]
        #print("Result:", result[i])
    #print("Results:", result)
    return result

def extract_prognosis_values(prs, label: str, start: Union[str, datetime], interval: int, count: int) -> List[float]:
    if not prs or len(prs) == 0:
        raise TaskFailException(f"No proper {label}.")

    if len(prs) < count:
        raise TaskFailException(f"Not enough {label}. Length {len(prs)}, expected {count}")

    if isinstance(start, str):
        start = datetime.fromisoformat(start.replace("Z", "+00:00"))

    result = []

    for i in range(count):
        item = prs[i]
        time = parse_time(item["time"])
        expected_time = start + timedelta(seconds=i * interval)
        if time != expected_time:
            raise TaskFailException(
                f"{label} times do not match. Expected {expected_time}, given {time} at index {i}"
            )

        value = item.get("value")
        if value is None:
            raise TaskFailException(f"{label} has null value at index {i}")

        result.append(value)

    return result
