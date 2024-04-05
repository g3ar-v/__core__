import requests
from requests import HTTPError

from source.configuration import Configuration
from source.util.log import LOG


class Api:
    def __init__(self, path):
        self.path = path

        config = Configuration.get()
        config_server = config.get("ui_server", {})
        self.url = config_server.get("url", {})
        self.version = config_server.get("version", {})

    def request(self, params):
        if "path" in params:
            params["path"] = params["path"]
        self.build_path(params)
        return self.send(params)

    def send(self, params, no_refresh=False):
        """Send request to core backend.
        The method handles Etags and will return a cached response value
        if nothing has changed on the remote.

        Args:
            params (dict): request parameters
            no_refresh (bool): optional parameter to disable refreshs of token

        Returns:
            Requests response object.
        """
        query_data = frozenset(params.get("query", {}).items())
        params_key = (params.get("path"), query_data)
        # etag = self.params_to_etag.get(params_key)

        method = params.get("method", "GET")
        headers = self.build_headers(params)
        data = self.build_data(params)
        json_body = self.build_json(params)
        query = self.build_query(params)
        url = self.build_url(params)

        # For an introduction to the Etag feature check out:
        # https://en.wikipedia.org/wiki/HTTP_ETag
        # if etag:
        #     headers["If-None-Match"] = etag

        response = requests.request(
            method,
            url,
            headers=headers,
            params=query,
            data=data,
            json=json_body,
            timeout=(3.05, 15),
        )
        # if response.status_code == 304:
        #     # Etag matched, use response previously cached
        #     # response = self.etag_to_response[etag]
        # elif "ETag" in response.headers:
        #     etag = response.headers["ETag"].strip('"')
        #     # Cache response for future lookup when we receive a 304
        #     self.params_to_etag[params_key] = etag
        #     self.etag_to_response[etag] = response

        return self.get_response(response, no_refresh)

    def get_response(self, response, no_refresh=False):
        """Parse response and extract data from response.

        Will try to refresh the access token if it's expired.

        Args:
            response (requests Response object): Response to parse
            no_refresh (bool): Disable refreshing of the token

        Returns:
            data fetched from server
        """
        data = self.get_data(response)

        if 200 <= response.status_code < 300:
            return data
        elif (
            not no_refresh
            and response.status_code == 401
            and not response.url.endswith("auth/token")
        ):
            self.refresh_token()
            return self.send(self.old_params, no_refresh=True)
        raise HTTPError(data, response=response)

    def get_data(self, response):
        try:
            return response.json()
        except Exception:
            return response.text

    def build_headers(self, params):
        headers = params.get("headers", {})
        self.add_content_type(headers)
        self.add_authorization(headers)
        params["headers"] = headers
        return headers

    def add_content_type(self, headers):
        if not headers.__contains__("Content-Type"):
            headers["Content-Type"] = "application/json"

    def add_authorization(self, headers):
        if not headers.__contains__("Authorization"):
            headers["Authorization"] = "Bearer "

    def build_data(self, params):
        return params.get("data")

    def build_json(self, params):
        json = params.get("json")
        if json and params["headers"]["Content-Type"] == "application/json":
            for k, v in json.items():
                if v == "":
                    json[k] = None
            params["json"] = json
        return json

    def build_query(self, params):
        return params.get("query")

    def build_path(self, params):
        path = params.get("path", "")
        params["path"] = self.path + path
        return params["path"]

    def build_url(self, params):
        path = params.get("path", "")
        version = params.get("version", self.version)
        return self.url + "/" + version + "/" + path


class SystemApi(Api):
    """Web Api wrapper for obtaining system-level information"""

    def __init__(self):
        super(SystemApi, self).__init__("system")

    def send_ai_utterance(self, data):
        LOG.info("SENDING AI MESSAGE TO UI BACKEND")
        return self.request(
            {
                "method": "POST",
                "path": "/ai/utterance",
                "json": {"role": "system", "content": data},
            }
        )
