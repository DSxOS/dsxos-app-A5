from Query import Query
import logging

#loki-logger-handler1.1.2 importida, req.txt 

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[
        logging.FileHandler("query.log"),
        logging.StreamHandler()  # logs to terminal
        
    ]
)

logger = logging.getLogger(__name__)

url = "http://localhost:8080/api"
headers={"Authorization": "Bearer YOUR_TOKEN"}

###########################################################
# GET
###########################################################

# GET datapoint data
def get_datapoint(dp_identifier):
    dp_data = (
        Query(url)
        .filter(identifier__equals=dp_identifier)
        .paginate(page=0, size=1)
        .get("/datapoints")
    )
    return dp_data

# Get datapoint last reading data
def get_last_reading(dp_id):
    last_reading = (
        Query(url)
        .filter(datapointId__equals=dp_id)
        .order_by("time", "desc")
        .paginate(page=0, size=1)
        .get("/readings")
    )
    return last_reading

def get_last_reading(dp_identifier):
    dp_data = get_datapoint(dp_identifier)
    dp_id = dp_data[0]["id"]
    last_reading = (
        Query(url)
        .filter(datapointId__equals=dp_id)
        .order_by("time", "desc")
        .paginate(page=0, size=1)
        .get("/readings")
    )
    return last_reading
def get_last_reading_value(dp_identifier):
    dp_data = get_datapoint(dp_identifier)
    dp_id = dp_data[0]["id"]
    last_reading = (
        Query(url)
        .filter(datapointId__equals=dp_id)
        .order_by("time", "desc")
        .paginate(page=0, size=1)
        .get("/readings")
    )
    return last_reading[0].get("value")

# GET datapoint last prognosis readings data
def get_last_prognosis_readings(dp_identifier):
    last_prognosis_id = get_datapoint(dp_identifier)[0].get("lastPrognosisId")
    if last_prognosis_id is not None:
        last_prognosis_readings = (
            Query(url, headers=headers)
            .filter(datapointPrognosisId__equals=last_prognosis_id)
            .get("/prognosis-readings")
        )
        #print(f"last_prognosis_readings ===== ", last_prognosis_readings)
        return last_prognosis_readings

    else:
        print("No prognosis available for this datapoint.")
        logger.warning("No prognosis available for this datapoint.")
        
def get_datapoint_prognosis(dp_identifier):
    last_prognosis_id = get_datapoint(dp_identifier)[0].get("lastPrognosisId")
    if last_prognosis_id is not None:
        datapoint_prognosis = (
            Query(url, headers=headers)
            .filter(Id__equals=last_prognosis_id)
            .get("/datapoint-prognoses")
        )
        print(f"datapoint_prognosis ++++ ", datapoint_prognosis)
        return datapoint_prognosis
    else:
        print("No prognosis available for this datapoint.")
        logger.warning("No prognosis available for this datapoint.")
        
##########################################################        
# POST
##########################################################
# POST prognosis readings
def post_prognosis_readings(prognosis_readings_payload):
    for reading in prognosis_readings_payload:
        
        response = (
            Query(url, headers=headers)
            .post("/prognosis-readings", json=reading)
        )
        
    return response

# POST datapoint prognosis
def post_datapoint_prognosis(prognosis_payload):

    response = (
        Query(url, headers=headers)
        .post("/datapoint-prognoses", json=prognosis_payload)
    )
    
    prognosis_readings_payload = prognosis_payload["readings"]
    for dp_pr_id in prognosis_readings_payload:
        dp_pr_id["datapointPrognosisId"] = response["id"]

    post_prognosis_readings(prognosis_readings_payload)
    
    return response

