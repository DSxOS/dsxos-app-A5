"""Data server access for A5: authentication, datapoints, forecasts and plan output."""
import logging

from Query import Query

logger = logging.getLogger("A5Runner")

# Data server maximum page size (spring.data.web.pageable.max-page-size).
MAX_PAGE_SIZE = 10000

_query_url = None
_query_headers = None


def init(url, headers):
    global _query_url, _query_headers
    _query_url = url
    _query_headers = headers
    logger.info(f"query_utils initialized with URL: {_query_url}")


def Q():
    """New Query object with the current base URL and headers."""
    return Query(_query_url, headers=_query_headers)


def add_header(key, value):
    global _query_headers
    if _query_headers is None:
        _query_headers = {}
    _query_headers[key] = value


def get_token(client_id, client_secret):
    """Exchange the API credential for a short-lived JWT (client_credentials, same as A4).
    Returns the access token, or None if the request failed or returned no token."""
    token_data = Q()._request("POST", "/auth/token", data={
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    })
    if not token_data or "access_token" not in token_data:
        return None
    return token_data["access_token"]


###########################################################
# GET
###########################################################

def get_datapoint(dp_identifier):
    """List with the datapoint (empty if it does not exist), or None if the request failed."""
    return (
        Q()
        .filter(identifier__equals=dp_identifier)
        .paginate(page=0, size=1)
        .get("/datapoints")
    )


def get_prognosis_readings(prognosis_id, page_size=MAX_PAGE_SIZE):
    """All readings of one prognosis, sorted by time, fetched page by page (A5-IMP R7).
    Returns None if a request failed."""
    readings = []
    page = 0
    while True:
        batch = (
            Q()
            .filter(datapointPrognosisId__equals=prognosis_id)
            .order_by("time", "asc")
            .paginate(page=page, size=page_size)
            .get("/prognosis-readings")
        )
        if batch is None:
            return None
        readings.extend(batch)
        if len(batch) < page_size:
            break
        page += 1
    return readings


def get_last_prognosis_readings(dp_identifier, page_size=MAX_PAGE_SIZE):
    """All readings of the datapoint's latest prognosis (empty list if it has none), or None on a failed request."""
    dp = get_datapoint(dp_identifier)
    if not dp:
        return None
    last_prognosis_id = dp[0].get("lastPrognosisId")
    if last_prognosis_id is None:
        logger.warning(f"No prognosis available for datapoint '{dp_identifier}'.")
        return []
    return get_prognosis_readings(last_prognosis_id, page_size=page_size)


##########################################################
# POST
##########################################################

def post_datapoint_prognosis(datapoint_id, prognosis_time, readings):
    """Post one prognosis and all its readings in one batch (A5-IMP R9).
    readings: list of {"time": ISO string, "value": float}. Raises RuntimeError on any failure."""
    prognosis = Q().post("/datapoint-prognoses", json={"datapointId": datapoint_id, "time": prognosis_time})
    if not prognosis or "id" not in prognosis:
        raise RuntimeError(f"posting the prognosis for datapoint id {datapoint_id} failed")
    payload = [{"time": r["time"], "value": r["value"], "datapointPrognosisId": prognosis["id"]} for r in readings]
    saved = Q().post("/prognosis-readings/batch", json=payload)
    if saved is None or len(saved) != len(payload):
        raise RuntimeError(f"posting {len(payload)} prognosis readings failed "
                           f"(saved {0 if saved is None else len(saved)})")
    return prognosis
