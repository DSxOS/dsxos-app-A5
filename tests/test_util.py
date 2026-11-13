"""A5-IMP AC1(b): time grid."""
from datetime import datetime, timezone, timedelta

import Util


def test_align_start_rounds_down_to_the_interval():
    t = datetime(2026, 11, 13, 22, 0, 11, 303000, tzinfo=timezone.utc)
    assert Util.align_start(t, 60) == datetime(2026, 11, 13, 22, 0, 0, tzinfo=timezone.utc)
    assert Util.align_start(t, 900) == datetime(2026, 11, 13, 22, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 11, 13, 22, 14, 59, tzinfo=timezone.utc)
    assert Util.align_start(t2, 900) == datetime(2026, 11, 13, 22, 0, 0, tzinfo=timezone.utc)


def test_align_start_handles_other_time_zones():
    eet = timezone(timedelta(hours=2))
    t = datetime(2026, 11, 14, 0, 7, 30, tzinfo=eet)  # = 22:07:30 UTC
    assert Util.align_start(t, 900) == datetime(2026, 11, 13, 22, 0, 0, tzinfo=timezone.utc)


def test_series_step_count_includes_both_ends():
    start = datetime(2026, 11, 14, 0, 0, tzinfo=timezone.utc)
    prs = [{"time": "2026-11-13T23:59:00Z", "value": 1.0}, {"time": "2026-11-14T00:30:00Z", "value": 2.0}]
    out = Util.extract_prognosis_values(prs, "x", start, start + timedelta(hours=1), 900)
    assert [r["value"] for r in out] == [1.0, 1.0, 2.0, 2.0, 2.0]
