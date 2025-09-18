from typing import Dict, Any, Optional
from urllib.parse import urljoin

import requests


class APIRequestTool:
    """
    A simple HTTP client for making API requests with support for GET, POST, PUT, DELETE methods.
    """

    def __init__(self, base_url: str, token: str):
        if not base_url:
            self.base_url = "https://api.jiandaoyun.com/api/"
        else:
            self.base_url = base_url.rstrip("/") + "/"
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        url = urljoin(self.base_url, endpoint.lstrip("/"))
        try:
            response = requests.request(
                method=method.upper(),
                url=url,
                headers=self.headers,
                params=params,
                json=data,
                timeout=10,
            )

            response.raise_for_status()

            try:
                response_data = response.json()
            except ValueError:
                response_data = {"raw_response": response.text}
            return {
                "status": "success",
                "data": response_data,
                "message": "Request completed successfully",
            }

        except requests.exceptions.HTTPError as http_err:
            return {
                "status": "error",
                "data": None,
                "message": f"HTTP error occurred: {str(http_err)}",
            }
        except requests.exceptions.ConnectionError:
            return {
                "status": "error",
                "data": None,
                "message": "Failed to connect to the server",
            }
        except requests.exceptions.Timeout:
            return {"status": "error", "data": None, "message": "Request timed out"}
        except requests.exceptions.RequestException as req_err:
            return {
                "status": "error",
                "data": None,
                "message": f"Request failed: {str(req_err)}",
            }

    def create(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        return self.make_request("POST", endpoint, data=data)

    def read(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self.make_request("GET", endpoint, params=params, data=data)

    def update(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        return self.make_request("PUT", endpoint, data=data)

    def delete(self, endpoint: str) -> Dict[str, Any]:
        return self.make_request("DELETE", endpoint)
