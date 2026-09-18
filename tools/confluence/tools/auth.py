from typing import Any
from urllib.parse import urlparse

from atlassian import ConfluenceV2
from atlassian.confluence import ConfluenceServer


def auth(credential: dict[str, Any]) -> ConfluenceV2 | ConfluenceServer:
    """
    Authenticate to Confluence using environment variables.
    """
    url = credential.get("url")
    hostname = urlparse(url).hostname or ""
    is_cloud = hostname in {"atlassian.net", "jira.com", "api.atlassian.com"} or hostname.endswith(
        (".atlassian.net", ".jira.com")
    )
    client = ConfluenceV2 if is_cloud else ConfluenceServer
    confluence = client(
        url=url,
        username=credential.get("username"),
        password=credential.get("token"),
        cloud=is_cloud,
    )
    return confluence
