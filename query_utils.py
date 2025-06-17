from Query import Query
import logging


logger = logging.getLogger()

_query_url = None
_query_headers = None

def init(url, headers):
    global _query_url, _query_headers
    _query_url = url
    _query_headers = headers
    logger.info(f"query_utils initialized with URL: {_query_url}")
    
# Helper to create Query object
def Q():
    return Query(_query_url, headers=_query_headers)
    
###########################################################
# GET
###########################################################

# GET datapoint data
def get_datapoint(dp_identifier):
    dp_data = (
        Q()
        .filter(identifier__equals=dp_identifier)
        .paginate(page=0, size=1)
        .get("/datapoints")
    )
    return dp_data

# Get datapoint last reading by identifier
def get_last_reading(dp_identifier):
    dp_data = get_datapoint(dp_identifier)
    dp_id = dp_data[0]["id"]
    last_reading = (
        Q()
        .filter(datapointId__equals=dp_id)
        .order_by("time", "desc")
        .paginate(page=0, size=1)
        .get("/readings")
    )
    return last_reading

# Get datapoint last reading value by identifier
def get_last_reading_value(dp_identifier):
    last_reading_value = get_last_reading(dp_identifier)
    return last_reading_value[0].get("value")

# GET datapoint last prognosis readings data
def get_last_prognosis_readings(dp_identifier):
    last_prognosis_id = get_datapoint(dp_identifier)[0].get("lastPrognosisId")
    if last_prognosis_id is not None:
        last_prognosis_readings = (
            Q()
            .filter(datapointPrognosisId__equals=last_prognosis_id)
            .get("/prognosis-readings")
        )
        return last_prognosis_readings

    else:
        logger.warning("No prognosis available for this datapoint.")
        return []
        
# GET datapoint's last datapoint prognosis
def get_datapoint_prognosis(dp_identifier):
    last_prognosis_id = get_datapoint(dp_identifier)[0].get("lastPrognosisId")
    if last_prognosis_id is not None:
        datapoint_prognosis = (
            Q()
            .filter(Id__equals=last_prognosis_id)
            .get("/datapoint-prognoses")
        )
        logger.info(f"datapoint_prognosis: {datapoint_prognosis}")
        return datapoint_prognosis
    else:
        logger.warning("No prognosis available for this datapoint.")
        return None
        
##########################################################        
# POST
##########################################################
# POST prognosis readings
def post_prognosis_readings(prognosis_readings_payload):
    for reading in prognosis_readings_payload:
        response = (Q().post("/prognosis-readings", json=reading))
    return response

# POST datapoint prognosis
def post_datapoint_prognosis(prognosis_payload):
    response = (Q().post("/datapoint-prognoses", json=prognosis_payload))
    
    prognosis_readings_payload = prognosis_payload["readings"]
    for dp_pr_id in prognosis_readings_payload:
        dp_pr_id["datapointPrognosisId"] = response["id"]
    post_prognosis_readings(prognosis_readings_payload)
    
    return response

