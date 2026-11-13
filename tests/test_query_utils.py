"""A5-IMP AC1(a) paging and AC1(j) batch output."""
import pytest

import query_utils


class FakeQuery:
    def __init__(self, log, pages=None, post_reply=None):
        self.log, self.pages, self.post_reply, self.params = log, pages, post_reply, {}

    def filter(self, **kw):
        self.params.update({k.replace("__", "."): v for k, v in kw.items()})
        return self

    def order_by(self, field, direction="asc"):
        self.params["sort"] = f"{field},{direction}"
        return self

    def paginate(self, page=0, size=100):
        self.params.update(page=page, size=size)
        return self

    def get(self, endpoint, params=None):
        self.log.append(("GET", endpoint, dict(self.params)))
        return self.pages(self.params)

    def post(self, endpoint, data=None, json=None):
        self.log.append(("POST", endpoint, json))
        return self.post_reply(endpoint, json)


def test_prognosis_readings_are_fetched_through_all_pages_sorted(monkeypatch):
    data = [{"time": f"2026-11-14T00:0{i}:00Z", "value": float(i)} for i in range(5)]
    log = []

    def pages(p):
        s = p["page"] * p["size"]
        return data[s:s + p["size"]]

    monkeypatch.setattr(query_utils, "Q", lambda: FakeQuery(log, pages=pages))
    out = query_utils.get_prognosis_readings(42, page_size=2)
    assert out == data
    assert [e[2]["page"] for e in log] == [0, 1, 2]
    assert all(e[2]["sort"] == "time,asc" and e[2]["datapointPrognosisId.equals"] == 42 for e in log)


def test_failed_page_returns_none(monkeypatch):
    monkeypatch.setattr(query_utils, "Q", lambda: FakeQuery([], pages=lambda p: None))
    assert query_utils.get_prognosis_readings(42) is None


def test_plan_is_posted_in_one_batch_and_count_is_checked(monkeypatch):
    log = []

    def reply(endpoint, body):
        return {"id": 7} if endpoint == "/datapoint-prognoses" else [dict(r, id=i) for i, r in enumerate(body)]

    monkeypatch.setattr(query_utils, "Q", lambda: FakeQuery(log, post_reply=reply))
    readings = [{"time": "2026-11-14T00:00:00Z", "value": 1.0}, {"time": "2026-11-14T00:01:00Z", "value": -2.0}]
    query_utils.post_datapoint_prognosis(530, "2026-11-14T00:00:00Z", readings)
    assert [(e[0], e[1]) for e in log] == [("POST", "/datapoint-prognoses"), ("POST", "/prognosis-readings/batch")]
    assert log[0][2] == {"datapointId": 530, "time": "2026-11-14T00:00:00Z"}
    assert all(r["datapointPrognosisId"] == 7 for r in log[1][2])


def test_short_batch_reply_is_an_error(monkeypatch):
    def reply(endpoint, body):
        return {"id": 7} if endpoint == "/datapoint-prognoses" else body[:1]

    monkeypatch.setattr(query_utils, "Q", lambda: FakeQuery([], post_reply=reply))
    with pytest.raises(RuntimeError):
        query_utils.post_datapoint_prognosis(530, "t", [{"time": "a", "value": 1}, {"time": "b", "value": 2}])
