import os
from typing import Literal, Optional, TypedDict

import requests

API_BASE_URL = "https://api.spider.cloud/v1"
# Seconds to wait for the API. Crawls stream pages as they finish, so the read timeout
# stays under the plugin daemon's MAX_REQUEST_TIMEOUT of 120 seconds.
REQUEST_TIMEOUT = (10, 110)


class RequestParamsDict(TypedDict, total=False):
    url: Optional[str]
    request: Optional[Literal["http", "browser", "smart"]]
    limit: Optional[int]
    return_format: Optional[Literal["raw", "markdown", "commonmark", "html2text", "text", "xml", "bytes"]]
    tld: Optional[bool]
    depth: Optional[int]
    cache: Optional[bool]
    budget: Optional[dict[str, int]]
    locale: Optional[str]
    cookies: Optional[str]
    stealth: Optional[bool]
    headers: Optional[dict[str, str]]
    metadata: Optional[bool]
    viewport: Optional[dict[str, int]]
    encoding: Optional[str]
    subdomains: Optional[bool]
    user_agent: Optional[str]
    fingerprint: Optional[bool]
    readability: Optional[bool]
    respect_robots: Optional[bool]
    root_selector: Optional[str]
    exclude_selector: Optional[str]
    blacklist: Optional[list[str]]
    whitelist: Optional[list[str]]
    full_resources: Optional[bool]
    request_timeout: Optional[int]
    run_in_background: Optional[bool]
    skip_config_checks: Optional[bool]


class SpiderError(Exception):
    """An error returned by the Spider API, with a message safe to show the user."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class Spider:
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the Spider with an API key.

        :param api_key: A string of the API key for Spider. Defaults to the SPIDER_API_KEY environment variable.
        :raises ValueError: If no API key is provided.
        """
        self.api_key = api_key or os.getenv("SPIDER_API_KEY")
        if not self.api_key:
            raise ValueError("No API key provided")

    def api_post(
        self,
        endpoint: str,
        data: dict,
        stream: bool,
        content_type: str = "application/json",
    ):
        """
        Send a POST request to the specified API endpoint.

        :param endpoint: The API endpoint to which the POST request is sent.
        :param data: The data (dictionary) to be sent in the POST request.
        :param stream: Boolean indicating if the response should be streamed.
        :return: The JSON response or the raw response stream if stream is True.
        """
        headers = self._prepare_headers(content_type)
        response = self._post_request(f"{API_BASE_URL}/{endpoint}", data, headers, stream)

        if response.status_code == 200:
            return response if stream else response.json()
        self._handle_error(response, f"post to {endpoint}")

    def api_get(self, endpoint: str, stream: bool = False, content_type: str = "application/json"):
        """
        Send a GET request to the specified endpoint.

        :param endpoint: The API endpoint from which to retrieve data.
        :return: The JSON decoded response.
        """
        headers = self._prepare_headers(content_type)
        response = self._get_request(f"{API_BASE_URL}/{endpoint}", headers, stream)
        if response.status_code == 200:
            return response.json()
        self._handle_error(response, f"get from {endpoint}")

    def get_credits(self):
        """
        Retrieve the account's remaining credits. This call does not spend credits.

        :return: JSON response containing the number of credits left.
        """
        return self.api_get("data/credits")

    def scrape_url(
        self,
        url: str,
        params: Optional[RequestParamsDict] = None,
        stream: bool = False,
        content_type: str = "application/json",
    ):
        """
        Scrape one page from the specified URL, with no link traversal.

        :param url: The URL from which to scrape data.
        :param params: Optional dictionary of additional parameters for the scrape request.
        :return: JSON response containing the scraping results.
        """
        params = dict(params or {})
        params.setdefault("return_format", "markdown")
        # /scrape fetches one page; crawl-only fields do not apply.
        for key in ("limit", "depth", "blacklist", "whitelist", "subdomains", "tld", "budget"):
            params.pop(key, None)

        return self.api_post("scrape", {**params, "url": url}, stream, content_type)

    def crawl_url(
        self,
        url: str,
        params: Optional[RequestParamsDict] = None,
        stream: bool = False,
        content_type: str = "application/json",
    ):
        """
        Start crawling at the specified URL.

        :param url: The URL to begin crawling.
        :param params: Optional dictionary with additional parameters to customize the crawl.
        :param stream: Boolean indicating if the response should be streamed. Defaults to False.
        :return: JSON response or the raw response stream if streaming enabled.
        """
        params = dict(params or {})
        params.setdefault("return_format", "markdown")

        return self.api_post("crawl", {**params, "url": url}, stream, content_type)

    def links(
        self,
        url: str,
        params: Optional[RequestParamsDict] = None,
        stream: bool = False,
        content_type: str = "application/json",
    ):
        """
        Retrieve links from the specified URL.

        :param url: The URL from which to extract links.
        :param params: Optional parameters for the link retrieval request.
        :return: JSON response containing the links.
        """
        return self.api_post("links", {**(params or {}), "url": url}, stream, content_type)

    def _prepare_headers(self, content_type: str = "application/json"):
        return {
            "Content-Type": content_type,
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "Spider-Dify-Plugin",
        }

    def _post_request(self, url: str, data, headers, stream=False):
        return requests.post(url, headers=headers, json=data, stream=stream, timeout=REQUEST_TIMEOUT)

    def _get_request(self, url: str, headers, stream=False):
        return requests.get(url, headers=headers, stream=stream, timeout=REQUEST_TIMEOUT)

    @staticmethod
    def _error_detail(response) -> str:
        try:
            body = response.json()
        except ValueError:
            return ""
        if isinstance(body, dict):
            return str(body.get("error") or body.get("message") or "")
        return ""

    def _handle_error(self, response, action):
        status = response.status_code
        detail = self._error_detail(response)
        if status == 401:
            raise SpiderError("Not a valid Spider API key.", status)
        if status == 402:
            raise SpiderError(
                detail or "Not enough credits in the Spider account. Add credits at https://spider.cloud/credits/new",
                status,
            )
        if status == 429:
            retry_after = response.headers.get("Retry-After") if response.headers else None
            wait = f" Retry after {retry_after} seconds." if retry_after else ""
            raise SpiderError(f"Spider rate limit reached.{wait}", status)
        message = f"Failed to {action}. Status code: {status}."
        if detail:
            message += f" Error: {detail}"
        raise SpiderError(message, status)
