import requests
import logging


logger = logging.getLogger("A5Runner")

class Query:
    def __init__(self, base_url, headers=None, timeout=10):

        self.base_url = base_url.rstrip('/')
        self.headers = headers or {}
        self.params = {}
        self.timeout = timeout
        self.logger = logging.getLogger(__name__)
        #logger.info(f"Query initialized with base_url={base_url}")

    def post(self, endpoint, data=None, json=None):
        return self._request("POST", endpoint, data=data, json=json)

    def put(self, endpoint, data=None, json=None):
        return self._request("PUT", endpoint, data=data, json=json)

    def delete(self, endpoint):
        return self._request("DELETE", endpoint)

    def filter(self, **kwargs):
        for key, value in kwargs.items():
            key = key.replace("__", ".")
            self.params[key] = value
        return self

    def paginate(self, page=0, size=100):
        self.params["page"] = page
        self.params["size"] = size
        return self

    def order_by(self, field, direction="asc"):
        # direction = "asc" or "desc"
        self.params["sort"] = f"{field},{direction}"
        return self

    def get(self, endpoint, params=None):
        # combine all self.params and additional parameters
        combined_params = self.params.copy()
        if params:
            combined_params.update(params)
        response = self._request("GET", endpoint, params=combined_params)
        self.params.clear()  # clean up params to make queries independent
        return response

    def fetch(self, endpoint):
        return self.get(endpoint)

    def post_fetch(self, endpoint, data=None, json=None):
        return self.post(endpoint, data=data, json=json)

    def _request(self, method, endpoint, **kwargs):
        url = f"{self.base_url}{endpoint}"
        
        try:
            response = requests.request(
                method,
                url,
                headers=self.headers,
                timeout=self.timeout,
                **kwargs
            )
            response.raise_for_status()
            #logger.info(f"{method} {url} – {response.status_code}")
            if response.content:
                return response.json()
            return None
        except requests.HTTPError as e:
            logger.error(f"{method} {url} – {response.status_code}")
            logger.error(f"HTTP error: {e.response.status_code} {e.response.text}")
        except requests.RequestException as e:
            logger.error(f"Request failed: {e}")
        return None
