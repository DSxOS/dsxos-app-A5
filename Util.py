from datetime import datetime, timedelta, timezone
from typing import List, Dict, Union


class TaskFailException(Exception):
    """A forecast cannot provide a value for the planning window."""
    pass


def align_start(now: datetime, interval_s: int) -> datetime:
    """Round a time down to a multiple of interval_s since the UTC epoch (A5-IMP R8)."""
    if interval_s <= 0:
        raise ValueError("interval must be positive")
    epoch_s = int(now.astimezone(timezone.utc).timestamp())
    return datetime.fromtimestamp(epoch_s - epoch_s % interval_s, tz=timezone.utc)


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
            val = prs[current_idx]["value"]
        else:
            raise TaskFailException(f"No valid {label} value for time {expected_time}")

        result.append({"time": expected_time, "value": val})

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
            continue  # ignore empty series
        times = [parse_time(point["time"]) for point in series]
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