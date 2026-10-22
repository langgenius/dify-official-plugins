"""
Shared Microsoft Graph plumbing for the Teams tools.

Teams uses delegated OAuth only: posting messages, chats and group calendars are
not available to app-only tokens, so every call acts as the signed-in user.

The OAuth credential remembers which Microsoft cloud it was authorized against
(``graph_base_url``); credentials authorized before national-cloud support have
none and stay on the global cloud. The login host and the Graph host are always
looked up together from ``CLOUDS`` so they never point at different clouds.
"""

import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Mapping
from urllib.parse import quote, unquote, urlparse

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


def bounded_int(value: Any, default: int, low: int, high: int, name: str) -> int:
    """An integer parameter within [low, high]; empty means the default."""
    if value in (None, ""):
        return default
    try:
        number = int(value)
    except (TypeError, ValueError) as e:
        raise GraphError(f"{name} must be a number from {low} to {high}.") from e
    if not low <= number <= high:
        raise GraphError(f"{name} must be a number from {low} to {high}.")
    return number


def check_next_link(ctx: GraphContext, next_link: str, resource_path: str) -> str:
    """
    Accept a continuation link only if it points at the same Graph host, API version and
    resource path the tool reads (e.g. ``/me/chats``), so the bearer token is never sent
    elsewhere and a link for another chat cannot be slipped in.
    """
    parsed = urlparse(next_link.strip())
    expected = urlparse(f"{ctx.api_base}{resource_path}")
    path = unquote(parsed.path)
    same_path = path == unquote(expected.path)
    if not same_path and resource_path.startswith("/me/"):
        # Graph may phrase the continuation of /me/... as /users/{id}/...
        prefix, _, rest = unquote(expected.path).partition("/me/")
        parts = path[len(prefix):].strip("/").split("/") if path.startswith(prefix + "/users/") else []
        same_path = len(parts) >= 3 and parts[0] == "users" and "/".join(parts[2:]) == rest
    if (parsed.scheme, parsed.netloc) != (expected.scheme, expected.netloc) or not same_path:
        raise GraphError(f"next_link must be a Microsoft Graph link for {resource_path} returned by this tool.")
    return next_link.strip()


@dataclass
class Page:
    items: list[dict[str, Any]]
    pages: int
    next_link: str | None
    error: str | None = None

    @property
    def complete(self) -> bool:
        return self.next_link is None and self.error is None


def paginate(
    ctx: GraphContext,
    url: str,
    params: Mapping[str, Any] | None,
    *,
    resource_path: str,
    max_pages: int,
    budget_seconds: float = 70.0,
) -> Page:
    """
    Read up to ``max_pages`` pages, following @odata.nextLink even across empty pages
    (Graph returns empty pages while a filter is still scanning), and stop early when the
    time budget is used up. An error on the first page raises; a later error returns what
    was read so far with the link to resume from.
    """
    started = time.monotonic()
    items: list[dict[str, Any]] = []
    pages = 0
    current: str | None = url
    while current and pages < max_pages:
        if pages and time.monotonic() - started > budget_seconds:
            break
        try:
            body = ctx.request("GET", current[len(ctx.api_base):] if current.startswith(ctx.api_base) else current, params=params).json()
        except GraphError as e:
            if not pages:
                raise
            return Page(items, pages, current, str(e))
        pages += 1
        items.extend(body.get("value", []))
        link = body.get("@odata.nextLink")
        current = check_next_link(ctx, link, resource_path) if link else None
        params = None  # the next link already carries the query
    return Page(items, pages, current)


# ── flat, typed fields for the tools' output variables ────────────────


def _s(value: Any) -> str:
    return "" if value is None else str(value)


def message_vars(msg: Mapping[str, Any]) -> dict[str, Any]:
    """A channel or chat message as flat fields (sender, body, times, link)."""
    sender = msg.get("from") or {}
    who = sender.get("user") or sender.get("application") or sender.get("device") or {}
    body = msg.get("body") or {}
    return {
        "id": _s(msg.get("id")),
        "message_type": _s(msg.get("messageType")),
        "subject": _s(msg.get("subject")),
        "content": _s(body.get("content")),
        "content_type": _s(body.get("contentType")),
        "from_name": _s(who.get("displayName")),
        "from_user_id": _s(who.get("id")),
        "created_datetime": _s(msg.get("createdDateTime")),
        "last_modified_datetime": _s(msg.get("lastModifiedDateTime")),
        "web_url": _s(msg.get("webUrl")),
        "reply_to_id": _s(msg.get("replyToId")),
        "attachment_names": [_s(a.get("name")) for a in msg.get("attachments") or []],
    }


def task_vars(task: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "task_id": _s(task.get("id")),
        "title": _s(task.get("title")),
        "bucket_id": _s(task.get("bucketId")),
        "percent_complete": int(task.get("percentComplete") or 0),
        "due_datetime": _s(task.get("dueDateTime")),
    }


def meeting_vars(meeting: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "meeting_id": _s(meeting.get("id")),
        "subject": _s(meeting.get("subject")),
        "join_url": _s(meeting.get("joinWebUrl")),
        "start": _s(meeting.get("startDateTime")),
        "end": _s(meeting.get("endDateTime")),
    }
