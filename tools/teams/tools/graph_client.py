"""
Shared Microsoft Graph plumbing for the Teams tools.

Teams uses delegated OAuth only: posting messages, chats and group calendars are
not available to app-only tokens, so every call acts as the signed-in user.

The OAuth credential remembers which Microsoft cloud it was authorized against
(``graph_base_url``); credentials authorized before national-cloud support have
none and stay on the global cloud. The login host and the Graph host are always
looked up together from ``CLOUDS`` so they never point at different clouds.
"""

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Mapping
from urllib.parse import quote

import requests

# cloud -> (Entra login host, Microsoft Graph host)
CLOUDS: dict[str, tuple[str, str]] = {
    "global": ("https://login.microsoftonline.com", "https://graph.microsoft.com"),
    "usgov": ("https://login.microsoftonline.us", "https://graph.microsoft.us"),
    "dod": ("https://login.microsoftonline.us", "https://dod-graph.microsoft.us"),
    "china": ("https://login.partner.microsoftonline.cn", "https://microsoftgraph.chinacloudapi.cn"),
}
DEFAULT_CLOUD = "global"
GRAPH_HOSTS = {host for _, host in CLOUDS.values()}


class GraphError(Exception):
    """A Graph call that could not be made or did not succeed; the message is shown to the user."""


def cloud_hosts(cloud: str | None) -> tuple[str, str]:
    """Return (login host, Graph host) for a cloud name; unknown names are rejected."""
    name = (cloud or DEFAULT_CLOUD).strip().lower()
    if name not in CLOUDS:
        raise GraphError(f"Unknown Microsoft cloud '{cloud}'. Use one of: {', '.join(CLOUDS)}.")
    return CLOUDS[name]


def segment(value: Any) -> str:
    """Quote an ID for use as one URL path segment (Teams IDs contain ':' and '@')."""
    return quote(str(value).strip(), safe="")


def require(tool_parameters: Mapping[str, Any], *names: str) -> list[str]:
    """Return the stripped values of required string parameters, or raise naming the first missing one."""
    values = []
    for name in names:
        value = str(tool_parameters.get(name) or "").strip()
        if not value:
            raise GraphError(f"{name} is required.")
        values.append(value)
    return values


def split_list(value: Any) -> list[str]:
    """Split a comma- or newline-separated parameter into its non-empty items."""
    return [item.strip() for item in str(value or "").replace("\n", ",").split(",") if item.strip()]


def to_graph_datetime(value: str, name: str) -> tuple[str, bool]:
    """
    Normalize an ISO 8601 date or date-time to the UTC form Graph expects
    (``2026-12-01T09:00:00Z``). Returns (value, assumed_utc): a value without a
    UTC offset is taken as UTC, and the caller says so in its reply.
    """
    text = value.strip()
    try:
        if len(text) == 10:
            parsed = datetime.combine(date.fromisoformat(text), datetime.min.time())
        else:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as e:
        raise GraphError(f"{name} must be an ISO 8601 date or date-time, e.g. 2026-12-01T09:00:00+09:00.") from e
    assumed_utc = parsed.tzinfo is None
    if assumed_utc:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), assumed_utc


def etag_of(ctx: "GraphContext", path: str) -> str:
    """Planner updates and deletes need the item's current ETag in If-Match."""
    etag = ctx.request("GET", path).json().get("@odata.etag")
    if not etag:
        raise GraphError("Microsoft Graph returned no ETag for this item.")
    return etag


@dataclass(frozen=True)
class GraphContext:
    access_token: str
    # Graph v1.0 root, e.g. https://graph.microsoft.com/v1.0
    api_base: str

    @property
    def graph_host(self) -> str:
        return self.api_base.rsplit("/v1.0", 1)[0]

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
        headers: Mapping[str, str] | None = None,
        timeout: int = 30,
    ) -> requests.Response:
        """Call ``{api_base}{path}``; network errors and non-2xx answers raise GraphError."""
        all_headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}
        all_headers.update(headers or {})
        try:
            response = requests.request(
                method, f"{self.api_base}{path}", headers=all_headers, params=params, json=json, timeout=timeout
            )
        except requests.exceptions.RequestException as e:
            raise GraphError(f"Network error: {e}") from e
        if response.status_code < 200 or response.status_code >= 300:
            raise GraphError(describe_error(response))
        return response


def describe_error(response: requests.Response) -> str:
    """Turn a Graph error response into a short message with a hint for the common cases."""
    try:
        error = response.json().get("error") or {}
        detail = f"{error.get('code', '')}: {error.get('message', '')}".strip(": ")
    except ValueError:
        detail = response.text[:300]
    hint = {
        401: "The sign-in has expired; re-authorize the plugin.",
        403: "A required delegated permission is missing or not consented; see the plugin's setup guide.",
        404: "Not found; check the IDs (get them from the List tools).",
        412: "The item changed since it was read; run the tool again.",
        429: "Microsoft Graph is throttling requests; wait a moment and retry.",
    }.get(response.status_code, "")
    return f"API error {response.status_code}: {detail}" + (f" {hint}" if hint else "")


def resolve_graph_context(credentials: Mapping[str, Any]) -> GraphContext:
    """Turn the runtime OAuth credentials into a token and the Graph v1.0 root."""
    token = credentials.get("access_token")
    if not token:
        raise GraphError("Access token is required in credentials.")
    graph_host = (credentials.get("graph_base_url") or CLOUDS[DEFAULT_CLOUD][1]).rstrip("/")
    if graph_host not in GRAPH_HOSTS:
        # Never send the bearer token to a host that is not a Microsoft Graph endpoint.
        raise GraphError(f"Unsupported Microsoft Graph endpoint '{graph_host}'.")
    return GraphContext(token, f"{graph_host}/v1.0")
